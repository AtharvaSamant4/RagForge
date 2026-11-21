"""HTTP checks for the Next.js proxy, widget delivery and all integration clients.

Requires a running web/API/worker and the generated sample PDF. No browser is used.
"""
import json
import subprocess
import time
import uuid
from pathlib import Path

import httpx

origin = "http://localhost:3000"
web = httpx.Client(base_url=origin, headers={"Origin": origin}, timeout=120)
assert web.get("/").status_code == 200
assert web.get("/widget.js").status_code == 200
assert web.get("/embed-client.js").status_code == 200
assert web.get("/embed.css").status_code == 200
assert web.get("/api/health").json()["status"] == "ok"
assert web.get("/api/docs").status_code == 200
schema = web.get("/openapi.json").json()
assert schema["servers"][0]["url"] == "/api"
assert "ProjectKey" in schema["components"]["securitySchemes"]
assert web.post("/api/v1/auth/register", json={"email": f"web-{uuid.uuid4().hex[:12]}@example.com", "password": uuid.uuid4().hex}).status_code == 201
p = web.post("/api/v1/projects", json={"name": "Web integration checks"}).json()
base = "/api/v1/projects/" + p["id"]
try:
    source = Path(__file__).resolve().parents[1] / "samples/acme-handbook.pdf"
    with source.open("rb") as file:
        doc = web.post(base + "/documents", files={"file": (source.name, file)}).json()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        state = web.get(base + "/documents/" + doc["id"]).json()
        if state["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    assert state["status"] == "ready", state
    key = web.post(base + "/keys", json={"name": "Integration clients"}).json()["secret"]
    url = "http://localhost:8000/v1/projects/" + p["id"] + "/query"
    data = {"question": "What is the refund period?"}
    # Pass credentials via stdin to child clients, never in command arguments or output.
    import os
    child_env = {**os.environ, "RAGFORGE_API_KEY": key, "RAGFORGE_QUERY_URL": url}
    node = subprocess.run(["node", "--input-type=module", "-"], input="""
const r = await fetch(process.env.RAGFORGE_QUERY_URL, {method:'POST',headers:{Authorization:`Bearer ${process.env.RAGFORGE_API_KEY}`,'Content-Type':'application/json'},body:JSON.stringify({question:'What is the refund period?'})});
if (!r.ok) throw new Error(`HTTP ${r.status}`);
const d = await r.json(); if(d.refused || !d.citations.length) throw new Error('No grounded result');
console.log('JavaScript client passed');
""", text=True, capture_output=True, env=child_env, check=True)
    print(node.stdout.strip())
    curl_config = f'url = "{url}"\nheader = "Authorization: Bearer {key}"\nheader = "Content-Type: application/json"\ndata = "{{\\"question\\":\\"What is the refund period?\\"}}"\n'
    curl = subprocess.run(["curl.exe" if os.name == "nt" else "curl", "--silent", "--show-error", "--fail", "--config", "-"], input=curl_config, text=True, capture_output=True, check=True)
    assert json.loads(curl.stdout)["citations"]
    print("cURL client passed")
    published = web.put(base + "/widget", json={"enabled": True, "title": "<script>alert('test')</script>", "allowed_origins": ["http://localhost:4000"]}).json()
    frame = web.get("/embed", params={"project": p["id"]})
    assert frame.status_code == 200, frame.text
    assert "frame-ancestors http://localhost:4000" in frame.headers["content-security-policy"]
    assert published["token"] not in frame.text
    assert "<script>alert('test')</script>" not in frame.text
    assert frame.headers["referrer-policy"] == "no-referrer"
    token = published["token"]
    with httpx.Client(base_url=origin, timeout=120) as visitor:
        config = visitor.get("/api/v1/public/" + p["id"] + "/config", headers={"Authorization": "Bearer " + token})
        assert config.status_code == 200
        public = visitor.post("/api/v1/public/" + p["id"] + "/query", headers={"Authorization": "Bearer " + token}, json=data)
        assert public.status_code == 200 and public.json()["citations"]
    web.put(base + "/widget", json={"enabled": False})
    assert web.get("/embed", params={"project": p["id"]}).status_code == 404
    print("PASS: web routes, same-origin API proxy, PDF upload, JS/cURL clients, widget CSP, escaped configuration, public query and revocation")
finally:
    web.delete(base)
    web.close()
