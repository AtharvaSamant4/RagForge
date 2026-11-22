"""Single-collection API. No hosted account, cookie or service dependency."""
import hashlib
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from .bootstrap import MANIFEST, COLLECTION_ID, PIPELINE
from .engine.config import settings
from .engine.db import get_db
from .engine.models import Document, Job, Project
from .engine.ingestion import validate_file, ExtractionError
from .engine.indexing import index_status, require_compatible, storage_dimensions
from .engine.providers import ProviderError
from .engine.worker import enqueue
from .engine.logging_config import configure_logging
from .embeddings import profile, runtime_stats
from .models import QueryInput
from .retrieval import answer
from .security import authenticate


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    yield


app = FastAPI(title="Standalone Knowledge API", version="1.0.0", lifespan=lifespan)
from .http_limits import BodyLimit
app.add_middleware(BodyLimit)


@app.middleware("http")
async def limits(request: Request, call_next):
    maximum = (settings().max_upload_mb+1)*1024*1024 if request.url.path.endswith("/documents") else 256*1024
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError:
        length = maximum+1
    if length > maximum or length < 0:
        return JSONResponse({"detail":"Request exceeds body limit"},413)
    if request.method=="POST" and request.url.path.endswith("/documents") and "content-length" not in request.headers:
        return JSONResponse({"detail":"Content-Length is required for uploads"},411)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Cache-Control"]="no-store"
    return response


@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return JSONResponse({"detail":str(exc)},503)


def collection(db,lock=False):
    query=select(Project).where(Project.id==COLLECTION_ID)
    project = db.scalar(query.with_for_update() if lock else query)
    if not project:
        raise HTTPException(503,"Run python -m app.initialize before starting the API")
    return project


def imports_enabled():
    if not MANIFEST["allow_imports"]:
        raise HTTPException(403,"Document import is disabled in this exported configuration")


@app.get("/health")
def health():
    return {"status":"ok","runtime":"standalone","generator_version":MANIFEST["generator_version"]}


@app.get("/v1/config",dependencies=[Depends(authenticate)])
def config(db=Depends(get_db)):
    project=collection(db)
    return {"name":project.name,"pipeline":project.pipeline,"embedding_profile":profile(),"generation_provider":settings().generation_provider,"allow_imports":MANIFEST["allow_imports"],"generator_version":MANIFEST["generator_version"],"template_sha256":MANIFEST["template_sha256"]}


@app.get("/v1/status",dependencies=[Depends(authenticate)])
def status(db=Depends(get_db)):
    project=collection(db)
    return {"index":index_status(db,project),"embedding_runtime":runtime_stats(),"documents":[{"id":d.id,"name":d.name,"status":d.status,"chunk_count":d.chunk_count,"error":d.error,"metadata":d.metadata_json} for d in db.scalars(select(Document).where(Document.project_id==COLLECTION_ID))]}


@app.post("/v1/query",dependencies=[Depends(authenticate)])
def query(body:QueryInput,db=Depends(get_db)):
    return answer(db,collection(db),body.question,"standalone",save=False)


@app.get("/v1/documents",dependencies=[Depends(authenticate)])
def documents(db=Depends(get_db)):
    return status(db)["documents"]


@app.post("/v1/documents",status_code=202,dependencies=[Depends(authenticate)])
def upload(file:UploadFile,db=Depends(get_db)):
    imports_enabled()
    project=collection(db,lock=True)
    require_compatible(db,project,for_upload=True)
    if db.scalar(select(func.count()).select_from(Document))>=100:
        raise HTTPException(409,"Limit: 100 documents per collection")
    content=file.file.read(settings().max_upload_mb*1024*1024+1)
    if len(content)>settings().max_upload_mb*1024*1024:
        raise HTTPException(413,"Upload exceeds configured size limit")
    try:
        name,kind=validate_file(file.filename or "",content)
    except ExtractionError as exc:
        raise HTTPException(422,str(exc)) from None
    sha=hashlib.sha256(content).hexdigest()
    db.execute(text("DELETE FROM standalone_removed_sources WHERE sha256=:sha"),{"sha":sha})
    previous=db.scalar(select(Document).where(Document.sha256==sha))
    if previous:
        return {"id":previous.id,"status":previous.status,"duplicate":True}
    storage_name=uuid.uuid4().hex+"."+kind
    path=settings().storage_dir/storage_name
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as out:
        out.write(content)
    try:
        doc=Document(project_id=COLLECTION_ID,name=name,kind=kind,storage_name=storage_name,sha256=sha,size_bytes=len(content))
        db.add(doc);db.flush();enqueue(db,doc,project);db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"id":doc.id,"status":doc.status}


@app.delete("/v1/documents/{document_id}",dependencies=[Depends(authenticate)])
def delete_document(document_id:str,db=Depends(get_db)):
    imports_enabled()
    collection(db,lock=True)
    doc=db.scalar(select(Document).where(Document.id==document_id,Document.project_id==COLLECTION_ID))
    if not doc:raise HTTPException(404,"Document not found")
    if any(source["sha256"]==doc.sha256 for source in MANIFEST["sources"]):
        db.execute(text("INSERT INTO standalone_removed_sources (sha256) VALUES (:sha) ON CONFLICT (sha256) DO NOTHING"),{"sha":doc.sha256})
    path=settings().storage_dir/doc.storage_name
    db.delete(doc);db.commit()
    path.unlink(missing_ok=True)
    return {"deleted":True}


@app.get("/v1/jobs",dependencies=[Depends(authenticate)])
def jobs(db=Depends(get_db)):
    return [{"id":j.id,"document_id":j.document_id,"status":j.status,"attempts":j.attempts,"error":j.error} for j in db.scalars(select(Job).where(Job.project_id==COLLECTION_ID).order_by(Job.created_at.desc()).limit(200))]


@app.post("/v1/jobs/{job_id}/retry",dependencies=[Depends(authenticate)])
def retry(job_id:str,db=Depends(get_db)):
    imports_enabled()
    project=collection(db,lock=True)
    if project.index_profile and project.index_profile.get("id")!=profile()["id"]:
        raise HTTPException(409,"Model configuration changed; rebuild the collection before retrying individual jobs")
    job=db.get(Job,job_id)
    if not job or job.project_id!=COLLECTION_ID:
        raise HTTPException(404,"Job not found")
    if job.status!="failed":
        raise HTTPException(409,"Only failed jobs can be retried")
    job.status,job.attempts,job.available_at,job.error,job.finished_at="queued",0,time.time(),None,None
    job.config={**project.pipeline,"_embedding":profile(),"_generation":project.index_generation}
    doc=db.get(Document,job.document_id);doc.status,doc.error="queued",None
    db.commit()
    return {"id":job.id,"status":job.status}


@app.post("/v1/reindex",status_code=202,dependencies=[Depends(authenticate)])
def reindex(db=Depends(get_db)):
    project=collection(db,lock=True)
    if storage_dimensions(db) not in (None,profile()["dimensions"]):
        raise HTTPException(409,"Storage dimensions differ; an explicit vector-column migration is required")
    active=list(db.scalars(select(Job).where(Job.project_id==COLLECTION_ID,Job.status.in_(["queued","processing"]))))
    if active and project.pipeline==PIPELINE and all(j.config.get("_embedding",{}).get("id")==profile()["id"] and j.config.get("_generation")==project.index_generation for j in active):
        return {"queued":0,"message":"Matching work is already active"}
    for job in active:
        job.status,job.lease_token,job.lease_until="cancelled",str(uuid.uuid4()),None
    project.index_generation+=1
    project.index_profile=profile()
    # Editing config/manifest.json changes pipeline only through this explicit rebuild.
    project.pipeline=PIPELINE
    project.pipeline_version+=1
    count=0
    for doc in db.scalars(select(Document).where(Document.project_id==COLLECTION_ID)):
        enqueue(db,doc,project);count+=1
    db.commit()
    return {"queued":count,"index_generation":project.index_generation}
