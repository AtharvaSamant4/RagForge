import logging
import time
import uuid
from pathlib import Path

from sqlalchemy import delete, or_, select, func, text as sql_text

from .config import settings
from .db import SessionLocal
from .ingestion import ExtractionError, chunk_sections, extract
from .models import Chunk, Document, Job, Project
from .providers import ProviderError, embed, embedding_id
from .embeddings import profile, token_count

log = logging.getLogger("ragforge.worker")


def enqueue(db, document: Document, project: Project):
    document.status, document.error = "queued", None
    active = profile()
    project.index_profile = active
    db.add(Job(project_id=project.id, document_id=document.id, config={**project.pipeline, "_embedding": active, "_generation": project.index_generation}, pipeline_version=project.pipeline_version))


def run_once(project_id: str | None = None) -> bool:
    now = time.time()
    with SessionLocal() as db:
        if db.bind.dialect.name=='postgresql':db.execute(sql_text('SELECT pg_advisory_xact_lock(6743323)'))
        else:db.execute(sql_text('BEGIN IMMEDIATE'))
        running=db.scalar(select(func.count()).select_from(Job).where(Job.status=='processing',Job.lease_until>now))
        if running>=settings().max_ingestion_processes:return False
        query = select(Job).where(or_((Job.status == "queued") & (Job.available_at <= now), (Job.status == "processing") & (Job.lease_until < now)))
        if project_id:
            query = query.where(Job.project_id == project_id)
        job = db.scalar(query.order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            return False
        if job.attempts >= 3:
            job.status, job.error, job.finished_at = "failed", "Processing lease expired after maximum attempts. Retry explicitly.", now
            doc = db.get(Document, job.document_id)
            if doc:
                doc.status, doc.error = "failed", job.error
            db.commit()
            return True
        job.status, job.attempts = "processing", job.attempts + 1
        token = str(uuid.uuid4())
        job.lease_until, job.lease_token = now + settings().job_lease_seconds, token
        doc = db.get(Document, job.document_id)
        doc.status, doc.error = "processing", None
        job_id, doc_id, project_id = job.id, doc.id, job.project_id
        storage_name, kind, config, version = doc.storage_name, doc.kind, job.config, job.pipeline_version
        db.commit()
    try:
        started = time.perf_counter()
        expected = config.get("_embedding", {"id": "local:hash-v1:384"})
        if expected["id"] != embedding_id():
            raise ExtractionError("Embedding configuration changed after this job was queued. Rebuild the project index; no incompatible vectors were published.")
        if "_embedding" not in config:
            expected = profile()  # Recognized default lexical legacy job, now explicitly profiled.
        path = settings().storage_dir / storage_name
        sections, metadata = extract(path, kind)
        chunks = chunk_sections(sections, config["chunk_size"], config["overlap"], count_tokens=token_count if settings().embedding_provider == "semantic" else None)
        vectors = []
        embedding_started = time.perf_counter()
        for offset in range(0, len(chunks), 32):
            # Renew lease between batches. Token protects against stale workers.
            with SessionLocal() as db:
                lease = db.scalar(select(Job).where(Job.id == job_id, Job.lease_token == token).with_for_update())
                if not lease or lease.status != "processing":
                    return True
                lease.lease_until = time.time() + settings().job_lease_seconds
                db.commit()
            vectors.extend(embed([text for text, _ in chunks[offset:offset + 32]]))
        with SessionLocal() as db:
            project = db.scalar(select(Project).where(Project.id == project_id).with_for_update())
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            doc = db.get(Document, doc_id)
            if not project or not job or not doc or job.lease_token != token or job.status != "processing":
                return True
            if project.index_profile is None and project.index_generation == 0:
                project.index_profile = expected
            if project.index_generation != config.get("_generation", 0) or project.index_profile.get("id") != expected["id"]:
                job.status, job.error = "cancelled", "Index generation changed; stale output was discarded."
                db.commit()
                return True
            db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
            for i, ((text, locator), vector) in enumerate(zip(chunks, vectors, strict=True)):
                db.add(Chunk(project_id=project_id, document_id=doc_id, ordinal=i, text=text, locator=locator, embedding=vector, embedding_model=embedding_id(), pipeline_version=version))
            metadata.update({"embedding_profile": expected, "index_generation": config.get("_generation", 0), "embedding_ms": round((time.perf_counter()-embedding_started)*1000, 2), "indexing_ms": round((time.perf_counter()-started)*1000, 2), "chunking": "token-budget-aware" if settings().embedding_provider == "semantic" else "word-window"})
            doc.status, doc.chunk_count, doc.metadata_json, doc.error = "ready", len(chunks), metadata, None
            job.status, job.finished_at, job.error, job.lease_until = "succeeded", time.time(), None, None
            db.commit()
        log.info("ingestion_succeeded", extra={"job_id": job_id, "chunks": len(chunks)})
        from .observability import metric
        metric('ingestion_succeeded',(time.perf_counter()-started)*1000)
    except Exception as exc:
        retry=False
        safe = str(exc) if isinstance(exc, (ExtractionError, ProviderError)) else "Document processing failed. Check format or server logs, then retry."
        with SessionLocal() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            doc = db.get(Document, doc_id)
            if job and doc and job.lease_token == token:
                retry = isinstance(exc, ProviderError) and job.attempts < 3
                job.status = "queued" if retry else "failed"
                job.available_at = time.time() + 2 ** job.attempts
                job.error, job.lease_until = safe[:300], None
                job.finished_at = None if retry else time.time()
                doc.status, doc.error = job.status, job.error
                db.commit()
        log.warning("ingestion_failed", extra={"job_id": job_id, "error_type": type(exc).__name__})
        from .observability import metric
        metric('ingestion_retry' if retry else 'ingestion_failed')
    return True


def main():
    from .logging_config import configure_logging
    configure_logging()
    settings().storage_dir.mkdir(parents=True, exist_ok=True)
    if settings().embedding_provider == "semantic":
        from .embeddings import model
        try:
            model()  # Download/init before claiming a lease; persistent cache is shared with API.
        except ProviderError:
            log.warning("embedding_model_unavailable")
    log.info("worker_started")
    from .exports import run_once as export_once, cleanup
    from .parse_isolation import execute_parser
    from .observability import heartbeat
    parser_state={}
    try:
        probe=execute_parser(b'Probe','txt',probe='boundaries',outside='/etc/passwd') if __import__('sys').platform=='linux' else execute_parser(b'Probe','txt')
        if __import__('sys').platform=='linux' and not all(probe.get('blocked',{}).get(k) for k in ('outside_file','network','process')):raise RuntimeError('Parser control probe failed')
        parser_state=probe.get('restrictions',probe.get('metadata',{}).get('parser_containment',{}))
    except Exception:
        log.warning('parser_containment_unavailable')
    last_cleanup = 0.0
    import threading
    def publish_heartbeat():
        while True:
            try:heartbeat(parser_state)
            except Exception:log.warning('heartbeat_failed')
            time.sleep(5)
    threading.Thread(target=publish_heartbeat,daemon=True).start()
    while True:
        if time.time()-last_cleanup > 60:
            with SessionLocal() as db:
                cleanup(db); db.commit()
            last_cleanup=time.time()
        if not run_once() and not export_once():
            time.sleep(1)


if __name__ == "__main__":
    main()
