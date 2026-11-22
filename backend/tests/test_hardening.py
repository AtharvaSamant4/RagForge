import hashlib
import io
import json
import logging
import os
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal,engine
from app.main import app
from app.models import User,Invite,LoginSession,APIKey,Document,ProviderUsage
from app.security import digest,password_hash
from app.parse_isolation import execute_parser
from app.ingestion import ExtractionError
from app.provider_budget import reserve_hosted
from app.embeddings import EmbeddingError
from app.backup_crypto import encrypt,decrypt
from app.logging_config import JSONFormatter
from test_workflow import ingest


def test_invites_single_use_expiry_revocation_and_disabled_registration(client,monkeypatch):
    monkeypatch.setattr(settings(),'registration_mode','invite')
    monkeypatch.setattr(settings(),'allow_registration',False)
    with SessionLocal() as db:
        admin=User(email='operator@example.com',password_hash=password_hash('operator-test-password'),is_admin=True)
        db.add(admin);db.flush()
        for raw,ttl,revoked in [('valid',60,False),('expired',-1,False),('revoked',60,True)]:db.add(Invite(token_hash=digest(raw),created_by=admin.id,expires_at=time.time()+ttl,revoked=revoked))
        db.commit()
    credentials={'email':'new@example.com','password':'private-alpha-test-password'}
    for token in [None,'wrong','expired','revoked']:
        assert client.post('/v1/auth/register',json={**credentials,'invite_token':token}).status_code==403
    assert client.post('/v1/auth/register',json={**credentials,'invite_token':'valid'}).status_code==201
    assert client.post('/v1/auth/register',json={**credentials,'email':'another@example.com','invite_token':'valid'}).status_code==403
    monkeypatch.setattr(settings(),'registration_mode','disabled')
    assert client.post('/v1/auth/register',json=credentials).status_code==403


def test_diagnostics_admin_only_keys_expire_and_disabled_users_lose_access(owner,project):
    base='/v1/projects/'+project['id']
    assert owner.get('/v1/admin/diagnostics').status_code==403
    with SessionLocal() as db:
        user=db.scalar(select(User));user.is_admin=True;db.commit()
    response=owner.post('/v1/admin/invites',json={});assert response.status_code==200
    assert owner.delete('/v1/admin/invites/'+response.json()['id']).status_code==200
    assert owner.get('/v1/admin/diagnostics').status_code==200
    result=owner.post(base+'/keys',json={'name':'expiry'}).json();raw=result['secret']
    assert owner.get('/v1/admin/diagnostics',headers={'Authorization':'Bearer '+raw}).status_code==403
    with SessionLocal() as db:
        key=db.get(APIKey,result['id']);key.expires_at=time.time()-1;db.commit()
    assert owner.get(base+'/status',headers={'Authorization':'Bearer '+raw}).status_code==401
    with SessionLocal() as db:
        user=db.scalar(select(User));user.disabled=True;db.commit()
    assert owner.get('/v1/projects').status_code==401


def test_storage_document_and_job_limits_enforced(owner,project,monkeypatch):
    s=settings();base='/v1/projects/'+project['id']
    monkeypatch.setattr(s,'user_storage_mb',0)
    assert owner.post(base+'/documents',files={'file':('x.txt',b'Valid source')}).status_code==413
    monkeypatch.setattr(s,'user_storage_mb',1)
    monkeypatch.setattr(s,'max_ingestion_jobs_per_user',1)
    assert owner.post(base+'/documents',files={'file':('x.txt',b'Valid source')}).status_code==202
    assert owner.post(base+'/documents',files={'file':('y.txt',b'Valid source')}).status_code==429
    monkeypatch.setattr(s,'max_documents_per_project',1)
    assert owner.post(base+'/documents',files={'file':('y.txt',b'Valid source')}).status_code==409
    monkeypatch.setattr(s,'user_storage_mb',512)
    monkeypatch.setattr(s,'max_export_jobs_per_user',1)
    assert owner.post(base+'/exports',json={}).status_code==202
    other=owner.post('/v1/projects',json={'name':'second'}).json()
    assert owner.post('/v1/projects/'+other['id']+'/exports',json={}).status_code==429


def test_provider_budget_atomic_under_concurrency(monkeypatch):
    monkeypatch.setattr(settings(),'hosted_daily_requests',3)
    monkeypatch.setattr(settings(),'hosted_daily_input_chars',100)
    def reserve(_):
        try:reserve_hosted(20);return True
        except EmbeddingError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,range(10)))
    assert sum(results)==3
    with SessionLocal() as db:
        row=db.scalar(select(ProviderUsage));assert row.requests==3 and row.input_chars==60


def test_parser_time_memory_and_cpu_limits(monkeypatch):
    s=settings()
    monkeypatch.setattr(s,'parser_wall_seconds',2)
    started=time.monotonic()
    with pytest.raises(ExtractionError,match='execution-time'):execute_parser(b'Test','txt',probe='timeout')
    assert time.monotonic()-started<6
    monkeypatch.setattr(s,'parser_wall_seconds',8)
    monkeypatch.setattr(s,'parser_cpu_seconds',1)
    with pytest.raises(ExtractionError):execute_parser(b'Test','txt',probe='cpu')
    monkeypatch.setattr(s,'parser_cpu_seconds',5)
    monkeypatch.setattr(s,'parser_memory_mb',128)
    with pytest.raises(ExtractionError):execute_parser(b'Test','txt',probe='memory')
    assert execute_parser(b'The worker still processes valid sources.','txt')['sections']


@pytest.mark.skipif(__import__('sys').platform!='linux',reason='Linux Landlock/seccomp boundary; Windows has resource Job Objects')
def test_linux_parser_cannot_read_other_files_open_network_or_spawn(monkeypatch,tmp_path):
    monkeypatch.setattr(settings(),'parser_require_sandbox',True)
    outside=tmp_path/'secret.txt';outside.write_text('private-control-secret')
    result=execute_parser(b'Test','txt',probe='boundaries',outside=str(outside))
    assert result['blocked']=={'outside_file':True,'network':True,'process':True}
    assert result['restrictions']['filesystem']=='landlock'


def test_backup_encryption_integrity_and_authentication_before_use(tmp_path):
    source=tmp_path/'plain';source.write_bytes(b'private source and DB data'*1000)
    target=tmp_path/'encrypted';password='long-private-test-passphrase'
    encrypt(source,target,password)
    assert b'private source' not in target.read_bytes()
    restored=tmp_path/'restored';decrypt(target,restored,password);assert source.read_bytes()==restored.read_bytes()
    with pytest.raises(ValueError,match='authentication'):decrypt(target,tmp_path/'wrong','wrong-but-long-passphrase')
    assert not (tmp_path/'wrong').exists()
    data=bytearray(target.read_bytes());data[-30]^=1;target.write_bytes(data)
    with pytest.raises(ValueError,match='authentication'):decrypt(target,tmp_path/'tampered',password)
    assert not (tmp_path/'tampered').exists()


def test_sensitive_text_is_not_in_formatted_logs(owner,project):
    secret='PRIVATE-DOCUMENT-TOKEN-DO-NOT-LOG'
    record=logging.LogRecord('external.parser',logging.ERROR,'x',1,secret,(),None)
    formatted=JSONFormatter().format(record)
    assert secret not in formatted and 'external_log' in formatted
    record=logging.LogRecord('ragforge.api',logging.ERROR,'x',1,'request_failed',(),None)
    record.error_type='ValueError';record.request_id='request-test'
    assert 'request-test' in JSONFormatter().format(record)
    response=owner.get('/'+secret)
    assert response.status_code==404 and response.headers.get('X-Request-ID')
    too_long=secret*200
    response=owner.post('/v1/auth/register',json={'email':'validation@example.com','password':too_long})
    assert response.status_code==422 and secret not in response.text
    response=owner.post('/v1/projects/'+project['id']+'/query',json={'question':too_long})
    assert response.status_code==422 and secret not in response.text



def test_concurrent_upload_and_export_reservations_never_exceed_account_limits(owner,project,monkeypatch):
    from app.models import ExportJob
    from app.quotas import usage
    monkeypatch.setattr(settings(),'max_ingestion_jobs_per_user',2)
    cookies=dict(owner.cookies)
    base='/v1/projects/'+project['id']
    def upload(i):
        with TestClient(app,headers={'origin':'http://localhost:3000'},cookies=cookies) as c:
            return c.post(base+'/documents',files={'file':(f'source-{i}.txt',b'Bounded concurrent source.')}).status_code
    with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(upload,range(8)))
    assert results.count(202)==2 and results.count(429)==6,results
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Document))))==2
        assert usage(db,db.scalar(select(User.id)))['source_bytes']==2*len(b'Bounded concurrent source.')
    monkeypatch.setattr(settings(),'max_export_jobs_per_user',1)
    projects=[owner.post('/v1/projects',json={'name':f'Export {i}'}).json()['id'] for i in range(4)]
    def export(i):
        with TestClient(app,headers={'origin':'http://localhost:3000'},cookies=cookies) as c:return c.post('/v1/projects/'+i+'/exports',json={}).status_code
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(export,projects))
    assert results.count(202)==1 and results.count(429)==3,results
    with SessionLocal() as db:assert len(list(db.scalars(select(ExportJob))))==1


def test_concurrent_invite_redemption_has_exactly_one_winner(client,monkeypatch):
    monkeypatch.setattr(settings(),'registration_mode','invite')
    with SessionLocal() as db:
        admin=User(email='admin@example.com',password_hash='disabled',is_admin=True);db.add(admin);db.flush()
        db.add(Invite(token_hash=digest('single-use-concurrent-token'),created_by=admin.id,expires_at=time.time()+300));db.commit()
    def redeem(i):
        with TestClient(app,headers={'origin':'http://localhost:3000'}) as c:return c.post('/v1/auth/register',json={'email':f'claim-{i}@example.com','password':'concurrent-test-password','invite_token':'single-use-concurrent-token'}).status_code
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(redeem,range(3)))
    assert sorted(results)==[201,403,403]


def test_operator_rotation_revokes_sessions_and_project_keys(owner,project):
    import subprocess,sys
    result=owner.post('/v1/projects/'+project['id']+'/keys',json={'name':'rotation'}).json()
    password='rotated-private-operator-test-password'
    run=subprocess.run([sys.executable,'-m','app.ops','rotate-password','--email','owner@example.com','--password-stdin'],input=password+'\n',text=True,capture_output=True,timeout=40,env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])})
    assert run.returncode==0,run.stderr
    assert password not in run.stdout+run.stderr
    assert owner.get('/v1/projects').status_code==401
    assert owner.get('/v1/projects/'+project['id']+'/status',headers={'authorization':'Bearer '+result['secret']}).status_code==401
    assert owner.post('/v1/auth/login',json={'email':'owner@example.com','password':password}).status_code==200


def test_first_admin_initialization_is_serialized_and_never_prints_password():
    import subprocess,sys
    password='operator-bootstrap-fixture-password'
    def bootstrap(i):return subprocess.run([sys.executable,'-m','app.ops','bootstrap-admin','--email',f'first-{i}@example.com','--password-stdin'],input=password+'\n',text=True,capture_output=True,timeout=40,env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(bootstrap,range(2)))
    assert sum(r.returncode==0 for r in results)==1
    assert all(password not in r.stdout+r.stderr for r in results)
    with SessionLocal() as db:assert len(list(db.scalars(select(User).where(User.is_admin==True))))==1


def test_docx_bomb_encoding_and_corrupted_model_fail_closed(owner,project,monkeypatch,tmp_path):
    import zipfile
    from app.embeddings import model_files,REVISION
    base='/v1/projects/'+project['id']+'/documents'
    content=io.BytesIO()
    with zipfile.ZipFile(content,'w',compression=zipfile.ZIP_DEFLATED) as archive:archive.writestr('word/document.xml',b'A'*2_000_000)
    result=owner.post(base,files={'file':('bomb.docx',content.getvalue())})
    assert result.status_code==422 and 'compression ratio' in result.json()['detail']
    assert owner.post(base,files={'file':('bad.txt',b'\xff\xfeinvalid')}).status_code==422
    directory=tmp_path/'minilm'/REVISION;directory.mkdir(parents=True)
    (directory/'model.onnx').write_bytes(b'corrupted-untrusted-model')
    monkeypatch.setattr(settings(),'model_cache_dir',tmp_path)
    monkeypatch.setattr(settings(),'model_local_files_only',True)
    with pytest.raises(EmbeddingError,match='missing or corrupt'):model_files()


def test_private_alpha_rejects_insecure_startup_and_never_opens_default_registration(monkeypatch):
    s=settings()
    monkeypatch.setattr(s,'deployment_mode','private_alpha')
    monkeypatch.setattr(s,'cookie_secure',False)
    with pytest.raises(RuntimeError,match='HTTPS origins and secure cookies'):
        with TestClient(app):pass
    monkeypatch.setattr(s,'cookie_secure',True)
    monkeypatch.setattr(s,'app_origins','')
    with pytest.raises(RuntimeError,match='HTTPS origins and secure cookies'):
        with TestClient(app):pass
    monkeypatch.setattr(s,'app_origins','https://localhost:8443')
    monkeypatch.setattr(s,'registration_mode','development')
    with TestClient(app,headers={'origin':'https://localhost:8443'}) as c:
        assert c.get('/health').json()['registration_mode']=='disabled'
        assert c.post('/v1/auth/register',json={'email':'uninvited@example.com','password':'private-alpha-closed-test-password'}).status_code==403


def test_operator_widget_disable_blocks_previous_capability_and_frame_policy(owner,project,monkeypatch):
    base='/v1/projects/'+project['id']
    config={'enabled':True,'allowed_origins':['https://pilot.example']}
    r=owner.put(base+'/widget',json=config);assert r.status_code==200,r.text
    token=r.json()['token']
    monkeypatch.setattr(settings(),'allow_public_widgets',False)
    assert owner.put(base+'/widget',json=config).status_code==403
    for path in ['/config','/frame-policy']:
        assert owner.get('/v1/public/'+project['id']+path,headers={'authorization':'Bearer '+token}).status_code==404
    assert owner.post('/v1/public/'+project['id']+'/query',json={'question':'What is known?'},headers={'authorization':'Bearer '+token}).status_code==404


def test_partial_storage_write_failure_leaves_no_file_or_quota_reservation(owner,project,monkeypatch):
    from sqlalchemy import func
    store=settings().storage_dir
    before=set(store.iterdir())
    original=Path.open
    marker='PRIVATE-STORAGE-ERROR-NOT-FOR-CLIENTS'
    class FailingWriter:
        def __init__(self,file):self.file=file
        def __enter__(self):return self
        def write(self,data):
            self.file.write(data[:3])
            raise OSError(marker)
        def __exit__(self,*args):self.file.close()
    def opening(path,mode='r',*args,**kwargs):
        file=original(path,mode,*args,**kwargs)
        return FailingWriter(file) if mode=='xb' and path.parent==store else file
    monkeypatch.setattr(Path,'open',opening)
    result=owner.post('/v1/projects/'+project['id']+'/documents',files={'file':('partial.txt',b'Valid source bytes.')})
    assert result.status_code==500 and marker not in result.text
    assert set(store.iterdir())==before
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Document))==0


def test_delayed_rate_request_cannot_reopen_an_earlier_window(monkeypatch):
    from fastapi import HTTPException
    from app import security
    from app.models import RateBucket
    identity='rollover regression fixture'
    future=int(time.time()//60)+1
    with SessionLocal() as db:
        db.add(RateBucket(key=digest(identity),window=future,count=2));db.commit()
    monkeypatch.setattr(security.time,'time',lambda:future*60-1)
    with SessionLocal() as db,pytest.raises(HTTPException) as raised:security.rate_limit(db,identity,2)
    assert raised.value.status_code==429
    with SessionLocal() as db:
        row=db.get(RateBucket,digest(identity));assert row.window==future and row.count==3
    monkeypatch.setattr(security.time,'time',lambda:(future+1)*60+1)
    with SessionLocal() as db:security.rate_limit(db,identity,2)
    with SessionLocal() as db:
        row=db.get(RateBucket,digest(identity));assert row.window==future+1 and row.count==1
