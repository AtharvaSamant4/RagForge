"""Operator CLI and administrator-only diagnostics/invites."""
import argparse
import getpass
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from .config import settings
from .db import get_db, SessionLocal
from .models import User, Invite, LoginSession, APIKey, Project, Job, ExportJob, OperationalMetric, WorkerHeartbeat, ProviderUsage, QueryRecord
from .security import current_user,digest,password_hash

router=APIRouter(tags=['Operator diagnostics'])


def admin(request:Request,db=Depends(get_db)):
    if request.headers.get('authorization'):raise HTTPException(403,'Administrator session required')
    user=current_user(request,db)
    if not user.is_admin:raise HTTPException(403,'Administrator access required')
    return user


class InviteInput(BaseModel):
    ttl_hours:int=Field(default=48,ge=1,le=168)


@router.post('/v1/admin/invites')
def invite(body:InviteInput,user=Depends(admin),db=Depends(get_db)):
    raw=secrets.token_urlsafe(32)
    row=Invite(token_hash=digest(raw),created_by=user.id,expires_at=time.time()+body.ttl_hours*3600)
    db.add(row);db.commit()
    return {'id':row.id,'token':raw,'expires_at':row.expires_at,'notice':'Shown once. Deliver privately; never put invite tokens in URLs/logs.'}


@router.delete('/v1/admin/invites/{invite_id}')
def revoke(invite_id:str,user=Depends(admin),db=Depends(get_db)):
    row=db.get(Invite,invite_id)
    if not row:raise HTTPException(404,'Invite not found')
    row.revoked=True;db.commit();return {'revoked':True}


def readiness(db):
    checks={}
    try:db.execute(text('SELECT 1'));checks['database']=True
    except Exception:return {'ready':False,'checks':{'database':False}}
    try:checks['schema']=db.scalar(text('SELECT version_num FROM alembic_version'))=='0005'
    except Exception:
        db.rollback();checks['schema']=False
    workers=list(db.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.updated_at>time.time()-90)))
    checks['worker']=bool(workers)
    s=settings()
    checks['secure_alpha_config']=s.deployment_mode!='private_alpha' or (s.cookie_secure and bool(s.origins) and s.registration_mode in ('invite','disabled') and all(x.startswith('https://') for x in s.origins))
    checks['parser']=s.deployment_mode!='private_alpha' or any(w.details.get('parser',{}).get('filesystem')=='landlock' and w.details.get('parser',{}).get('network_process')=='seccomp' for w in workers)
    checks['model']=s.embedding_provider!='semantic' or any(w.details.get('embedding',{}).get('loaded') for w in workers)
    import os
    checks['storage']=all(p.is_dir() and os.access(p,os.W_OK) for p in (s.storage_dir,s.export_dir))
    return {'ready':all(checks.values()),'checks':checks}


@router.get('/ready')
def ready(db=Depends(get_db)):
    from fastapi.responses import JSONResponse
    state=readiness(db)
    return JSONResponse({'ready':state['ready']},200 if state['ready'] else 503)


def diagnostics(db):
    from .config import settings
    import psutil
    query_stats=db.execute(select(func.count(QueryRecord.id),func.avg(QueryRecord.latency_ms),func.max(QueryRecord.latency_ms))).one()
    return {'query_latency':{'count':query_stats[0],'mean_ms':query_stats[1],'max_ms':query_stats[2]},'readiness':readiness(db),'limits':{k:getattr(settings(),k) for k in ['user_storage_mb','max_documents_per_project','max_ingestion_jobs_per_user','max_ingestion_processes','max_export_jobs_per_user','rate_limit_per_minute','parser_wall_seconds','parser_cpu_seconds','parser_memory_mb','hosted_daily_requests','hosted_daily_input_chars']},'metrics':[{'key':r.key,'count':r.count,'total_ms':r.total_ms,'max_ms':r.max_ms} for r in db.scalars(select(OperationalMetric))],'workers':[{'instance':w.instance,'age_seconds':round(time.time()-w.updated_at,1),'resources':w.details} for w in db.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.updated_at>time.time()-300))],'jobs':dict(db.execute(select(Job.status,func.count()).group_by(Job.status)).all()),'exports':dict(db.execute(select(ExportJob.status,func.count()).group_by(ExportJob.status)).all()),'provider_usage':[{'day':r.day,'requests':r.requests,'input_chars':r.input_chars} for r in db.scalars(select(ProviderUsage))],'api_rss_bytes':psutil.Process().memory_info().rss}


@router.get('/v1/admin/diagnostics')
def diagnostic_endpoint(user=Depends(admin),db=Depends(get_db)):
    return diagnostics(db)


def cli():
    parser=argparse.ArgumentParser(description='Local operator authority. Secrets are read from stdin/getpass, never CLI arguments.')
    parser.add_argument('action',choices=['bootstrap-admin','rotate-password','disable-user','diagnostics'])
    parser.add_argument('--email')
    parser.add_argument('--password-stdin',action='store_true')
    args=parser.parse_args()
    with SessionLocal() as db:
        if args.action=='diagnostics':
            import json;print(json.dumps(diagnostics(db),indent=2));return
        if not args.email:parser.error('--email is required')
        email=args.email.strip().lower()
        # Serialize first-admin initialization and operator mutations across processes.
        if db.bind.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(6743324)'))
        else:db.execute(text('BEGIN IMMEDIATE'))
        user=db.scalar(select(User).where(User.email==email))
        if args.action=='disable-user':
            if not user:parser.error('Account not found')
            user.disabled=True
        else:
            if args.action=='bootstrap-admin' and db.scalar(select(User.id).where(User.is_admin==True).limit(1)):parser.error('Administrator already initialized; use controlled password rotation')
            if args.action=='rotate-password' and not user:parser.error('Account not found')
            if args.password_stdin:
                import sys;password=sys.stdin.readline().rstrip('\r\n')
            else:password=getpass.getpass('New password (12+ characters): ')
            if not 12<=len(password)<=200:parser.error('Password must contain 12–200 characters')
            if not user:user=User(email=email,password_hash='!');db.add(user)
            user.password_hash=password_hash(password)
            if args.action=='bootstrap-admin':user.is_admin=True
        db.flush()
        db.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
        # Password rotation/disable also revoke project keys, including legacy nonexpiring keys.
        db.execute(delete(APIKey).where(APIKey.project_id.in_(select(Project.id).where(Project.owner_id==user.id))))
        db.commit();print('Operator action completed; credentials were not printed.')


if __name__=='__main__':cli()
