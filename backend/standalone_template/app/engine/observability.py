"""Low-cardinality persistent counters/histograms. No questions or source text."""
import os
import socket
import time
import psutil
from sqlalchemy import select, case
from .db import SessionLocal
from .models import OperationalMetric, WorkerHeartbeat
_process=psutil.Process()
_process.cpu_percent()


def _metric(key,elapsed_ms=0):
    with SessionLocal() as db:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
        stmt=insert(OperationalMetric).values(key=key,count=1,total_ms=elapsed_ms,max_ms=elapsed_ms)
        db.execute(stmt.on_conflict_do_update(index_elements=[OperationalMetric.key],set_={'count':OperationalMetric.count+1,'total_ms':OperationalMetric.total_ms+elapsed_ms,'max_ms':case((OperationalMetric.max_ms<elapsed_ms,elapsed_ms),else_=OperationalMetric.max_ms)}))
        db.commit()


def metric(key,elapsed_ms=0):
    try:_metric(key,elapsed_ms)
    except Exception:pass


def api_metric(method,route,status,elapsed):
    method=method if method in ('GET','POST','PUT','PATCH','DELETE','OPTIONS') else 'OTHER'
    key=f'http|{method}|{route}|{status}'
    try:
        metric(key,elapsed)
        bucket=next((b for b in [10,50,100,250,500,1000,2000,5000,10000] if elapsed<=b),'inf')
        metric(key+'|bucket_'+str(bucket))
    except Exception:pass # Database outage must not replace the original API response.


def heartbeat(parser=None):
    from .embeddings import runtime_stats
    process=_process
    instance=socket.gethostname()+':'+str(os.getpid())
    details={'rss_bytes':process.memory_info().rss,'cpu_percent':process.cpu_percent(),'embedding':runtime_stats(),'parser':parser or {}}
    with SessionLocal() as db:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
        stmt=insert(WorkerHeartbeat).values(instance=instance,updated_at=time.time(),details=details)
        db.execute(stmt.on_conflict_do_update(index_elements=[WorkerHeartbeat.instance],set_={'updated_at':time.time(),'details':details}))
        from sqlalchemy import delete
        db.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.updated_at<time.time()-86400))
        db.commit()
