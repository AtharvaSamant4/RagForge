"""Exercise real HTTP API and worker. Requires a running local stack.

Creates and deletes its own project. Prints no credentials.
"""
import argparse
import time
import uuid
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8000")
parser.add_argument("--origin", default="http://localhost:3000")
args = parser.parse_args()
client = httpx.Client(base_url=args.url, headers={"Origin": args.origin}, timeout=120)
password = uuid.uuid4().hex
email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"


def check(response, status=200):
    assert response.status_code == status, f"HTTP {response.status_code}: {response.text[:400]}"
    return response.json()


check(client.post("/v1/auth/register", json={"email": email, "password": password}), 201)
p = check(client.post("/v1/projects", json={"name": "HTTP smoke test"}), 201)
base = "/v1/projects/" + p["id"]
try:
    file = Path(__file__).resolve().parents[1] / "samples" / "acme-handbook.pdf"
    with file.open("rb") as source:
        d = check(client.post(base + "/documents", files={"file": (file.name, source, "application/pdf")}), 202)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = check(client.get(base + "/documents/" + d["id"]))
        if state["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    assert state["status"] == "ready", state
    question = {"question": "What is the refund period?"}
    result = check(client.post(base + "/query", json=question))
    assert "30 day" in result["answer"] and result["citations"]
    key = check(client.post(base + "/keys", json={"name": "Smoke", "scopes": ["read", "query"]}), 201)
    with httpx.Client(base_url=args.url, headers={"Authorization": "Bearer " + key["secret"]}, timeout=120) as external:
        assert check(external.post(base + "/query", json=question))["citations"]
        assert check(external.get(base + "/status"))["ready"]
    assert check(client.post(base + "/query", json={"question": "Who won the Martian election in 2050?"}))["refused"]
    check(client.post(base + "/evaluation/cases", json={"question": question["question"], "relevant_document_ids": [d["id"]]}), 201)
    evaluation = check(client.post(base + "/evaluation/runs", json={}), 201)
    assert evaluation["result"]["metrics"]["recall_at_k"] == 1
    check(client.delete(base + "/documents/" + d["id"]))
    assert check(client.post(base + "/query", json=question))["refused"]
    print("PASS: PDF upload -> durable worker -> index -> cited answer -> external authenticated API -> refusal -> measured evaluation -> deletion cleanup")
finally:
    check(client.delete(base))
    client.close()
