"""Owner-only durable export jobs with bounded storage reservations and retention."""
import os
import re
import tempfile
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, or_, text

from .config import settings
from .db import get_db, SessionLocal
from .embeddings import profile
from .models import Document, ExportJob, RateBucket, Project
from .schemas import PipelineInput
from .security import access
from .indexing import require_compatible
from .export_compiler import VERSION, ExportError, compile_archive, template_digest
from .quotas import lock_owner, allocate

router=APIRouter(prefix="/v1/projects/{project_id}/exports",tags=["Application export"])


class ExportInput(BaseModel):
    model_config=ConfigDict(extra="forbid")
    mode:Literal["configuration","snapshot"]="configuration"
    document_ids:list[str]=Field(default_factory=list,max_length=100)
    acknowledge_copy:bool=False
    allow_imports:bool=True
    include_pilot_evidence:bool=False

    @model_validator(mode="after")
    def selection(self):
        if len(set(self.document_ids))!=len(self.document_ids):raise ValueError("Select each document once")
        if self.mode=="snapshot" and (not self.document_ids or not self.acknowledge_copy):
            raise ValueError("Select documents and acknowledge that exported copies cannot be revoked")
        if self.mode=="configuration" and self.document_ids:raise ValueError("Configuration-only exports cannot include documents")
        return self


def artifact(job_id):
    if not re.fullmatch(r"[a-f0-9-]{36}",job_id):raise ExportError("Invalid export identity")
    root=settings().export_dir
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root.is_symlink():raise ExportError("Export storage cannot be a symlink")
    return root/(job_id+".zip")


def lock_storage(db):
    if db.bind.dialect.name=="postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(6743322)"))
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if db.bind.dialect.name=="postgresql" else sqlite_insert
    db.execute(insert(RateBucket).values(key="export-storage",window=int(time.time()//60),count=0).on_conflict_do_nothing(index_elements=[RateBucket.key]))
    row=db.scalar(select(RateBucket).where(RateBucket.key=="export-storage").with_for_update())
    # A write also serializes SQLite reservations (FOR UPDATE is ignored there).
    db.execute(RateBucket.__table__.update().where(RateBucket.key==row.key).values(count=0,window=int(time.time()//60)))


def expire(job):
    try:artifact(job.id).unlink(missing_ok=True)
    except PermissionError:pass # An existing Windows download may still hold the file.
    job.status,job.lease_token,job.lease_until="expired",None,None


def cleanup(db):
    now=time.time()
    for job in db.scalars(select(ExportJob).where(ExportJob.expires_at<=now)):
        expire(job)
    # Orphans can remain after a project is deleted or a worker is interrupted.
    root=settings().export_dir
    if root.exists() and not root.is_symlink():
        known=set(db.scalars(select(ExportJob.id)))
        for path in root.iterdir():
            if path.is_file() and not path.is_symlink():
                if (path.suffix==".zip" and re.fullmatch(r"[a-f0-9-]{36}",path.stem) and path.stem not in known) or (path.name.startswith("build-") and path.suffix==".part" and now-path.stat().st_mtime>600):
                    try:path.unlink(missing_ok=True)
                    except PermissionError:pass
    for job in db.scalars(select(ExportJob).where(ExportJob.status.in_(["expired","failed"]),ExportJob.created_at<now-86400)):
        db.delete(job)


def serialize(job):
    return {"id":job.id,"status":job.status,"error":job.error,"created_at":job.created_at,"expires_at":job.expires_at,"size_bytes":job.size_bytes,"sha256":job.sha256,"generation_ms":job.config.get("generation_ms"),"manifest":job.config["manifest"],"instructions":"Extract the ZIP, run python scripts/init.py, then docker compose up --build -d. See its README.md. Initial dependency/image/model downloads require network access."}


@router.post("",status_code=202)
def create_export(project_id:str,body:ExportInput,request:Request,db=Depends(get_db)):
    project=access(project_id,request,db,owner_only=True).project
    lock_owner(db,project.owner_id)
    from .pilot import participant
    member=participant(db,project.owner_id,require_consent=True,lock=True)
    if body.include_pilot_evidence and not member:
        raise HTTPException(403,'Current pilot consent is required for optional offline deployment evidence')
    active=profile()
    if active["dimensions"]!=384:raise HTTPException(422,"Standalone schema v1 supports 384-dimensional embeddings")
    pipeline=PipelineInput.model_validate(project.pipeline).model_dump()
    selected=[]
    if body.mode=="snapshot":
        require_compatible(db,project)
        for doc_id in body.document_ids:
            doc=db.scalar(select(Document).where(Document.id==doc_id,Document.project_id==project_id))
            if not doc:raise HTTPException(404,"Selected document not found in this project")
            if doc.status!="ready":raise HTTPException(409,"Every selected document must be ready before exporting")
            selected.append(doc)
    selected.sort(key=lambda d:(d.name,d.sha256,d.id))
    if sum(d.size_bytes for d in selected)>settings().export_max_source_mb*1024**2:
        raise HTTPException(413,"Selected sources exceed the export size limit")
    sources=[{"document_id":d.id,"storage_name":d.storage_name,"path":f"data/knowledge/{i+1:03d}-{d.sha256[:12]}.{d.kind}","name":d.name,"kind":d.kind,"sha256":d.sha256,"size_bytes":d.size_bytes} for i,d in enumerate(selected)]
    manifest={"schema_version":"1.0","generator_version":VERSION,"template_sha256":template_digest(),"name":project.name,"pipeline":pipeline,"embedding":active,"generation":{"provider":settings().generation_provider,"model":settings().openai_model if settings().generation_provider=="openai" else "exact-sentence extraction"},"mode":body.mode,"allow_imports":body.allow_imports,"sources":[{k:v for k,v in source.items() if k not in ("storage_name","document_id")} for source in sources]}
    job_id=str(uuid.uuid4())
    evidence=None
    if body.include_pilot_evidence:
        from .pilot import deployment_ticket
        evidence=deployment_ticket(db,project.owner_id,job_id,manifest['template_sha256'])
    lock_storage(db);cleanup(db)
    db.flush()
    allocate(db,project.owner_id,incoming=settings().export_max_archive_mb*1024**2,export=1)
    jobs=list(db.scalars(select(ExportJob).order_by(ExportJob.created_at)))
    if any(j.project_id==project_id and j.status in ("queued","generating") for j in jobs):
        db.commit()
        raise HTTPException(409,"An export for this project is already active")
    if sum(j.status in ("queued","generating") for j in jobs)>=4:
        db.commit()
        raise HTTPException(429,"Export workers are busy; retry after current exports finish")
    ready=[j for j in jobs if j.status=="ready"]
    own=[j for j in ready if j.project_id==project_id]
    for old in own[:-1]:expire(old)
    reserve=settings().export_max_archive_mb*1024**2
    # Count incomplete/orphan artifacts as well as durable reservations.
    root=settings().export_dir
    known_files={j.id+".zip" for j in jobs if j.status in ("ready","generating")}
    extra_bytes=sum(p.stat().st_size for p in root.iterdir() if p.is_file() and not p.is_symlink() and p.name not in known_files) if root.exists() else 0
    def used():return extra_bytes+sum(j.size_bytes if j.status=="ready" else reserve if j.status in ("queued","generating") else 0 for j in jobs)
    for old in ready:
        if used()+reserve<=settings().export_storage_mb*1024**2:break
        expire(old)
    if used()+reserve>settings().export_storage_mb*1024**2:
        db.commit()
        raise HTTPException(429,"Export storage is reserved by active jobs; retry later")
    job=ExportJob(id=job_id,project_id=project_id,config={"manifest":manifest,"sources":sources},expires_at=time.time()+settings().export_retention_seconds)
    if evidence:
        job.config={**job.config,'pilot_evidence':evidence}
    db.add(job);db.commit()
    return serialize(job)


@router.get("")
def list_exports(project_id:str,request:Request,db=Depends(get_db)):
    access(project_id,request,db,owner_only=True)
    jobs=list(db.scalars(select(ExportJob).where(ExportJob.project_id==project_id).order_by(ExportJob.created_at.desc()).limit(10)))
    for job in jobs:
        if job.expires_at<=time.time() and job.status!="expired":expire(job)
    db.commit()
    return [serialize(job) for job in jobs]


def owned_job(project_id,job_id,request,db):
    access(project_id,request,db,owner_only=True)
    job=db.scalar(select(ExportJob).where(ExportJob.id==job_id,ExportJob.project_id==project_id))
    if not job:raise HTTPException(404,"Export not found")
    if job.expires_at<=time.time() and job.status!="expired":expire(job);db.commit()
    return job


@router.get("/{job_id}")
def get_export(project_id:str,job_id:str,request:Request,db=Depends(get_db)):
    return serialize(owned_job(project_id,job_id,request,db))


@router.get("/{job_id}/download")
def download_export(project_id:str,job_id:str,request:Request,db=Depends(get_db)):
    job=owned_job(project_id,job_id,request,db)
    path=artifact(job.id)
    if job.status!="ready" or not path.is_file() or path.is_symlink():
        raise HTTPException(410 if job.status=="expired" else 409,"Export is unavailable; generate a new application")
    try:
        source=os.fdopen(os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0)),"rb")
    except OSError:
        raise HTTPException(410,"Export expired while opening; generate a new application") from None
    def chunks():
        try:
            while block:=source.read(1024*1024):yield block
        finally:source.close()
    return StreamingResponse(chunks(),media_type="application/zip",headers={"X-Archive-SHA256":job.sha256,"Content-Length":str(job.size_bytes),"Content-Disposition":'attachment; filename="standalone-knowledge.zip"'},background=BackgroundTask(source.close))


def run_once():
    from .observability import metric
    now=time.time()
    with SessionLocal() as db:
        job=db.scalar(select(ExportJob).where(ExportJob.expires_at>now,or_(ExportJob.status=="queued",(ExportJob.status=="generating")&(ExportJob.lease_until<now))).order_by(ExportJob.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:return False
        if job.attempts>=2:
            job.status,job.error="failed","Export worker lease expired twice; generate a new application"
            db.commit();metric('export_failed');return True
        token=str(uuid.uuid4());job_id=job.id
        job.status,job.lease_token,job.lease_until,job.attempts="generating",token,now+600,job.attempts+1
        recovered=job.attempts>1
        config=job.config
        for source in config["sources"]:
            doc=db.scalar(select(Document).where(Document.id==source["document_id"],Document.project_id==job.project_id))
            if not doc or doc.status!="ready" or doc.sha256!=source["sha256"]:
                job.status,job.error="failed","A selected source changed or was deleted; generate a new export"
                db.commit();metric('export_failed');return True
        db.commit()
    if recovered:metric('export_retry')
    part=None
    try:
        started=time.perf_counter()
        destination=artifact(job_id)
        fd,temp=tempfile.mkstemp(prefix="build-",suffix=".part",dir=destination.parent)
        os.close(fd);part=destination.parent/temp.split(os.sep)[-1]
        result=compile_archive(part,config["manifest"],config["sources"],config.get('pilot_evidence'))
        with SessionLocal() as db:
            from .pilot import participant
            owner_id=db.scalar(select(Project.owner_id).join(ExportJob,ExportJob.project_id==Project.id).where(ExportJob.id==job_id))
            if owner_id: participant(db,owner_id,require_consent=True,lock=True)
            job=db.scalar(select(ExportJob).where(ExportJob.id==job_id).with_for_update())
            if not job or job.lease_token!=token or job.status!="generating" or job.expires_at<=time.time():return True
            os.replace(part,destination)
            job.status,job.size_bytes,job.sha256,job.lease_until="ready",result["size_bytes"],result["sha256"],None
            job.config={**job.config,"generation_ms":round((time.perf_counter()-started)*1000,2)}
            from .pilot import emit
            project=db.get(Project,job.project_id)
            if project: emit(db,project.owner_id,'standalone_exported',job.id)
            db.commit()
        metric('export_succeeded',(time.perf_counter()-started)*1000)
    except Exception as exc:
        metric('export_failed')
        __import__('logging').getLogger('ragforge.exports').warning('export_failed',extra={'job_id':job_id,'error_type':type(exc).__name__})
        with SessionLocal() as db:
            from .pilot import participant
            owner_id=db.scalar(select(Project.owner_id).join(ExportJob,ExportJob.project_id==Project.id).where(ExportJob.id==job_id))
            if owner_id: participant(db,owner_id,require_consent=True,lock=True)
            job=db.get(ExportJob,job_id)
            if job and job.lease_token==token:
                job.status="failed"
                job.error=str(exc)[:300] if isinstance(exc,ExportError) else "Export generation failed; verify sources and storage, then generate again"
                from .pilot import emit
                project=db.get(Project,job.project_id)
                if project: emit(db,project.owner_id,'export_failed',job.id)
                db.commit()
    finally:
        if part:part.unlink(missing_ok=True)
    return True
