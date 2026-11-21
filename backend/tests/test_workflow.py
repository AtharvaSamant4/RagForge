import io
import time

from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import APIKey, Chunk, Document, Job, LoginSession
from app.worker import run_once


def pdf_bytes(text="Acme offers a 30 day refund period for all annual subscriptions."):
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(50, 750, text)
    canvas.save()
    return buffer.getvalue()


def ingest(owner, project, content=None, name="guide.pdf"):
    base = f"/v1/projects/{project['id']}"
    response = owner.post(base + "/documents", files={"file": (name, pdf_bytes() if content is None else content)})
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    assert run_once()
    documents = owner.get(base + "/documents").json()
    return base, next(d for d in documents if d["id"] == response.json()["id"])


def test_complete_pdf_api_evaluation_and_deletion(owner, project):
    base, doc = ingest(owner, project)
    assert doc["status"] == "ready" and doc["chunk_count"] > 0
    detail = owner.get(base + "/documents/" + doc["id"]).json()
    assert detail["metadata_json"]["pages"] == 1
    assert detail["chunks"][0]["locator"]["page"] == 1
    result = owner.post(base + "/query", json={"question": "What is the refund period?"})
    assert result.status_code == 200, result.text
    answer = result.json()
    assert not answer["refused"] and "30 day" in answer["answer"]
    assert answer["citations"][0]["document_id"] == doc["id"]
    assert answer["citations"][0]["quote"] in answer["citations"][0]["text"]
    assert owner.get(base + "/conversations/" + answer["conversation_id"]).json()[0]["question"] == "What is the refund period?"
    unsupported = owner.post(base + "/query", json={"question": "Who won the Martian election in 2050?"}).json()
    assert unsupported["refused"] and not unsupported["citations"]
    key = owner.post(base + "/keys", json={"name": "Backend", "scopes": ["query", "read"]}).json()
    with TestClient(app) as external:
        assert external.post(base + "/query", headers={"Authorization": "Bearer " + key["secret"]}, json={"question": "What is the refund period?"}).status_code == 200
        assert external.get(base + "/status", headers={"Authorization": "Bearer " + key["secret"]}).json()["ready"]
        assert external.post(base + "/documents", headers={"Authorization": "Bearer " + key["secret"]}, files={"file": ("x.txt", b"test")}).status_code == 403
    assert "secret" not in str(owner.get(base + "/keys").json())
    with SessionLocal() as db:
        assert key["secret"] not in db.scalar(select(APIKey)).token_hash
        assert not db.scalar(select(LoginSession)).token_hash.startswith("rf_")
    case = owner.post(base + "/evaluation/cases", json={"question": "What is the refund period?", "relevant_document_ids": [doc["id"]], "expected_answer": "30 day refund period"})
    assert case.status_code == 201, case.text
    owner.post(base + "/evaluation/cases", json={"question": "Who won the Martian election?", "expect_refusal": True})
    run = owner.post(base + "/evaluation/runs", json={})
    assert run.status_code == 201, run.text
    evaluation = run.json()["result"]
    assert evaluation["case_count"] == 2
    assert evaluation["metrics"]["recall_at_k"] == 1
    assert evaluation["metrics"]["refusal_correct"] == 1
    assert evaluation["semantic_faithfulness"] == "not assessed"
    assert owner.get(base + "/usage").json()["queries"] == 3
    assert owner.delete(base + "/documents/" + doc["id"]).status_code == 200
    after = owner.post(base + "/query", json={"question": "What is the refund period?"}).json()
    assert after["refused"] and not after["retrieved"]
    assert owner.get(base + "/evaluation/runs").json() == []
    with SessionLocal() as db:
        assert not db.scalar(select(Chunk).where(Chunk.document_id == doc["id"]))
        assert not db.get(Document, doc["id"])
        assert not db.scalar(select(Job).where(Job.document_id == doc["id"]))


def test_tenant_project_and_conversation_isolation(owner, project):
    base, doc = ingest(owner, project)
    result = owner.post(base + "/query", json={"question": "What is the refund period?"}).json()
    other = owner.post("/v1/projects", json={"name": "Other"}).json()
    other_base = "/v1/projects/" + other["id"]
    assert owner.get(other_base + "/documents/" + doc["id"]).status_code == 404
    assert owner.post(other_base + "/query", json={"question": "Refund period", "conversation_id": result["conversation_id"]}).status_code == 404
    key = owner.post(other_base + "/keys", json={"name": "Other"}).json()
    assert owner.get(base, headers={"Authorization": "Bearer " + key["secret"]}).status_code == 404
    with TestClient(app, headers={"origin": "http://localhost:3000"}) as attacker:
        attacker.post("/v1/auth/register", json={"email": "attacker@example.com", "password": "attacker-password-long"})
        for suffix in ("", "/documents", "/jobs", "/keys", "/manifest", "/conversations", "/evaluation/runs"):
            assert attacker.get(base + suffix).status_code == 404
        assert attacker.post(base + "/query", json={"question": "Refund period"}).status_code == 404
        assert attacker.delete(base + "/documents/" + doc["id"]).status_code == 404
        assert attacker.get("/v1/projects").json() == []


def test_failed_job_recovery_and_expired_lease(owner, project):
    base, doc = ingest(owner, project, b"%PDF-1.7\nnot a valid pdf")
    assert doc["status"] == "failed" and doc["error"]
    job = owner.get(base + "/jobs").json()[0]
    assert job["status"] == "failed"
    with SessionLocal() as db:
        stored = db.get(Document, doc["id"])
        (settings().storage_dir / stored.storage_name).write_bytes(pdf_bytes())
    assert owner.post(base + "/jobs/" + job["id"] + "/retry").status_code == 200
    assert run_once()
    assert owner.get(base + "/documents").json()[0]["status"] == "ready"
    owner.post(base + "/reindex")
    with SessionLocal() as db:
        pending = db.scalar(select(Job).where(Job.status == "queued"))
        pending.status, pending.lease_until, pending.attempts = "processing", time.time() - 1, 1
        db.commit()
    assert run_once()
    assert owner.get(base + "/documents").json()[0]["status"] == "ready"
    assert not run_once()


def test_csrf_login_logout_and_revocation(owner, project):
    assert owner.post("/v1/projects", json={"name": "bad"}, headers={"origin": "https://evil.example"}).status_code == 403
    base = "/v1/projects/" + project["id"]
    key = owner.post(base + "/keys", json={"name": "revoke"}).json()
    assert owner.delete(base + "/keys/" + key["id"]).status_code == 200
    assert owner.get(base, headers={"Authorization": "Bearer " + key["secret"]}).status_code == 401
    assert owner.post("/v1/auth/logout").status_code == 200
    assert owner.get(base).status_code == 401
    assert owner.post("/v1/auth/login", json={"email": "owner@example.com", "password": "wrong-password-long"}).status_code == 401
    assert owner.post("/v1/auth/login", json={"email": "owner@example.com", "password": "test-password-very-long"}).status_code == 200


def test_public_widget_capability_and_revocation(owner, project):
    base, _ = ingest(owner, project)
    public = "/v1/public/" + project["id"]
    assert owner.get(public + "/config?token=invalid").status_code == 404
    result = owner.put(base + "/widget", json={"enabled": True, "allowed_origins": ["https://example.com"]}).json()
    token = result["token"]
    with TestClient(app) as visitor:
        assert visitor.post(public + "/query", headers={"Authorization": "Bearer " + token}, json={"question": "What is the refund period?"}).json()["citations"]
        assert visitor.get(base + "/documents", headers={"Authorization": "Bearer " + token}).status_code == 401
        assert visitor.post(public + "/query", headers={"Authorization": "Bearer " + token, "Origin": "https://evil.example"}, json={"question": "Refund period"}).status_code == 403
    owner.put(base + "/widget", json={"enabled": False})
    assert owner.get(public + "/config?token=" + token).status_code == 404


def test_sse_and_synthetic_evaluation_are_real_and_labeled(owner, project):
    base, _ = ingest(owner, project)
    stream = owner.post(base + "/query/stream", json={"question": "What is the refund period?"})
    assert stream.status_code == 200 and "text/event-stream" in stream.headers["content-type"]
    assert "event: sources" in stream.text and "event: delta" in stream.text and "event: done" in stream.text
    assert owner.post(base + "/evaluation/generate").json()["created"] > 0
    assert all(not c["verified"] and c["origin"] == "synthetic" for c in owner.get(base + "/evaluation/cases").json())
    assert owner.post(base + "/evaluation/runs", json={}).status_code == 409
    assert owner.post(base + "/evaluation/runs", json={"include_unverified": True}).json()["result"]["synthetic_count"] > 0


def test_pipeline_reindex_and_all_retrieval_strategies(owner, project):
    base, _ = ingest(owner, project)
    config = project["pipeline"]
    for strategy in ("keyword", "vector", "hybrid"):
        config["strategy"] = strategy
        assert owner.put(base + "/pipeline", json=config).status_code == 200
        assert not owner.post(base + "/query", json={"question": "Refund period"}).json()["refused"]
    config["chunk_size"] = 100
    owner.put(base + "/pipeline", json=config)
    assert owner.get(base + "/pipeline").json()["reindex_required"]
    assert owner.post(base + "/reindex").json()["queued"] == 1
    assert owner.post(base + "/reindex").json()["queued"] == 0
    assert run_once()
    assert not owner.get(base + "/pipeline").json()["reindex_required"]
    config["overlap"] = 110
    assert owner.put(base + "/pipeline", json=config).status_code == 422


def test_project_rename_and_cascade_delete(owner, project):
    base, doc = ingest(owner, project)
    assert owner.patch(base, json={"name": "Renamed"}).json()["name"] == "Renamed"
    with SessionLocal() as db:
        path = settings().storage_dir / db.get(Document, doc["id"]).storage_name
    assert path.exists()
    assert owner.delete(base).status_code == 200
    assert not path.exists()
    assert owner.get(base).status_code == 404
