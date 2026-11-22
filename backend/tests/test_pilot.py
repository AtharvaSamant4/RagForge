"""Synthetic, disposable engineering QA only; no real human participation."""
import concurrent.futures
import hashlib
import io
import json
import time
import uuid
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.db import SessionLocal
from app.models import User, Project, ExportJob, PilotParticipant, PilotEvent, PilotTask, PilotIssue, PilotDeployment
from app.pilot import emit, purge, CHECKS
from app import exports, worker
from app.config import settings


def enroll(client, *, consent=True):
    """Mark a disposable test account as operator; enroll QA, never real users."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == 'owner@example.com'))
        user.is_admin = True; db.commit(); user_id = user.id
    response = client.post('/v1/admin/pilot/participants', json={'email': 'owner@example.com', 'cohort': 'engineering_qa', 'authorization_obtained': True, 'authorization_reference': 'Synthetic isolated test fixture'})
    assert response.status_code == 201, response.text
    participant_id = response.json()['id']
    if consent:
        response = client.put('/v1/pilot/consent', json={'accepted': True, 'version': 'pilot-v1'})
        assert response.status_code == 200, response.text
    return user_id, participant_id


def counts():
    with SessionLocal() as db:
        return dict(db.execute(select(PilotEvent.kind, func.count()).group_by(PilotEvent.kind)).all())


def project_and_document(client):
    response = client.post('/v1/projects', json={'name': 'Synthetic engineering QA'})
    assert response.status_code == 201
    base = '/v1/projects/' + response.json()['id']
    response = client.post(base + '/documents', files={'file': ('sample.txt', b'The return period is 30 calendar days after receiving the order. Eligible products can be returned within that period.')})
    assert response.status_code == 202, response.text
    assert worker.run_once(base.split('/')[-1])
    return base, response.json()['id']


def test_default_off_and_no_backfill(owner):
    base, _ = project_and_document(owner)
    assert owner.post(base + '/query', json={'question': 'What is the return period?'}).status_code == 200
    assert counts() == {}
    enroll(owner, consent=False)
    assert owner.post(base + '/keys', json={'name': 'before consent'}).status_code == 201
    assert counts() == {}
    assert owner.put('/v1/pilot/consent', json={'accepted': True, 'version': 'pilot-v1'}).status_code == 200
    assert counts() == {'account_activation': 1}
    funnel = owner.get('/v1/pilot/me').json()['funnel']
    assert funnel['time_to_first_cited_answer_seconds'] is None
    assert not next(s for s in funnel['stages'] if s['stage'] == 'project_created')['completed']


def test_real_operation_funnel_and_redacted_report(owner):
    enroll(owner)
    base, _ = project_and_document(owner)
    secret = owner.post(base + '/keys', json={'name': 'Synthetic API client'}).json()['secret']
    marker = 'PRIVATE-QUESTION-MARKER'
    response = owner.post(base + '/query', json={'question': 'What is the return period?'}, headers={'Authorization': 'Bearer ' + secret})
    assert response.status_code == 200 and response.json()['citations']
    assert owner.post(base + '/query', json={'question': 'What is unknown about ' + marker + '?'}).status_code == 200
    c = counts()
    assert all(c.get(kind) == 1 for kind in ['account_activation', 'project_created', 'document_uploaded', 'document_indexed', 'first_cited_answer', 'api_key_created', 'external_api_query'])
    assert c['query_completed'] == 2
    assert owner.get('/v1/admin/pilot/report').json()['participants'] == []
    report = owner.get('/v1/admin/pilot/report?cohort=engineering_qa')
    assert report.status_code == 200
    assert all(value not in report.text for value in [marker, secret, 'owner@example.com', '30 calendar days', 'Synthetic isolated test fixture'])
    assert report.json()['operator_attested_real_trials'] == 0
    assert report.json()['participants'][0]['time_to_first_cited_answer_seconds'] >= 0
    assert report.json()['participants'][0]['time_from_account_creation_to_first_cited_answer_seconds'] >= report.json()['participants'][0]['time_to_first_cited_answer_seconds']
    assert report.json()['participants'][0]['time_to_observed_standalone_deployment_seconds'] is None


def test_event_deduplication_is_atomic(owner):
    user_id, _ = enroll(owner)
    def record(_):
        with SessionLocal() as db:
            result = emit(db, user_id, 'document_indexed', 'same-synthetic-operation')
            db.commit(); return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(record, range(12))) == 1
    assert counts() == {'account_activation': 1, 'document_indexed': 1}
    with SessionLocal() as db:
        assert db.scalar(select(PilotParticipant.event_count)) == 2


def test_distinct_concurrent_events_do_not_lose_counter_increments(owner):
    import threading
    user_id,_=enroll(owner);barrier=threading.Barrier(6)
    def record(i):
        with SessionLocal() as db:
            # Retain a pre-lock identity-map snapshot in every publisher.
            prior=db.scalar(select(PilotParticipant).where(PilotParticipant.user_id==user_id))
            assert prior.event_count==1
            barrier.wait(timeout=10)
            emit(db,user_id,'query_completed','synthetic-distinct-'+str(i),1.0);db.commit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(record,range(6)))
    with SessionLocal() as db:
        assert db.scalar(select(PilotParticipant.event_count))==7
        assert db.scalar(select(func.count()).select_from(PilotEvent))==7


def test_withdrawal_erases_records_and_prevents_late_events(owner):
    user_id, _ = enroll(owner)
    base, _ = project_and_document(owner)
    body = {'status': 'failed', 'duration_seconds': 42, 'errors': 2, 'assistance': 1, 'difficulty': 4, 'feedback': 'Private synthetic feedback'}
    assert owner.put('/v1/pilot/tasks/1', json=body).status_code == 200
    assert owner.post('/v1/pilot/issues', json={'category': 'ux', 'description': 'Synthetic private problem'}).status_code == 201
    assert owner.put('/v1/pilot/consent', json={'accepted': False, 'version': 'pilot-v1'}).status_code == 200
    with SessionLocal() as db:
        for model in (PilotEvent, PilotTask, PilotIssue, PilotDeployment):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert not emit(db, user_id, 'document_indexed', 'late-worker-operation')
        db.commit()
    assert owner.put('/v1/pilot/tasks/1', json=body).status_code == 403
    assert owner.post(base + '/query', json={'question': 'What is the return period?'}).status_code == 200
    assert counts() == {}
    assert owner.put('/v1/pilot/consent', json={'accepted': True, 'version': 'pilot-v1'}).status_code == 200
    assert counts() == {'account_activation': 1}


def test_authorization_tenant_boundaries_and_qa_never_counts_as_humans(owner):
    _, id_ = enroll(owner)
    with TestClient(app, headers={'Origin': 'http://localhost:3000'}) as other:
        assert other.get('/v1/admin/pilot/report').status_code == 401
        assert other.post('/v1/auth/register', json={'email': 'synthetic-other@example.com', 'password': 'synthetic-test-password'}).status_code == 201
        assert other.get('/v1/pilot/me').json()['enrolled'] is False
        assert other.get(f'/v1/admin/pilot/participants/{id_}/feedback').status_code == 403
        assert other.delete(f'/v1/admin/pilot/participants/{id_}').status_code == 403
        assert other.get('/v1/admin/pilot/readiness').status_code == 403
        assert other.post('/v1/admin/pilot/participants', json={'email': 'synthetic-other@example.com', 'cohort': 'human', 'authorization_obtained': True, 'authorization_reference': 'not authorized'}).status_code == 403
        assert other.put('/v1/pilot/consent', json={'accepted': True, 'version': 'pilot-v1'}).status_code == 403
    assert owner.post(f'/v1/admin/pilot/participants/{id_}/review-trial', json={'actual_participation_attested': True}).status_code == 409
    assert owner.post(f'/v1/admin/pilot/participants/{id_}/review-trial').status_code == 422
    assert owner.get('/v1/admin/pilot/readiness').json()['actual_participant_trials']['operator_attested_count'] == 0


def test_feedback_is_private_and_issue_export_requires_review(owner):
    _, id_ = enroll(owner)
    private = 'PRIVATE FEEDBACK MARKER owner@example.com'
    body = {'status': 'abandoned', 'duration_seconds': 88, 'errors': 3, 'assistance': 2, 'difficulty': 5, 'feedback': private}
    assert owner.put('/v1/pilot/tasks/1',json={**body,'difficulty':0}).status_code==422
    assert owner.put('/v1/pilot/tasks/2', json=body).status_code == 200
    assert owner.put('/v1/pilot/tasks/2', json={**body, 'errors': 4}).status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PilotTask)) == 1
    report = owner.get('/v1/admin/pilot/report?cohort=engineering_qa')
    assert private not in report.text
    assert report.json()['participants'][0]['reported_tasks'][0]['errors'] == 4
    assert private in owner.get(f'/v1/admin/pilot/participants/{id_}/feedback').text
    issue_id = owner.post('/v1/pilot/issues', json={'category': 'setup', 'description': private}).json()['id']
    assert owner.get(f'/v1/admin/pilot/issues/{issue_id}/export').status_code == 409
    review = {'severity': 'high', 'status': 'investigating', 'sanitized_reproduction': 'User reported owner@example.com', 'engineering_reference': 'ENG-123', 'export_approved': True}
    assert owner.put(f'/v1/admin/pilot/issues/{issue_id}', json=review).status_code == 422
    review['sanitized_reproduction'] = 'On a fresh isolated installation, upload the public sample and observe a setup failure.'
    assert owner.put(f'/v1/admin/pilot/issues/{issue_id}', json=review).status_code == 200
    exported = owner.get(f'/v1/admin/pilot/issues/{issue_id}/export')
    assert exported.status_code == 200 and private not in exported.text
    assert 'description' not in exported.json()


def test_retention_and_deletion_leave_application_usable(owner):
    enroll(owner)
    base, _ = project_and_document(owner)
    assert owner.delete('/v1/pilot/me').status_code == 200
    assert owner.get('/v1/pilot/me').json()['enrolled'] is False
    assert owner.get(base).status_code == 200
    assert counts() == {}
    enroll(owner)
    with SessionLocal() as db:
        row = db.scalar(select(PilotParticipant)); row.expires_at = time.time() - 1; db.commit()
    assert owner.get('/v1/pilot/me').json()['enrolled'] is False
    assert counts() == {}


def test_failed_uploads_processing_and_quotas_are_observed(owner, monkeypatch):
    enroll(owner)
    base = '/v1/projects/' + owner.post('/v1/projects', json={'name': 'Synthetic failures'}).json()['id']
    assert owner.post(base + '/documents', files={'file': ('bad.exe', b'not a supported file')}).status_code == 422
    assert owner.post(base + '/documents', content=b'x', headers={'Content-Length': str(22 * 1024 ** 2)}).status_code == 413
    assert owner.post(base + '/documents', files={'file': ('broken.pdf', b'%PDF-1.7\nnot-a-pdf')}).status_code == 202
    assert worker.run_once(base.split('/')[-1])
    c = counts()
    assert c['upload_failed'] == 2 and c['quota_error'] == 1 and c['processing_failed'] == 1
    monkeypatch.setattr(settings(), 'max_documents_per_project', 1)
    assert owner.post(base + '/documents', files={'file': ('extra.txt', b'Text')}).status_code == 409
    assert counts()['quota_error'] == 2


def opted_export(owner, base, doc_id):
    response = owner.post(base + '/exports', json={'mode': 'snapshot', 'document_ids': [doc_id], 'acknowledge_copy': True, 'include_pilot_evidence': True})
    assert response.status_code == 202, response.text
    assert exports.run_once()
    download = owner.get(base + '/exports/' + response.json()['id'] + '/download')
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        return json.loads(archive.read('config/pilot-evidence.json')), download.content


def signed_proof(config, cited=True):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    payload = {k: config[k] for k in ('deployment_id', 'export_id', 'template_sha256', 'challenge')}
    payload.update(version=1, boot_id=str(uuid.uuid4()), started_at=time.time(), cited_query_at=time.time() if cited else None, database_ready=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    return {'payload': payload, 'signature': Ed25519PrivateKey.from_private_bytes(bytes.fromhex(config['private_key_hex'])).sign(encoded).hex()}


def test_deployment_requires_explicit_consent_and_runtime_evidence(owner):
    base, doc_id = project_and_document(owner)
    assert owner.post(base + '/exports', json={'include_pilot_evidence': True}).status_code == 403
    enroll(owner)
    config, _ = opted_export(owner, base, doc_id)
    assert counts()['standalone_exported'] == 1
    assert 'independent_startup' not in counts()  # ZIP creation/download proves no deployment.
    proof = signed_proof(config, False)
    assert owner.post('/v1/pilot/deployment-evidence', json={**proof, 'signature': '0' * 128}).status_code == 422
    assert owner.post('/v1/pilot/deployment-evidence', json=proof).status_code == 200
    assert 'standalone_cited_query' not in counts()
    proof = signed_proof(config)
    assert owner.post('/v1/pilot/deployment-evidence', json=proof).status_code == 200
    assert owner.post('/v1/pilot/deployment-evidence', json=proof).json()['duplicate'] is True
    assert counts()['independent_startup'] == counts()['standalone_cited_query'] == 1
    assert owner.get('/v1/admin/pilot/report').json()['operator_attested_real_trials'] == 0
    assert owner.put('/v1/pilot/consent', json={'accepted': False, 'version': 'pilot-v1'}).status_code == 200
    assert owner.post('/v1/pilot/deployment-evidence', json=proof).status_code == 403
    assert counts() == {}
    with SessionLocal() as db:
        job=db.get(ExportJob,config['export_id'])
        assert job.status=='expired' and 'pilot_evidence' not in job.config
        assert not exports.artifact(job.id).exists()


def test_operator_readiness_is_an_attestation_not_an_automatic_grant(owner):
    enroll(owner)
    before = owner.get('/v1/admin/pilot/readiness').json()
    assert not before['operator_configuration']['completed']
    assert not before['external_access_authorization']['recorded']
    assert before['external_phase'] == 'pending_human_action'
    assert owner.put('/v1/admin/pilot/operator-state', json={'checklist': {'incomplete': True}, 'incident_owner': ''}).status_code == 422
    assert owner.put('/v1/admin/pilot/operator-state', json={'checklist': dict.fromkeys(CHECKS, False), 'incident_owner': '', 'user_authorization_reference': ''}).status_code == 200
    assert not owner.get('/v1/admin/pilot/readiness').json()['operator_configuration']['completed']


def test_unknown_telemetry_and_sensitive_validation_are_rejected(owner):
    enroll(owner)
    secret = 'PRIVATE-VALIDATION-CREDENTIAL'
    response = owner.put('/v1/pilot/consent', json={'accepted': True, 'version': secret, 'question': secret})
    assert response.status_code == 422 and secret not in response.text
    response = owner.put('/v1/pilot/consent', json={'accepted': True, 'version': 'pilot-v1', secret: 'extra'})
    assert response.status_code == 422 and secret not in response.text
    assert owner.post('/v1/pilot/events', json={'kind': 'first_cited_answer', 'question': secret}).status_code == 404
    assert counts() == {'account_activation': 1}


def test_evidence_cannot_cross_tenants_and_expires(owner):
    enroll(owner)
    base,doc=project_and_document(owner);config,_=opted_export(owner,base,doc);proof=signed_proof(config)
    with TestClient(app,headers={'Origin':'http://localhost:3000'}) as other:
        email='synthetic-proof-other@example.com'
        assert other.post('/v1/auth/register',json={'email':email,'password':'synthetic-other-proof-password'}).status_code==201
        assert owner.post('/v1/admin/pilot/participants',json={'email':email,'cohort':'engineering_qa','authorization_obtained':True,'authorization_reference':'Synthetic unit test only'}).status_code==201
        assert other.put('/v1/pilot/consent',json={'accepted':True,'version':'pilot-v1'}).status_code==200
        assert other.post('/v1/pilot/deployment-evidence',json=proof).status_code==404
    with SessionLocal() as db:
        row=db.get(PilotDeployment,config['deployment_id']);row.expires_at=time.time()-1;db.commit()
    assert owner.post('/v1/pilot/deployment-evidence',json=proof).status_code==410
    assert 'independent_startup' not in counts()


def test_withdrawal_racing_publishers_has_no_post_withdrawal_events(owner):
    user_id,_=enroll(owner)
    def publish(i):
        for j in range(8):
            with SessionLocal() as db:
                emit(db,user_id,'query_completed',f'synthetic-race-{i}-{j}',1.0);db.commit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        pending=[pool.submit(publish,i) for i in range(4)]
        assert owner.put('/v1/pilot/consent',json={'accepted':False,'version':'pilot-v1'}).status_code==200
        for future in pending:future.result()
    assert counts()=={}


def test_pilot_collector_failure_does_not_replace_original_response(owner,monkeypatch):
    enroll(owner);base,_=project_and_document(owner)
    def unavailable(*args):raise RuntimeError('Synthetic collector outage')
    monkeypatch.setattr('app.pilot._record_http_failure',unavailable)
    response=owner.post(base+'/documents',files={'file':('bad.exe',b'unsupported')})
    assert response.status_code==422


def test_event_cap_is_visible_and_does_not_claim_more_completion(owner):
    user_id,_=enroll(owner)
    with SessionLocal() as db:
        row=db.scalar(select(PilotParticipant));row.event_count=10000;db.commit()
        assert not emit(db,user_id,'independent_startup','synthetic-over-cap')
        db.commit()
    report=owner.get('/v1/admin/pilot/report?cohort=engineering_qa').json()
    assert report['participants'][0]['event_cap_reached']
    assert report['participants'][0]['time_to_observed_standalone_deployment_seconds'] is None


def test_public_widget_failure_is_not_participant_telemetry(owner):
    from app.pilot import record_http_failure
    user_id,_=enroll(owner)
    record_http_failure(user_id,'/v1/public/{project_id}/query',503,'synthetic-public-error')
    assert counts()=={'account_activation':1}


def test_ticket_cap_is_enforced_before_expiring_a_ready_download(owner):
    enroll(owner);base,doc=project_and_document(owner);config,_=opted_export(owner,base,doc)
    with SessionLocal() as db:
        member=db.scalar(select(PilotParticipant))
        for _ in range(49):
            db.add(PilotDeployment(participant_id=member.id,export_id=str(uuid.uuid4()),template_sha256='0'*64,public_key='0'*64,challenge='0'*64,issued_at=time.time(),expires_at=time.time()+3600))
        db.commit()
    response=owner.post(base+'/exports',json={'include_pilot_evidence':True})
    assert response.status_code==429
    assert owner.get(base+'/exports/'+config['export_id']+'/download').status_code==200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PilotDeployment))==50


def test_concurrent_api_queries_with_consent_keep_counts_and_response_budget(owner):
    enroll(owner);base,_=project_and_document(owner)
    key=owner.post(base+'/keys',json={'name':'Synthetic concurrent API clients'}).json()['secret']
    def query(_):
        with TestClient(app,headers={'Authorization':'Bearer '+key}) as client:
            response=client.post(base+'/query',json={'question':'What is the return period?'})
            return response.status_code,response.json().get('citations')
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(query,range(12)))
    assert time.perf_counter()-start<60  # Generous liveness/deadlock budget, not a capacity claim.
    assert all(status==200 and citations for status,citations in responses)
    c=counts();assert c['query_completed']==c['external_api_query']==12 and c['first_cited_answer']==1


def test_simulated_human_review_requires_attempts_and_invalidates_after_edits(owner):
    # A temporary unit-test database only. Never exported as a real human outcome.
    enroll(owner);owner.delete('/v1/pilot/me')
    r=owner.post('/v1/admin/pilot/participants',json={'email':'owner@example.com','cohort':'human','authorization_obtained':True,'authorization_reference':'SIMULATED UNIT TEST ONLY, no real human'})
    assert r.status_code==201;id_=r.json()['id']
    assert owner.put('/v1/pilot/consent',json={'accepted':True,'version':'pilot-v1'}).status_code==200
    body={'status':'not_started','duration_seconds':0,'errors':0,'assistance':0,'difficulty':0,'feedback':'Synthetic contract fixture, not actual participation'}
    for number in range(1,6):assert owner.put(f'/v1/pilot/tasks/{number}',json=body).status_code==200
    endpoint=f'/v1/admin/pilot/participants/{id_}/review-trial'
    assert owner.post(endpoint,json={'actual_participation_attested':True}).status_code==409
    attempted={**body,'status':'failed','duration_seconds':30,'errors':1,'difficulty':4}
    assert owner.put('/v1/pilot/tasks/1',json=attempted).status_code==200
    assert owner.post(endpoint,json={'actual_participation_attested':True}).status_code==200
    assert owner.get('/v1/admin/pilot/report').json()['operator_attested_real_trials']==1
    assert owner.put('/v1/pilot/tasks/1',json={**attempted,'errors':2}).status_code==200
    assert owner.get('/v1/admin/pilot/report').json()['operator_attested_real_trials']==0


def test_operator_can_honor_deletion_for_a_disabled_participant(owner):
    enroll(owner)
    with TestClient(app,headers={'Origin':'http://localhost:3000'}) as person:
        email='synthetic-disabled-study@example.com'
        assert person.post('/v1/auth/register',json={'email':email,'password':'synthetic-disabled-password'}).status_code==201
        r=owner.post('/v1/admin/pilot/participants',json={'email':email,'cohort':'engineering_qa','authorization_obtained':True,'authorization_reference':'Synthetic deletion contract only'})
        id_=r.json()['id'];assert person.put('/v1/pilot/consent',json={'accepted':True,'version':'pilot-v1'}).status_code==200
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.email==email));user.disabled=True;db.commit()
        assert person.delete('/v1/pilot/me').status_code==401
        assert owner.delete(f'/v1/admin/pilot/participants/{id_}').status_code==200
        with SessionLocal() as db:
            assert db.get(PilotParticipant,id_) is None
            assert db.scalar(select(User).where(User.email==email)).disabled
