"""Opt-in pilot records. No document/question/credential payload enters analytics."""
import hashlib
import math
import re
import time
import uuid
from collections import Counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select, update, func
from .db import get_db, SessionLocal
from .models import User, Project, PilotParticipant, PilotEvent, PilotTask, PilotIssue, PilotDeployment, PilotOperatorState
from .security import current_user, rate_limit
from .ops import admin

router = APIRouter(tags=["Private developer pilot"])
CONSENT_VERSION = "pilot-v1"
RETENTION_DAYS = 30
EVENT_CAP = 10000
STAGES = ("account_activation", "project_created", "document_uploaded", "document_indexed", "first_cited_answer", "api_key_created", "external_api_query", "standalone_exported", "independent_startup", "standalone_cited_query")
KINDS = set(STAGES) | {"query_completed", "upload_failed", "processing_failed", "retrieval_error", "quota_error", "export_failed"}
CATEGORIES = Literal["security", "data_loss", "retrieval", "api", "export", "setup", "performance", "ux", "feature"]
CHECKS = ("permitted_data_explained", "retention_and_deletion", "private_network", "trusted_tls", "firewall_verified", "backup_restore_verified", "alerts_verified", "credentials_rotated", "paid_providers_disabled")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


def purge(db):
    """Called by worker every minute and pilot reads; expired rows cascade entirely."""
    from .quotas import lock_owner
    expired = list(db.execute(select(PilotParticipant.id, PilotParticipant.user_id).where(PilotParticipant.expires_at <= time.time()).order_by(PilotParticipant.user_id)).all())
    for id_, user_id in expired:
        lock_owner(db, user_id)
        row = db.scalar(select(PilotParticipant).where(PilotParticipant.id == id_, PilotParticipant.expires_at <= time.time()).with_for_update())
        if row:
            erase_children(db, id_); db.delete(row)


def participant(db, user_id, *, require_consent=False, lock=False):
    now = time.time()
    filters = [PilotParticipant.user_id == user_id, PilotParticipant.expires_at > now]
    if require_consent:
        filters.append(PilotParticipant.consented_at.is_not(None))
    if lock:
        # Load the current row directly from UPDATE RETURNING. populate_existing
        # replaces a stale pre-lock identity-map snapshot without a second SELECT.
        statement=update(PilotParticipant).where(*filters).values(lock_epoch=PilotParticipant.lock_epoch+1).returning(PilotParticipant)
        return db.scalar(select(PilotParticipant).from_statement(statement).execution_options(populate_existing=True))
    return db.scalar(select(PilotParticipant).where(*filters))


def emit(db, user_id, kind, entity, elapsed_ms=None):
    """Server-only, transactionally published and deduplicated. Caller commits."""
    return bool(emit_batch(db, user_id, [(kind, entity, elapsed_ms)]))


def emit_batch(db, user_id, events):
    if any(kind not in KINDS for kind, _, _ in events):
        raise ValueError('Unknown pilot event')
    if not participant(db, user_id, require_consent=True):
        return 0
    row = participant(db, user_id, require_consent=True, lock=True)
    if not row or row.event_count >= EVENT_CAP:
        return 0
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    values = []
    for kind, entity, elapsed_ms in events[:max(0, EVENT_CAP - row.event_count)]:
        if elapsed_ms is not None and (not math.isfinite(elapsed_ms) or not 0 <= elapsed_ms <= 86400000):
            raise ValueError('Invalid technical timing')
        values.append(dict(id=str(uuid.uuid4()), participant_id=row.id, kind=kind, entity_hash=hashlib.sha256((row.id + ':' + str(entity)).encode()).hexdigest(), observed_at=time.time(), elapsed_ms=elapsed_ms))
    inserted = list(db.scalars(insert(PilotEvent).values(values).on_conflict_do_nothing(index_elements=[PilotEvent.participant_id, PilotEvent.kind, PilotEvent.entity_hash]).returning(PilotEvent.id)))
    row.event_count += len(inserted)
    return len(inserted)


def record_http_failure(*args):
    try:
        _record_http_failure(*args)
    except Exception:
        __import__('logging').getLogger('ragforge.pilot').warning('pilot_event_unavailable')


def _record_http_failure(user_id, route, status, request_id, quota=False, identity=None):
    if route.startswith('/v1/public/'):
        return  # Public-widget visitors are not opted-in study participants.
    if not user_id and identity:
        from .models import LoginSession, APIKey
        with SessionLocal() as db:
            account = None
            if identity.get('session'):
                login = db.get(LoginSession, identity['session'])
                if login and login.expires_at > time.time():
                    account = db.get(User, login.user_id)
            elif identity.get('key') and identity.get('project_id'):
                key = db.scalar(select(APIKey).where(APIKey.token_hash == identity['key'], APIKey.project_id == identity['project_id']))
                if key and (key.expires_at is None or key.expires_at > time.time()):
                    project = db.get(Project, key.project_id)
                    account = db.get(User, project.owner_id) if project else None
            if account and not account.disabled:
                user_id = account.id
    if not user_id:
        return
    kinds = []
    if route.endswith("/documents") and status >= 400:
        kinds.append("upload_failed")
    if quota or status in (413, 429):
        kinds.append("quota_error")
    if route.endswith(("/query", "/query/stream")) and status >= 500:
        kinds.append("retrieval_error")
    if kinds:
        try:
            with SessionLocal() as db:
                for kind in kinds:
                    emit(db, user_id, kind, request_id)
                db.commit()
        except Exception:
            __import__('logging').getLogger('ragforge.pilot').warning('pilot_event_unavailable')


def erase_children(db, id_):
    from .models import ExportJob
    from .exports import expire
    export_ids = list(db.scalars(select(PilotDeployment.export_id).where(PilotDeployment.participant_id == id_)))
    for job in db.scalars(select(ExportJob).where(ExportJob.id.in_(export_ids)).with_for_update()):
        if 'pilot_evidence' in job.config:
            expire(job)
            job.config = {k: v for k, v in job.config.items() if k != 'pilot_evidence'}
    for model in (PilotEvent, PilotTask, PilotIssue, PilotDeployment):
        db.execute(delete(model).where(model.participant_id == id_))


def own(db, user, consent=True):
    row = participant(db, user.id, require_consent=consent, lock=True)
    if not row:
        raise HTTPException(403, "Operator enrollment and current pilot consent are required")
    return row


def task_dict(t, private=False):
    result = {k: getattr(t, k) for k in ("task_number", "status", "duration_seconds", "errors", "assistance", "difficulty", "updated_at")}
    if private:
        result["feedback"] = t.feedback
    result['difficulty_recorded'] = t.difficulty != 0
    return result


def funnel(db, row):
    first = dict(db.execute(select(PilotEvent.kind, func.min(PilotEvent.observed_at)).where(PilotEvent.participant_id == row.id).group_by(PilotEvent.kind)).all())
    activated = first.get("account_activation")
    account = db.get(User, row.user_id) if activated is not None else None
    duration = lambda stage: round(first[stage] - activated, 3) if activated is not None and stage in first else None
    from_account = lambda stage: round(first[stage]-account.created_at,3) if account and stage in first else None
    return {"stages": [{"stage": stage, "completed": stage in first, "observed_at": first.get(stage)} for stage in STAGES], "time_to_first_cited_answer_seconds": duration("first_cited_answer"), "time_to_observed_standalone_deployment_seconds": duration("independent_startup"), "time_from_account_creation_to_first_cited_answer_seconds": from_account('first_cited_answer'), "time_from_account_creation_to_observed_deployment_seconds": from_account('independent_startup'), "time_basis": "Primary intervals start at opt-in study activation. Separate account-creation intervals use the existing server signup timestamp only after consent. Deployment includes offline evidence-import delay; other prior activity is not backfilled."}


@router.get('/v1/pilot/me')
def me(user=Depends(current_user), db=Depends(get_db)):
    purge(db); db.commit()
    row = participant(db, user.id)
    result = {"enrolled": bool(row), "collection_default": "off", "consent_version": CONSENT_VERSION, "retention_days": RETENTION_DAYS, "notice": "Optional technical stages/timings and submitted feedback; no document contents, questions or credentials in analytics. Separately labeled signup-time intervals use the existing account timestamp only after consent. Feedback is private to operators. Withdraw to erase pilot records; normal app use continues. Exports never call home."}
    if row:
        result.update(participant_id=row.id, cohort=row.cohort, consented_at=row.consented_at, expires_at=row.expires_at, funnel=funnel(db, row), tasks=[task_dict(t, True) for t in db.scalars(select(PilotTask).where(PilotTask.participant_id == row.id))])
    return result


class Consent(Input):
    accepted: bool
    version: Literal['pilot-v1']


@router.put('/v1/pilot/consent')
def consent(body: Consent, user=Depends(current_user), db=Depends(get_db)):
    from .quotas import lock_owner
    lock_owner(db, user.id)
    row = own(db, user, False)
    if body.accepted:
        if row.consented_at is None:
            row.consented_at = time.time(); row.consent_version = CONSENT_VERSION
            row.expires_at = time.time() + RETENTION_DAYS * 86400
            db.flush(); emit(db, user.id, 'account_activation', 'activation')
    else:
        erase_children(db, row.id)
        row.consented_at = row.consent_version = row.trial_reviewed_at = row.trial_reviewed_by = None
        row.event_count = 0
    db.commit()
    return {"consented": body.accepted, "prior_activity_backfilled": False}


@router.delete('/v1/pilot/me')
def delete_pilot(user=Depends(current_user), db=Depends(get_db)):
    from .quotas import lock_owner
    lock_owner(db, user.id)
    row = participant(db, user.id, lock=True)
    if row:
        erase_children(db, row.id)
        db.delete(row)
    db.commit()
    return {"deleted": True, "scope": "All live pilot enrollment, telemetry, feedback, issues and evidence. Application projects remain. Encrypted backup copies age out under operator retention."}


class TaskInput(Input):
    status: Literal['completed', 'failed', 'abandoned', 'not_started']
    duration_seconds: int = Field(ge=0, le=86400)
    errors: int = Field(ge=0, le=1000)
    assistance: int = Field(ge=0, le=1000)
    difficulty: int = Field(ge=0, le=5)
    feedback: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def attempted_rating(self):
        if self.status != 'not_started' and self.difficulty == 0:
            raise ValueError('Choose a difficulty rating from 1 to 5 for an attempted task')
        return self


@router.put('/v1/pilot/tasks/{number}')
def task(number: int, body: TaskInput, user=Depends(current_user), db=Depends(get_db)):
    if number not in range(1, 6):
        raise HTTPException(422, 'Task number must be 1 through 5')
    row = own(db, user); rate_limit(db, 'pilot-feedback:' + user.id, 30)
    # Reacquire after rate_limit's commit so withdrawal cannot race a submission.
    row = own(db, user)
    entry = db.scalar(select(PilotTask).where(PilotTask.participant_id == row.id, PilotTask.task_number == number))
    if not entry:
        entry = PilotTask(participant_id=row.id, task_number=number); db.add(entry)
    for name, value in body.model_dump().items():
        setattr(entry, name, value)
    entry.updated_at = time.time()
    row.trial_reviewed_at = row.trial_reviewed_by = None
    db.commit()
    return {"saved": True, "outcome_source": "participant_self_report", "technical_completion_inferred": False}


class IssueInput(Input):
    category: CATEGORIES
    description: str = Field(min_length=5, max_length=2000)


@router.post('/v1/pilot/issues', status_code=201)
def issue(body: IssueInput, user=Depends(current_user), db=Depends(get_db)):
    row = own(db, user)
    rate_limit(db, 'pilot-feedback:' + user.id, 30); row = own(db, user)
    count = db.scalar(select(func.count()).select_from(PilotIssue).where(PilotIssue.participant_id == row.id))
    if count >= 50:
        raise HTTPException(429, 'Pilot report limit reached; contact the incident owner privately')
    entry = PilotIssue(participant_id=row.id, **body.model_dump()); db.add(entry); db.commit()
    return {"id": entry.id, "status": entry.status, "published": False}


class Enrollment(Input):
    email: str = Field(max_length=254)
    cohort: Literal['human', 'engineering_qa']
    authorization_obtained: Literal[True]
    authorization_reference: str = Field(min_length=3, max_length=100)


@router.post('/v1/admin/pilot/participants', status_code=201)
def enroll(body: Enrollment, operator=Depends(admin), db=Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower(), User.disabled == False))
    if not user:
        raise HTTPException(404, 'Existing active account required; this action sends no invitation')
    purge(db)
    from .quotas import lock_owner
    lock_owner(db, user.id)
    if db.scalar(select(PilotParticipant).where(PilotParticipant.user_id == user.id)):
        raise HTTPException(409, 'Account already enrolled')
    row = PilotParticipant(user_id=user.id, cohort=body.cohort, authorized_by=operator.id, authorization_reference=body.authorization_reference, expires_at=time.time() + RETENTION_DAYS * 86400)
    db.add(row); db.commit()
    return {"id": row.id, "cohort": row.cohort, "consent_required": True, "invitation_sent": False}


@router.get('/v1/admin/pilot/report')
def report(cohort: Literal['human', 'engineering_qa'] = 'human', operator=Depends(admin), db=Depends(get_db)):
    purge(db); db.commit()
    rows = list(db.scalars(select(PilotParticipant).where(PilotParticipant.cohort == cohort)))
    ids = [r.id for r in rows]
    counts = dict(db.execute(select(PilotEvent.kind, func.count()).where(PilotEvent.participant_id.in_(ids)).group_by(PilotEvent.kind)).all())
    timings = sorted(db.scalars(select(PilotEvent.elapsed_ms).where(PilotEvent.participant_id.in_(ids), PilotEvent.kind == 'query_completed', PilotEvent.elapsed_ms.is_not(None))))
    issues = list(db.scalars(select(PilotIssue).where(PilotIssue.participant_id.in_(ids))))
    participants = [{"participant_id": r.id, "consented_at": r.consented_at, "expires_at": r.expires_at, "event_cap_reached": r.event_count >= EVENT_CAP, "trial_reviewed_at": r.trial_reviewed_at, **funnel(db, r), "reported_tasks": [task_dict(t) for t in db.scalars(select(PilotTask).where(PilotTask.participant_id == r.id))]} for r in rows]
    return {"schema_version": 1, "cohort": cohort, "technical_events": counts, "activated_participants": sum(r.consented_at is not None for r in rows), "operator_attested_real_trials": sum(r.trial_reviewed_at is not None for r in rows) if cohort == 'human' else 0, "query_latency_ms": {"count": len(timings), "median": __import__('statistics').median(timings) if timings else None, "p95": timings[math.ceil(len(timings) * .95) - 1] if timings else None, "scope": "Answer service before API response/transport overhead"}, "reported_problems": dict(Counter(i.category for i in issues)), "issues": [{"id": i.id, "category": i.category, "severity": i.severity, "status": i.status} for i in issues], "participants": participants, "redaction": "Pseudonymous IDs and numeric/enum outcomes only. No email, authorization reference, content, questions, credentials or free-text feedback. Engineering QA excluded from human cohort. Never publish without authorization."}


@router.get('/v1/admin/pilot/participants/{id_}/feedback')
def private_feedback(id_: str, operator=Depends(admin), db=Depends(get_db)):
    row = db.get(PilotParticipant, id_)
    if not row or row.expires_at <= time.time():
        raise HTTPException(404, 'Participant not found')
    return {"participant_id": id_, "tasks": [task_dict(t, True) for t in db.scalars(select(PilotTask).where(PilotTask.participant_id == id_))], "issues": [{k: getattr(i, k) for k in ('id', 'category', 'severity', 'status', 'description', 'sanitized_reproduction', 'engineering_reference', 'export_approved')} for i in db.scalars(select(PilotIssue).where(PilotIssue.participant_id == id_))], "private": True}


@router.delete('/v1/admin/pilot/participants/{id_}')
def operator_delete_participant(id_: str, operator=Depends(admin), db=Depends(get_db)):
    from .quotas import lock_owner
    row=db.get(PilotParticipant,id_)
    if row:
        lock_owner(db,row.user_id)
        row=db.scalar(select(PilotParticipant).where(PilotParticipant.id==id_).with_for_update())
        if row:
            erase_children(db,id_);db.delete(row)
    db.commit()
    return {'deleted':True,'scope':'Pilot study records only; normal projects and account access remain separate'}


class IssueReview(Input):
    severity: Literal['critical', 'high', 'medium', 'low']
    status: Literal['new', 'investigating', 'scheduled', 'resolved', 'closed']
    sanitized_reproduction: str = Field(default='', max_length=2000)
    engineering_reference: str = Field(default='', max_length=150, pattern=r'^[A-Za-z0-9_/# .-]*$')
    export_approved: bool = False


@router.put('/v1/admin/pilot/issues/{id_}')
def review_issue(id_: str, body: IssueReview, operator=Depends(admin), db=Depends(get_db)):
    row = db.scalar(select(PilotIssue).join(PilotParticipant).where(PilotIssue.id==id_,PilotParticipant.expires_at>time.time(),PilotParticipant.consented_at.is_not(None)))
    if not row:
        raise HTTPException(404, 'Issue not found')
    if body.export_approved and (not body.sanitized_reproduction.strip() or re.search(r'(?:rf_|sa_|sk-|github_pat_|ghp_)[A-Za-z0-9_-]{16,}|password\s*[:=]|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', body.sanitized_reproduction, re.I)):
        raise HTTPException(422, 'Provide an operator-reviewed reproduction without credentials or email addresses')
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.reviewed_by = operator.id; row.reviewed_at = time.time(); db.commit()
    return {"reviewed": True, "published": False}


@router.get('/v1/admin/pilot/issues/{id_}/export')
def issue_export(id_: str, operator=Depends(admin), db=Depends(get_db)):
    row = db.scalar(select(PilotIssue).join(PilotParticipant).where(PilotIssue.id==id_,PilotParticipant.expires_at>time.time(),PilotParticipant.consented_at.is_not(None)))
    if not row or not row.export_approved:
        raise HTTPException(409, 'An operator must review and approve sanitized text first')
    return {"schema_version": 1, "category": row.category, "severity": row.severity, "status": row.status, "reproduction": row.sanitized_reproduction, "source": "operator_reviewed_private_report", "notice": "Download only. Independently review for private content before any authorized issue creation."}


class TrialReview(Input):
    actual_participation_attested: Literal[True]


@router.post('/v1/admin/pilot/participants/{id_}/review-trial')
def review_trial(id_: str, body: TrialReview, operator=Depends(admin), db=Depends(get_db)):
    row = db.scalar(select(PilotParticipant).where(PilotParticipant.id == id_, PilotParticipant.expires_at > time.time()).with_for_update())
    if not row or row.cohort != 'human' or row.consented_at is None:
        raise HTTPException(409, 'A consenting real-participant cohort is required')
    if db.scalar(select(func.count()).select_from(PilotTask).where(PilotTask.participant_id == id_)) != 5:
        raise HTTPException(409, 'Record all five task outcomes, including failures/incomplete tasks, before human trial review')
    if not db.scalar(select(PilotTask.id).where(PilotTask.participant_id==id_,PilotTask.status!='not_started').limit(1)):
        raise HTTPException(409,'Record an actual task attempt, including a failed/abandoned setup, before attesting a trial')
    row.trial_reviewed_at = time.time(); row.trial_reviewed_by = operator.id; db.commit()
    return {"reviewed": True, "basis": "Operator attestation of actual participation; never inferred from technical events"}


class OperatorInput(Input):
    checklist: dict[str, bool]
    incident_owner: str = Field(max_length=100)
    user_authorization_reference: str = Field(default='', max_length=100)


@router.get('/v1/admin/pilot/operator-state')
def get_operator_state(operator=Depends(admin), db=Depends(get_db)):
    row = db.get(PilotOperatorState, 'pilot')
    return {'checklist': {k: row.checklist.get(k, False) if row else False for k in CHECKS}, 'incident_owner': row.incident_owner if row else '', 'user_authorization_reference': row.checklist.get('user_authorization_reference', '') if row else ''}


def deployment_ticket(db, user_id, export_id, template_sha256):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import secrets
    member = participant(db, user_id, require_consent=True, lock=True)
    if not member:
        raise HTTPException(403, 'Current pilot consent is required for optional offline deployment evidence')
    db.execute(delete(PilotDeployment).where(PilotDeployment.participant_id==member.id,PilotDeployment.expires_at<=time.time()))
    if db.scalar(select(func.count()).select_from(PilotDeployment).where(PilotDeployment.participant_id==member.id)) >= 50:
        raise HTTPException(429, 'Pilot deployment evidence quota reached; wait for ticket expiry or withdraw/delete study data')
    key = Ed25519PrivateKey.generate()
    row = PilotDeployment(id=str(uuid.uuid4()), participant_id=member.id, export_id=export_id, template_sha256=template_sha256, public_key=key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex(), challenge=secrets.token_hex(32), issued_at=time.time(), expires_at=min(member.expires_at, time.time() + 7 * 86400))
    db.add(row)
    return {"deployment_id": row.id, "export_id": export_id, "template_sha256": template_sha256, "challenge": row.challenge, "expires_at": row.expires_at, "private_key_hex": key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()).hex()}


class RuntimePayload(Input):
    version: Literal[1]
    deployment_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    export_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    template_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    challenge: str = Field(pattern=r'^[a-f0-9]{64}$')
    boot_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    started_at: float = Field(gt=0, allow_inf_nan=False)
    cited_query_at: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    database_ready: Literal[True]


class RuntimeEvidence(Input):
    payload: RuntimePayload
    signature: str = Field(pattern=r'^[a-f0-9]{128}$')


@router.post('/v1/pilot/deployment-evidence')
def import_runtime_evidence(body: RuntimeEvidence, user=Depends(current_user), db=Depends(get_db)):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    import json
    member = own(db, user)
    row = db.scalar(select(PilotDeployment).where(PilotDeployment.id == body.payload.deployment_id, PilotDeployment.participant_id == member.id).with_for_update())
    if not row:
        raise HTTPException(404, 'Evidence ticket not found')
    now = time.time()
    if row.expires_at <= now:
        raise HTTPException(410, 'Deployment evidence ticket expired; generate a new opted-in export')
    payload = body.payload.model_dump()
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(row.public_key)).verify(bytes.fromhex(body.signature), encoded)
    except (ValueError, InvalidSignature):
        raise HTTPException(422, 'Invalid runtime evidence signature') from None
    if payload['challenge'] != row.challenge or payload['export_id'] != row.export_id or payload['template_sha256'] != row.template_sha256:
        raise HTTPException(422, 'Evidence does not match the issued export challenge')
    if not row.issued_at - 300 <= payload['started_at'] <= now + 300 or payload['cited_query_at'] is not None and not payload['started_at'] <= payload['cited_query_at'] <= now + 300:
        raise HTTPException(422, 'Runtime clock/evidence timestamps are outside the allowed interval')
    proof_hash = hashlib.sha256(encoded + body.signature.encode()).hexdigest()
    duplicate = row.proof_sha256 == proof_hash
    if row.received_at is None:
        row.received_at = now
        emit(db, user.id, 'independent_startup', row.id)
    if payload['cited_query_at'] is not None and row.query_received_at is None:
        row.query_received_at = now
        emit(db, user.id, 'standalone_cited_query', row.id)
    row.proof_sha256 = proof_hash
    db.commit()
    return {"accepted": True, "duplicate": duplicate, "startup_observed_at": row.received_at, "cited_query_observed_at": row.query_received_at, "evidence_class": "Signed self-hosted runtime evidence, not remote attestation or proof of human participation"}


@router.put('/v1/admin/pilot/operator-state')
def operator_state(body: OperatorInput, operator=Depends(admin), db=Depends(get_db)):
    if set(body.checklist) != set(CHECKS):
        raise HTTPException(422, 'Provide every documented operator checklist field')
    row = db.get(PilotOperatorState, 'pilot')
    if not row:
        row = PilotOperatorState(id='pilot'); db.add(row)
    row.checklist = {**body.checklist, 'user_authorization_reference': body.user_authorization_reference}
    row.incident_owner = body.incident_owner; row.updated_by = operator.id; row.updated_at = time.time(); db.commit()
    return {"recorded": True, "basis": "Operator attestation; no network, invite or public deployment action performed"}


@router.get('/v1/admin/pilot/readiness')
def pilot_readiness(operator=Depends(admin), db=Depends(get_db)):
    from .ops import readiness
    row = db.get(PilotOperatorState, 'pilot')
    checks = row.checklist if row else {}
    human = list(db.scalars(select(PilotParticipant).where(PilotParticipant.cohort == 'human', PilotParticipant.expires_at > time.time())))
    return {"engineering_runtime": readiness(db), "engineering_release_checks": "See versioned M5 CI/installation/performance receipts; runtime readiness alone is not full acceptance.", "operator_configuration": {"completed": bool(row and row.incident_owner.strip() and all(checks.get(k) is True for k in CHECKS)), "checks": {k: checks.get(k, False) for k in CHECKS}, "incident_owner_recorded": bool(row and row.incident_owner.strip())}, "external_access_authorization": {"recorded": bool(checks.get('user_authorization_reference')), "basis": "Operator-recorded user authorization, not an automatic grant"}, "human_evaluation": {"status": "Separate explicit label review/import required; no score inferred from activity"}, "actual_participant_trials": {"operator_attested_count": sum(p.trial_reviewed_at is not None for p in human), "technical_qa_counts_as_trial": False}, "external_phase": "pending_human_action" if not human or not any(p.trial_reviewed_at for p in human) else "operator_recorded_trials_require_review"}
