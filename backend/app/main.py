import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .evaluation import generate_cases, run_evaluation
from .ingestion import ExtractionError, validate_file
from .logging_config import configure_logging
from .models import APIKey, Chunk, Conversation, Document, EvalCase, EvalRun, Job, LoginSession, Project, QueryRecord, User, Invite
from .providers import ProviderError, embedding_id
from .retrieval import answer
from .retrieval import retrieve
from .embeddings import profile, runtime_stats
from .indexing import index_status, require_compatible, storage_dimensions
from .schemas import CaseInput, Credentials, RegistrationInput, KeyInput, PipelineInput, ProjectInput, QueryInput, RunInput, WidgetInput
from .security import access, current_user, digest, password_hash, password_valid, rate_limit
from .worker import enqueue
from .quotas import lock_owner, allocate, usage as quota_usage

log = logging.getLogger("ragforge.api")
s = settings()


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    s.export_dir.mkdir(parents=True, exist_ok=True)
    if s.deployment_mode=='private_alpha' and (not s.cookie_secure or not s.origins or any(not origin.startswith('https://') for origin in s.origins)):
        raise RuntimeError('Private alpha requires HTTPS origins and secure cookies')
    yield


app = FastAPI(title=f"{s.brand_name} API", version="0.1.0", lifespan=lifespan)
from .exports import router as export_router
app.include_router(export_router)
from .ops import router as ops_router
app.include_router(ops_router)


class BodyLimit:
    def __init__(self, app):
        self.app = app
        import threading
        self.upload_slots=threading.BoundedSemaphore(4)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        maximum = (s.max_upload_mb * 1024 * 1024 + 1024 * 1024) if scope["path"].endswith("/documents") else 256 * 1024
        headers = dict(scope["headers"])
        try:
            size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            size = maximum + 1
        if not 0 <= size <= maximum:
            return await JSONResponse({"detail": "Request body exceeds the size limit"}, 413)(scope, receive, send)
        # Require a declared size for uploads to bound multipart parsing before disk spooling.
        if scope["method"] == "POST" and scope["path"].endswith("/documents") and b"content-length" not in headers:
            return await JSONResponse({"detail": "Content-Length is required for uploads"}, 411)(scope, receive, send)
        total = 0
        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > maximum:
                raise HTTPException(413, "Request body exceeds the size limit")
            return message
        upload=scope["method"]=="POST" and scope["path"].endswith("/documents")
        if upload and not self.upload_slots.acquire(blocking=False):
            return await JSONResponse({"detail":"Upload capacity reached; retry shortly"},429)(scope,receive,send)
        try:await self.app(scope, bounded_receive, send)
        finally:
            if upload:self.upload_slots.release()


app.add_middleware(BodyLimit)


@app.middleware("http")
async def safeguards(request: Request, call_next):
    start = time.perf_counter()
    request_id = str(uuid.uuid4())
    # Session-cookie state changes require a trusted browser Origin. CLI uses Bearer keys.
    try:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.url.path.startswith("/v1/public/") and not request.headers.get("authorization") and request.headers.get("origin", "").rstrip("/") not in s.origins:
            response = JSONResponse({"detail": "A trusted Origin header is required"}, 403)
        else:
            response = await call_next(request)
    except Exception as exc:
        log.error("request_failed", extra={"request_id": request_id, "error_type": type(exc).__name__})
        response = JSONResponse({"detail": "An internal error occurred", "request_id": request_id}, 500)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    route=getattr(request.scope.get('route'),'path','unmatched')
    elapsed=round((time.perf_counter()-start)*1000,2)
    from .observability import api_metric
    import anyio
    await anyio.to_thread.run_sync(api_metric,request.method,route,response.status_code,elapsed)
    log.info("request_completed", extra={"request_id": request_id, "method": request.method, "path": route, "status": response.status_code, "latency_ms": elapsed})
    return response


app.add_middleware(CORSMiddleware, allow_origins=s.origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization"])


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Pydantic's default errors echo input and context, including credentials/questions.
    return JSONResponse({"detail": [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in exc.errors()]}, 422)


@app.exception_handler(ProviderError)
async def provider_failure(request, exc):
    return JSONResponse({"detail": str(exc)}, 503)


def row_dict(row, fields):
    return {field: getattr(row, field) for field in fields.split()}


def project_dict(db, project):
    docs = list(db.scalars(select(Document).where(Document.project_id == project.id)))
    return {**row_dict(project, "id name description created_at pipeline pipeline_version"), "document_count": len(docs), "ready_count": sum(d.status == "ready" for d in docs), "chunk_count": sum(d.chunk_count for d in docs), "query_count": db.scalar(select(func.count()).select_from(QueryRecord).where(QueryRecord.project_id == project.id))}


def document_dict(doc):
    return row_dict(doc, "id project_id name kind sha256 size_bytes status error chunk_count metadata_json created_at")


def job_dict(job):
    return row_dict(job, "id document_id status attempts error created_at finished_at available_at pipeline_version")


def child(db, model, project_id, id_):
    row = db.scalar(select(model).where(model.id == id_, model.project_id == project_id))
    if not row:
        raise HTTPException(404, "Resource not found")
    return row


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    mode=s.registration_mode if s.registration_mode!='development' or s.deployment_mode=='development' else 'disabled'
    return {"status": "ok", "brand": s.brand_name, "embedding_provider": s.embedding_provider, "embedding_profile": profile(), "embedding_runtime": runtime_stats(), "generation_provider": s.generation_provider, "registration_enabled": mode=='invite' or (mode=='development' and s.allow_registration),"registration_mode":mode}


def login_response(db, user, response):
    raw = secrets.token_urlsafe(32)
    db.execute(delete(LoginSession).where(LoginSession.expires_at < time.time()))
    db.add(LoginSession(token_hash=digest(raw), user_id=user.id, expires_at=time.time()+s.session_ttl_seconds))
    db.commit()
    response.set_cookie("ragforge_session", raw, httponly=True, secure=s.cookie_secure, samesite="strict", max_age=s.session_ttl_seconds, path="/")
    return {"id": user.id, "email": user.email,"is_admin":user.is_admin}


@app.post("/v1/auth/register", status_code=201)
def register(body: RegistrationInput, request: Request, response: Response, db: Session = Depends(get_db)):
    mode=health(db)['registration_mode']
    if mode=='disabled' or (mode=='development' and not s.allow_registration):
        raise HTTPException(403, "Registration is disabled")
    rate_limit(db, "auth:" + (request.client.host if request.client else "unknown"), 15)
    user = User(id=str(uuid.uuid4()),email=body.email, password_hash=password_hash(body.password))
    if mode=='invite':
        from sqlalchemy import update
        claimed=db.scalar(update(Invite).where(Invite.token_hash==digest(body.invite_token or ''),Invite.revoked==False,Invite.redeemed_by.is_(None),Invite.expires_at>time.time()).values(redeemed_by=user.id).returning(Invite.id))
        if not claimed:raise HTTPException(403,'A valid, unused invitation is required')
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with that email already exists") from None
    return login_response(db, user, response)


@app.post("/v1/auth/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(db, "auth:" + (request.client.host if request.client else "unknown"), 15)
    user = db.scalar(select(User).where(User.email == body.email))
    # Equal-cost check prevents trivial account enumeration through timing.
    encoded = user.password_hash if user else "pbkdf2:600000:" + "00"*16 + ":" + "00"*32
    if not password_valid(body.password, encoded) or not user or user.disabled:
        raise HTTPException(401, "Email or password is incorrect")
    return login_response(db, user, response)


@app.get("/v1/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email,"is_admin":user.is_admin}


@app.get('/v1/account/quotas')
def account_quotas(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return quota_usage(db,user.id)


@app.post("/v1/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(request.cookies.get("ragforge_session", ""))))
    db.commit()
    response.delete_cookie("ragforge_session", path="/")
    return {"ok": True}


@app.get("/v1/projects")
def projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [project_dict(db, p) for p in db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc()))]


@app.post("/v1/projects", status_code=201)
def create_project(body: ProjectInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(db, "user:" + user.id)
    lock_owner(db,user.id)
    if db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == user.id)) >= s.max_projects_per_user:
        raise HTTPException(409, "Project quota reached")
    project = Project(owner_id=user.id, **body.model_dump())
    db.add(project)
    db.commit()
    return project_dict(db, project)


@app.get("/v1/projects/{project_id}")
def get_project(project_id: str, request: Request, db: Session = Depends(get_db)):
    return project_dict(db, access(project_id, request, db).project)


@app.patch("/v1/projects/{project_id}")
def update_project(project_id: str, body: ProjectInput, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db, owner_only=True).project
    project.name, project.description = body.name, body.description
    db.commit()
    return project_dict(db, project)


@app.delete("/v1/projects/{project_id}")
def delete_project(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db, owner_only=True).project
    lock_owner(db,project.owner_id)
    names = list(db.scalars(select(Document.storage_name).where(Document.project_id == project_id)))
    db.delete(project)
    db.commit()
    for name in names:
        (s.storage_dir / name).unlink(missing_ok=True)
    return {"deleted": True}


@app.get("/v1/projects/{project_id}/documents")
def documents(project_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db)
    return [document_dict(d) for d in db.scalars(select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc()))]


@app.post("/v1/projects/{project_id}/documents", status_code=202)
def upload(project_id: str, file: UploadFile, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db, "documents").project
    lock_owner(db,project.owner_id)
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    require_compatible(db, project, for_upload=True)
    if db.scalar(select(func.count()).select_from(Document).where(Document.project_id == project_id)) >= s.max_documents_per_project:
        raise HTTPException(409, "Document quota reached for this project")
    content = file.file.read(s.max_upload_mb*1024*1024+1)
    if len(content) > s.max_upload_mb*1024*1024:
        raise HTTPException(413, f"Maximum upload size is {s.max_upload_mb} MB")
    allocate(db,project.owner_id,incoming=len(content),ingestion=1)
    try:
        name, kind = validate_file(file.filename or "", content)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from None
    if project.pipeline.get("auto") and not db.scalar(select(Document.id).where(Document.project_id == project_id).limit(1)):
        project.pipeline = {**project.pipeline, "strategy": "vector" if s.embedding_provider == "semantic" and db.bind.dialect.name == "sqlite" else "hybrid", "chunk_size": 100 if kind == "csv" else 180, "overlap": 15 if kind == "csv" else 30}
    storage_name = uuid.uuid4().hex + "." + kind
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    path = s.storage_dir / storage_name
    try:
        with path.open("xb") as target:
            target.write(content)
        doc = Document(project_id=project_id, name=name, kind=kind, storage_name=storage_name, sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content))
        db.add(doc)
        db.flush()
        enqueue(db, doc, project)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return document_dict(doc)


@app.get("/v1/projects/{project_id}/documents/{document_id}")
def inspect_document(project_id: str, document_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db)
    doc = child(db, Document, project_id, document_id)
    chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == doc.id, Chunk.project_id == project_id).order_by(Chunk.ordinal).limit(100)))
    return {**document_dict(doc), "chunks": [row_dict(c, "id ordinal text locator pipeline_version embedding_model") for c in chunks], "preview_limit": 100}


@app.delete("/v1/projects/{project_id}/documents/{document_id}")
def delete_document(project_id: str, document_id: str, request: Request, db: Session = Depends(get_db)):
    auth=access(project_id, request, db, "documents")
    lock_owner(db,auth.project.owner_id)
    doc = child(db, Document, project_id, document_id)
    path = s.storage_dir / doc.storage_name
    # Cached answer text may contain deleted material, so clear project history and eval runs.
    db.execute(delete(Conversation).where(Conversation.project_id == project_id))
    db.execute(delete(QueryRecord).where(QueryRecord.project_id == project_id))
    db.execute(delete(EvalRun).where(EvalRun.project_id == project_id))
    for case in db.scalars(select(EvalCase).where(EvalCase.project_id == project_id)):
        if document_id in case.relevant_document_ids:
            db.delete(case)
    db.delete(doc)
    db.commit()
    path.unlink(missing_ok=True)
    return {"deleted": True, "history_cleared": True}


@app.get("/v1/projects/{project_id}/jobs")
def jobs(project_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db)
    return [job_dict(j) for j in db.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc()).limit(200))]


@app.get("/v1/projects/{project_id}/jobs/{job_id}")
def get_job(project_id: str, job_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db)
    return job_dict(child(db, Job, project_id, job_id))


@app.post("/v1/projects/{project_id}/jobs/{job_id}/retry")
def retry_job(project_id: str, job_id: str, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db, "documents").project
    lock_owner(db,project.owner_id)
    allocate(db,project.owner_id,ingestion=1)
    job = child(db, Job, project_id, job_id)
    if job.status != "failed":
        raise HTTPException(409, "Only failed jobs can be retried")
    doc = child(db, Document, project_id, job.document_id)
    job.status, job.attempts, job.error, job.available_at, job.finished_at = "queued", 0, None, time.time(), None
    if project.index_profile and project.index_profile.get("id") != embedding_id():
        raise HTTPException(409, "Model configuration changed. Rebuild the entire project index before retrying individual jobs.")
    job.config, job.pipeline_version = {**project.pipeline, "_embedding": profile(), "_generation": project.index_generation}, project.pipeline_version
    doc.status, doc.error = "queued", None
    db.commit()
    return job_dict(job)


@app.get("/v1/projects/{project_id}/pipeline")
def pipeline(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db).project
    versions = list(db.scalars(select(Chunk.pipeline_version).where(Chunk.project_id == project_id).distinct()))
    status = index_status(db, project)
    return {"config": {"semantic_min_score": 0.32, **project.pipeline}, "version": project.pipeline_version, "reindex_required": any(v != project.pipeline_version for v in versions) or not status["query_ready"], "index": status, "embedding_profile": profile(), "embedding_runtime": runtime_stats(), "embedding_provider": s.embedding_provider, "embedding_model": embedding_id(), "generation_provider": s.generation_provider, "generation_model": s.openai_model if s.generation_provider == "openai" else "exact-sentence extraction", "selection_reason": "Hybrid uses reciprocal rank fusion of model-compatible vector and keyword candidates. MiniLM chunks respect a 256-token budget. Thresholds are explicit and benchmarked; they are not answer confidence probabilities."}


@app.put("/v1/projects/{project_id}/pipeline")
def set_pipeline(project_id: str, body: PipelineInput, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db, owner_only=True).project
    if any(project.pipeline[k] != getattr(body, k) for k in ("chunk_size", "overlap")):
        project.pipeline_version += 1
    project.pipeline = body.model_dump()
    db.commit()
    return {"config": project.pipeline, "version": project.pipeline_version}


@app.post("/v1/projects/{project_id}/reindex", status_code=202)
def reindex(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db, owner_only=True).project
    lock_owner(db,project.owner_id)
    project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
    dimensions = storage_dimensions(db)
    if dimensions is not None and dimensions != profile()["dimensions"]:
        raise HTTPException(409, "Database vector dimensions differ from the active model. Use a separate database or explicit vector-column migration; existing data is preserved.")
    active = list(db.scalars(select(Job).where(Job.project_id == project_id, Job.status.in_(["queued", "processing"]))))
    if active and project.index_profile and project.index_profile.get("id") == embedding_id() and all(j.config.get("_embedding", {}).get("id") == embedding_id() and j.config.get("_generation", 0) == project.index_generation and j.pipeline_version == project.pipeline_version for j in active):
        return {"queued": 0, "index_generation": project.index_generation, "message": "Matching jobs are already queued or processing."}
    for job in active:
        job.status, job.lease_token, job.lease_until = "cancelled", str(uuid.uuid4()), None
        job.error, job.finished_at = "Superseded by a controlled index rebuild", time.time()
    db.flush()
    allocate(db,project.owner_id,ingestion=db.scalar(select(func.count()).select_from(Document).where(Document.project_id==project_id)))
    project.index_generation += 1
    project.index_profile = profile()
    count = 0
    for doc in db.scalars(select(Document).where(Document.project_id == project_id)):
        enqueue(db, doc, project)
        count += 1
    db.commit()
    return {"queued": count, "index_generation": project.index_generation, "embedding_profile": profile()}


@app.post("/v1/projects/{project_id}/retrieval/compare")
def compare_retrieval(project_id: str, body: QueryInput, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db, owner_only=True).project
    results = []
    for strategy in ("vector", "keyword", "hybrid"):
        start = time.perf_counter()
        sources = retrieve(db, project, body.question, strategy=strategy)
        results.append({"strategy": strategy, "retrieval_latency_ms": round((time.perf_counter()-start)*1000, 2), "retrieved": sources})
    return {"question": body.question, "embedding_profile": profile(), "results": results, "note": "Retrieval signals are not accuracy or answer confidence scores. No answer generation or history entry is created."}


@app.post("/v1/projects/{project_id}/query")
def query(project_id: str, body: QueryInput, request: Request, db: Session = Depends(get_db)):
    auth = access(project_id, request, db, "query")
    return answer(db, auth.project, body.question, auth.principal, body.conversation_id)


@app.post("/v1/projects/{project_id}/query/stream")
def query_stream(project_id: str, body: QueryInput, request: Request, db: Session = Depends(get_db)):
    auth = access(project_id, request, db, "query")
    result = answer(db, auth.project, body.question, auth.principal, body.conversation_id)
    def events():
        yield "event: sources\ndata: " + json.dumps({"citations": result["citations"], "retrieved": result["retrieved"]}) + "\n\n"
        for offset in range(0, len(result["answer"]), 60):
            yield "event: delta\ndata: " + json.dumps({"text": result["answer"][offset:offset+60]}) + "\n\n"
        yield "event: done\ndata: " + json.dumps(result) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.get("/v1/projects/{project_id}/conversations")
def conversations(project_id: str, request: Request, db: Session = Depends(get_db)):
    auth = access(project_id, request, db, owner_only=True)
    return [row_dict(c, "id title created_at") for c in db.scalars(select(Conversation).where(Conversation.project_id == project_id, Conversation.principal == auth.principal).order_by(Conversation.created_at.desc()).limit(50))]


@app.get("/v1/projects/{project_id}/conversations/{conversation_id}")
def conversation(project_id: str, conversation_id: str, request: Request, db: Session = Depends(get_db)):
    auth = access(project_id, request, db, owner_only=True)
    c = child(db, Conversation, project_id, conversation_id)
    if c.principal != auth.principal:
        raise HTTPException(404, "Conversation not found")
    return [row_dict(q, "id question result created_at") for q in db.scalars(select(QueryRecord).where(QueryRecord.conversation_id == c.id, QueryRecord.project_id == project_id).order_by(QueryRecord.created_at).limit(200))]


@app.get("/v1/projects/{project_id}/keys")
def keys(project_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db, owner_only=True)
    return [row_dict(k, "id name prefix scopes created_at last_used_at") for k in db.scalars(select(APIKey).where(APIKey.project_id == project_id))]


@app.post("/v1/projects/{project_id}/keys", status_code=201)
def create_key(project_id: str, body: KeyInput, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db, owner_only=True)
    raw = "rf_" + secrets.token_urlsafe(32)
    key = APIKey(project_id=project_id, name=body.name, scopes=body.scopes, prefix=raw[:11], token_hash=digest(raw),expires_at=time.time()+s.api_key_ttl_days*86400)
    db.add(key)
    db.commit()
    return {**row_dict(key, "id name prefix scopes created_at expires_at"), "secret": raw}


@app.delete("/v1/projects/{project_id}/keys/{key_id}")
def revoke_key(project_id: str, key_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db, owner_only=True)
    db.delete(child(db, APIKey, project_id, key_id))
    db.commit()
    return {"revoked": True}


@app.get("/v1/projects/{project_id}/status")
def project_status(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = access(project_id, request, db).project
    states = dict(db.execute(select(Document.status, func.count()).where(Document.project_id == project_id).group_by(Document.status)).all())
    status = index_status(db, project)
    return {"project_id": project_id, "documents": states, "ready": bool(states.get("ready")) and status["query_ready"], "pipeline_version": project.pipeline_version, "index": status}


@app.get("/v1/projects/{project_id}/usage")
def usage(project_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db)
    count, average, refused = db.execute(select(func.count(QueryRecord.id), func.avg(QueryRecord.latency_ms), func.sum(cast_bool(QueryRecord.refused))).where(QueryRecord.project_id == project_id)).one()
    return {"queries": count, "average_latency_ms": round(average, 2) if average is not None else None, "refused_queries": refused or 0, "uploaded_bytes": db.scalar(select(func.sum(Document.size_bytes)).where(Document.project_id == project_id)) or 0, "provider_token_usage": None, "note": "Token billing is not tracked in this release. Deleting documents clears retained query history and these counters."}


def cast_bool(column):
    from sqlalchemy import case
    return case((column.is_(True), 1), else_=0)


@app.get("/v1/projects/{project_id}/manifest")
def manifest(project_id: str, request: Request, db: Session = Depends(get_db)):
    p = access(project_id, request, db, owner_only=True).project
    docs = db.scalars(select(Document).where(Document.project_id == project_id))
    return {"schema_version": "1.1", "name": p.name, "description": p.description, "pipeline": p.pipeline, "embedding": profile(), "index_generation": p.index_generation, "generation": {"provider": s.generation_provider, "model": s.openai_model or None}, "documents": [{"name": d.name, "sha256": d.sha256, "status": d.status} for d in docs], "export_status": "Configuration only. Standalone source package export is the next milestone."}


@app.get("/v1/projects/{project_id}/evaluation/cases")
def eval_cases(project_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db, owner_only=True)
    return [row_dict(c, "id question relevant_document_ids expected_answer expect_refusal verified origin") for c in db.scalars(select(EvalCase).where(EvalCase.project_id == project_id))]


@app.post("/v1/projects/{project_id}/evaluation/cases", status_code=201)
def create_case(project_id: str, body: CaseInput, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db, owner_only=True)
    for doc_id in body.relevant_document_ids:
        child(db, Document, project_id, doc_id)
    if db.scalar(select(func.count()).select_from(EvalCase).where(EvalCase.project_id == project_id)) >= 50:
        raise HTTPException(409, "Maximum 50 evaluation cases per project")
    case = EvalCase(project_id=project_id, **body.model_dump(), origin="manual")
    db.add(case)
    db.commit()
    return row_dict(case, "id question verified origin")


@app.delete("/v1/projects/{project_id}/evaluation/cases/{case_id}")
def delete_case(project_id: str, case_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db, owner_only=True)
    db.delete(child(db, EvalCase, project_id, case_id))
    db.commit()
    return {"deleted": True}


@app.post("/v1/projects/{project_id}/evaluation/generate")
def synthetic_cases(project_id: str, request: Request, db: Session = Depends(get_db)):
    p = access(project_id, request, db, owner_only=True).project
    if db.scalar(select(func.count()).select_from(EvalCase).where(EvalCase.project_id == project_id)) > 45:
        raise HTTPException(409, "Remove cases before generating more (maximum 50)")
    return {"created": len(generate_cases(db, p)), "verified": False}


@app.get("/v1/projects/{project_id}/evaluation/runs")
def eval_runs(project_id: str, request: Request, db: Session = Depends(get_db)):
    access(project_id, request, db, owner_only=True)
    return [row_dict(r, "id created_at result") for r in db.scalars(select(EvalRun).where(EvalRun.project_id == project_id).order_by(EvalRun.created_at.desc()).limit(20))]


@app.post("/v1/projects/{project_id}/evaluation/runs", status_code=201)
def create_run(project_id: str, body: RunInput, request: Request, db: Session = Depends(get_db)):
    p = access(project_id, request, db, owner_only=True).project
    if not db.scalar(select(EvalCase.id).where(EvalCase.project_id == project_id, EvalCase.verified.is_(True) if not body.include_unverified else True).limit(1)):
        raise HTTPException(409, "Add a verified test case or explicitly include unverified synthetic cases")
    run = run_evaluation(db, p, body.include_unverified)
    return row_dict(run, "id created_at result")


@app.get("/v1/projects/{project_id}/widget")
def widget(project_id: str, request: Request, db: Session = Depends(get_db)):
    p = access(project_id, request, db, owner_only=True).project
    return {**WidgetInput().model_dump(), **p.widget, "has_token": bool(p.widget_hash)}


@app.put("/v1/projects/{project_id}/widget")
def set_widget(project_id: str, body: WidgetInput, request: Request, db: Session = Depends(get_db)):
    if body.enabled and not s.allow_public_widgets:raise HTTPException(403,'Public widgets are disabled by the operator')
    p = access(project_id, request, db, owner_only=True).project
    raw = secrets.token_urlsafe(32) if body.enabled else None
    p.widget, p.widget_hash = body.model_dump(), digest(raw) if raw else None
    db.commit()
    return {**p.widget, "token": raw, "notice": "Enabling publishes query access to every ready document in this project. Saving rotates the token and invalidates previous embeds."}


def public_access(project_id, token, request, db):
    p = db.get(Project, project_id)
    if not s.allow_public_widgets or (p and db.get(User,p.owner_id).disabled):raise HTTPException(404,'Published assistant not found')
    if not p or not p.widget.get("enabled") or not p.widget_hash or not hmac.compare_digest(p.widget_hash, digest(token)):
        raise HTTPException(404, "Published assistant not found")
    # Embedding origin is enforced by the frame's CSP. It is not authentication.
    origin = request.headers.get("origin")
    allowed = p.widget.get("allowed_origins", []) + s.origins
    if origin and origin.rstrip("/") not in allowed:
        raise HTTPException(403, "Origin is not allowed")
    rate_limit(db, "public-project:" + project_id, 30)
    rate_limit(db, "public-client:" + project_id + ":" + (request.client.host if request.client else "unknown"), 10)
    return p


@app.get("/v1/public/{project_id}/config")
def public_config(project_id: str, request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    p = public_access(project_id, token, request, db)
    return {"title": p.widget["title"], "welcome": p.widget["welcome"], "color": p.widget["color"], "theme": p.widget["theme"], "allowed_origins": p.widget["allowed_origins"]}


@app.get("/v1/public/{project_id}/frame-policy")
def frame_policy(project_id: str, request: Request, db: Session = Depends(get_db)):
    # Only public embedding policy is disclosed. Document queries still require the capability.
    rate_limit(db, "frame:" + (request.client.host if request.client else "unknown"), 120)
    p = db.get(Project, project_id)
    if not s.allow_public_widgets or not p or db.get(User,p.owner_id).disabled or not p.widget.get("enabled"):
        raise HTTPException(404, "Published assistant not found")
    return {"allowed_origins": p.widget["allowed_origins"]}


@app.post("/v1/public/{project_id}/query")
def public_query(project_id: str, body: QueryInput, request: Request, db: Session = Depends(get_db)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    p = public_access(project_id, token, request, db)
    return answer(db, p, body.question, "widget", save=True, public=True)


def openapi_schema():
    from fastapi.openapi.utils import get_openapi
    from fastapi.routing import APIRoute
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {
        "ProjectKey": {"type": "http", "scheme": "bearer", "description": "Project-scoped key created in API & Integration"},
        "SessionCookie": {"type": "apiKey", "in": "cookie", "name": "ragforge_session", "description": "Sign in through the dashboard; browsers send the HttpOnly cookie"},
        "WidgetToken": {"type": "http", "scheme": "bearer", "description": "Public query capability from explicit widget publication"},
    }
    owners = {"projects", "create_project", "update_project", "delete_project", "keys", "create_key", "revoke_key", "conversations", "conversation", "set_pipeline", "reindex", "compare_retrieval", "manifest", "eval_cases", "create_case", "delete_case", "synthetic_cases", "eval_runs", "create_run", "widget", "set_widget", "create_export", "get_export", "download_export"}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        security = None
        if route.path.startswith("/v1/projects"):
            security = [{"SessionCookie": []}] if route.name in owners or "/exports" in route.path else [{"ProjectKey": []}, {"SessionCookie": []}]
        elif route.name in {"public_query", "public_config"}:
            security = [{"WidgetToken": []}]
        elif route.name == "me" or route.path.startswith(("/v1/admin/", "/v1/account/")):
            security = [{"SessionCookie": []}]
        if security:
            for method in route.methods:
                if method.lower() in schema["paths"].get(route.path, {}):
                    schema["paths"][route.path][method.lower()]["security"] = security
    app.openapi_schema = schema
    return schema


app.openapi = openapi_schema
