"""Allocation reads are serialized by the owner row before project/global locks."""
from fastapi import HTTPException
from sqlalchemy import func, select, update
from .config import settings
from .models import User, Project, Document, Job, ExportJob


def lock_owner(db,user_id):
    row=db.scalar(update(User).where(User.id==user_id).values(resource_epoch=User.resource_epoch+1).returning(User.id))
    if not row:raise HTTPException(404,'Account not found')


def usage(db,user_id):
    projects=select(Project.id).where(Project.owner_id==user_id)
    source=db.scalar(select(func.coalesce(func.sum(Document.size_bytes),0)).where(Document.project_id.in_(projects)))
    exports=list(db.scalars(select(ExportJob).where(ExportJob.project_id.in_(projects),ExportJob.status.in_(['queued','generating','ready']))))
    archive=sum(j.size_bytes if j.status=='ready' else settings().export_max_archive_mb*1024**2 for j in exports)
    ingestion=db.scalar(select(func.count()).select_from(Job).where(Job.project_id.in_(projects),Job.status.in_(['queued','processing'])))
    return {'source_bytes':source,'export_allocated_bytes':archive,'storage_allocated_bytes':source+archive,'ingestion_jobs':ingestion,'export_jobs':sum(j.status in ('queued','generating') for j in exports),'storage_limit_bytes':settings().user_storage_mb*1024**2}


def allocate(db,user_id,incoming=0,ingestion=0,export=0):
    state=usage(db,user_id)
    if state['storage_allocated_bytes']+incoming>state['storage_limit_bytes']:
        raise HTTPException(413,'Account storage quota reached. Delete sources or expired exports before retrying.')
    if ingestion>settings().max_ingestion_jobs_per_user:
        raise HTTPException(429,'Account ingestion-job quota reached. This rebuild needs more job slots than the configured cap; ask the operator to raise it or use a smaller collection.')
    if state['ingestion_jobs']+ingestion>settings().max_ingestion_jobs_per_user:
        raise HTTPException(429,'Account ingestion-job quota reached. Wait for processing to finish.',headers={'Retry-After':'10'})
    if state['export_jobs']+export>settings().max_export_jobs_per_user:
        raise HTTPException(429,'Account concurrent-export quota reached. Wait for the active export.')
    return state
