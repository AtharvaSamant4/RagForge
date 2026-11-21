import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.db import SessionLocal, engine
from app.models import Chunk, Document, Job
from app import worker
from test_workflow import pdf_bytes


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Multiple workers require PostgreSQL")
def test_postgres_workers_claim_distinct_jobs(owner, project):
    base = "/v1/projects/" + project["id"]
    for i in range(2):
        result = owner.post(base + "/documents", files={"file": (f"source-{i}.pdf", pdf_bytes())})
        assert result.status_code == 202
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert all(workers.map(lambda _: worker.run_once(), range(2)))
    with SessionLocal() as db:
        jobs = db.scalars(select(Job)).all()
        assert len(jobs) == 2
        assert all(j.status == "succeeded" and j.attempts == 1 for j in jobs)
        assert len(db.scalars(select(Chunk)).all()) == 2


def test_deleting_during_processing_cannot_resurrect_chunks(owner, project, monkeypatch):
    base = "/v1/projects/" + project["id"]
    result = owner.post(base + "/documents", files={"file": ("source.pdf", pdf_bytes())})
    doc_id = result.json()["id"]
    started, resume = threading.Event(), threading.Event()
    real_embed = worker.embed
    def paused_embed(texts):
        started.set()
        assert resume.wait(timeout=15), "Test did not resume the worker"
        return real_embed(texts)
    monkeypatch.setattr(worker, "embed", paused_embed)
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(worker.run_once)
        try:
            assert started.wait(timeout=15), "Worker did not reach embedding"
            assert owner.delete(base + "/documents/" + doc_id).status_code == 200
        finally:
            resume.set()
        assert future.result(timeout=15)
    with SessionLocal() as db:
        assert db.get(Document, doc_id) is None
        assert db.scalar(select(Chunk).where(Chunk.document_id == doc_id)) is None
        assert db.scalar(select(Job).where(Job.document_id == doc_id)) is None
