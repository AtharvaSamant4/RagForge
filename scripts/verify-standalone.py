"""Real independent-runtime acceptance test. Leaves its generated app for inspection.

Only --stop-source stops services, restricted to an isolated QA Compose project.
Never removes volumes. Source services are restored in finally.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile

import httpx

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument("--source",default="http://localhost:8030")
parser.add_argument("--origin",default="http://localhost:3030")
parser.add_argument("--port",type=int,default=8020)
parser.add_argument("--stop-source",choices=["ragforge-m3","ragforge-m4","ragforge-export-ci"])
parser.add_argument("--prepare-only",action="store_true")
parser.add_argument("--directory")
parser.add_argument("--archive",help="Use the ZIP downloaded by a real browser workflow")
parser.add_argument("--comparison",help="Browser workflow's export-before.json evidence")
parser.add_argument("--output",default="artifacts/standalone-acceptance.json")
args=parser.parse_args()
report={"created_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"source":args.source,"questions":[]}


def command(argv,cwd=ROOT):
    env=os.environ.copy()
    for key in ("API_PORT","WEB_PORT","APP_ORIGINS","COMPOSE_PROJECT_NAME"):env.pop(key,None)
    if cwd==ROOT:
        from urllib.parse import urlparse
        env.update(API_PORT=str(urlparse(args.source).port),WEB_PORT=str(urlparse(args.origin).port),APP_ORIGINS=args.origin)
    else:env["STANDALONE_URL"]=f"http://localhost:{args.port}"
    subprocess.run(argv,cwd=cwd,env=env,check=True)


def wait(check,seconds=240):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:result=check()
        except httpx.HTTPError:result=None
        if result:return result
        time.sleep(2)
    raise TimeoutError("Expected runtime state did not become ready")


def ready(client):
    r=client.get("/v1/status");r.raise_for_status()
    state=r.json()
    failed=[d for d in state["documents"] if d["status"]=="failed"]
    if failed:raise AssertionError(failed)
    return state if state["documents"] and all(d["status"]=="ready" for d in state["documents"]) else None


def query(client,question):
    r=client.post("/v1/query",json={"question":question});r.raise_for_status()
    return r.json()


directory=Path(args.directory).resolve() if args.directory else Path(tempfile.mkdtemp(prefix="standalone-",dir=ROOT/"artifacts"))
if args.archive:
    data=Path(args.archive).read_bytes()
    report=json.loads(Path(args.comparison).read_text(encoding="utf-8"))
    report.update(created_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),source=args.source,questions=[],archive_bytes=len(data),archive_sha256=hashlib.sha256(data).hexdigest())
    if report.get("export"):
        assert report["export"]["sha256"]==report["archive_sha256"]
        report["generation_ms"]=report["export"]["generation_ms"]
    with zipfile.ZipFile(__import__('io').BytesIO(data)) as archive:
        assert archive.testzip() is None
        assert sum(info.file_size for info in archive.infolist())<120*1024**2
        for info in archive.infolist():
            assert (directory/info.filename).resolve().is_relative_to(directory)
            assert (info.external_attr>>16)&0o170000==0o100000
        archive.extractall(directory)
    command([sys.executable,"scripts/init.py","--port",str(args.port)],directory)
    (directory/"acceptance-input.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
elif not args.directory:
    with httpx.Client(base_url=args.source,headers={"Origin":args.origin},timeout=120) as hosted:
        r=hosted.post("/v1/auth/register",json={"email":f"export-{secrets.token_hex(8)}@example.com","password":secrets.token_urlsafe(20)})
        r.raise_for_status()
        r=hosted.post("/v1/projects",json={"name":"Independent Acme Knowledge"});r.raise_for_status()
        base="/v1/projects/"+r.json()["id"]
        pipeline=r.json()["pipeline"]|{"strategy":"hybrid","auto":False}
        hosted.put(base+"/pipeline",json=pipeline).raise_for_status()
        with (ROOT/"samples/acme-handbook.pdf").open("rb") as source:
            r=hosted.post(base+"/documents",files={"file":("acme-handbook.pdf",source)})
        r.raise_for_status();document=r.json()
        def source_ready():
            r=hosted.get(base+"/documents");r.raise_for_status()
            doc=r.json()[0]
            if doc["status"]=="failed":raise AssertionError(doc)
            return doc if doc["status"]=="ready" else None
        wait(source_ready)
        known=["What is the refund period?","How long does a refund take?","Who won the Martian election in 2050?"]
        before=[]
        for question in known:
            r=hosted.post(base+"/query",json={"question":question});r.raise_for_status()
            before.append({"question":question,"result":r.json()})
        start=time.perf_counter()
        r=hosted.post(base+"/exports",json={"mode":"snapshot","document_ids":[document["id"]],"acknowledge_copy":True});r.raise_for_status()
        job_id=r.json()["id"]
        def exported():
            r=hosted.get(base+"/exports/"+job_id);r.raise_for_status()
            job=r.json()
            if job["status"]=="failed":raise AssertionError(job)
            return job if job["status"]=="ready" else None
        job=wait(exported)
        r=hosted.get(base+"/exports/"+job_id+"/download");r.raise_for_status()
        assert hashlib.sha256(r.content).hexdigest()==job["sha256"]
        report.update(export_wall_ms=round((time.perf_counter()-start)*1000,2),generation_ms=job["generation_ms"],archive_bytes=len(r.content),archive_sha256=job["sha256"],source_project_id=base.split("/")[-1],before=before)
        archive_path=directory/"application.zip";archive_path.write_bytes(r.content)
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            for info in archive.infolist():
                target=directory/info.filename
                assert target.resolve().is_relative_to(directory) and not info.filename.startswith("/")
                assert (info.external_attr>>16)&0o170000==0o100000
            archive.extractall(directory)
    command([sys.executable,"scripts/init.py","--port",str(args.port)],directory)
    (directory/"acceptance-input.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
else:
    report=json.loads((directory/"acceptance-input.json").read_text(encoding="utf-8"))
report["extracted_directory"]=str(directory)
if args.prepare_only:
    print("Prepared independent application:",directory)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    raise SystemExit(0)

started=time.perf_counter()
command(["docker","compose","up","--build","-d"],directory)
report["compose_build_start_seconds"]=round(time.perf_counter()-started,3)
started=time.perf_counter()
command(["docker","compose","exec","-T","api","python","-m","app.model_cache"],directory)
report["prefetch_or_cached_init_seconds"]=round(time.perf_counter()-started,3)
key=(directory/".standalone-key").read_text().strip()
with httpx.Client(base_url=f"http://localhost:{args.port}",headers={"Authorization":"Bearer "+key},timeout=120) as client:
    report["initial_ready_status"]=wait(lambda:ready(client))
    assert httpx.get(f"http://localhost:{args.port}/v1/config").status_code==401
    assert client.get("/v1/config",headers={"Authorization":"Bearer incorrect"}).status_code==401
    for row in report["before"]:
        result=query(client,row["question"])
        assert result["refused"]==row["result"]["refused"]
        assert sorted((c["document_name"],c["quote"]) for c in result["citations"])==sorted((c["document_name"],c["quote"]) for c in row["result"]["citations"])
        report["questions"].append({"question":row["question"],"result":result})
    first=report["questions"][0]["result"]
    assert "30 day" in first["answer"] and any(c["document_name"]=="acme-handbook.pdf" and "30 day" in c["quote"] for c in first["citations"])
    stopped=False
    try:
        if args.stop_source:
            command(["docker","compose","-p",args.stop_source,"stop"])
            stopped=True
            try:
                httpx.get(args.source+"/health",timeout=3)
            except httpx.HTTPError:pass
            else:raise AssertionError("Source API still responds after stop")
            result=query(client,"What is the refund period?")
            assert "30 day" in result["answer"] and result["citations"]
            report["source_stopped_query"]=result
    finally:
        if stopped:command(["docker","compose","-p",args.stop_source,"up","-d"])
    command(["docker","compose","restart"],directory)
    wait(lambda:client.get("/health").status_code==200)
    report["restart_status"]=wait(lambda:ready(client))
    after=query(client,"What is the refund period?")
    assert [(c["chunk_id"],c["quote"]) for c in after["citations"]]==[(c["chunk_id"],c["quote"]) for c in first["citations"]]
    report["restart_query"]=after
    report["runtime_status"]=client.get("/v1/status").json()
command(["node","scripts/example.mjs"],directory)
curl_result=subprocess.check_output(["curl","--fail","--silent",f"http://localhost:{args.port}/v1/query","--header","@-","-H","Content-Type: application/json","--data",json.dumps({"question":"What is the refund period?"})],input="Authorization: Bearer "+key+"\n",text=True)
assert "30 day" in json.loads(curl_result)["answer"]
report["curl_client"]="passed"
report["database_evidence"]=subprocess.check_output(["docker","compose","exec","-T","db","psql","-U","standalone","-d","standalone","-tAc","SELECT current_database(),(SELECT count(*) FROM chunks),(SELECT count(*) FROM pg_indexes WHERE indexname='standalone_chunks_vector');"],cwd=directory,text=True).strip()
assert report["database_evidence"].startswith("standalone|") and report["database_evidence"].endswith("|1")
report["containers"]=subprocess.check_output(["docker","compose","ps","--format","json"],cwd=directory,text=True)
report["resources"]=subprocess.check_output(["docker","stats","--no-stream","--format","{{json .}}",*subprocess.check_output(["docker","compose","ps","-q"],cwd=directory,text=True).split()],text=True)
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
Path(args.output).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print("PASS: standalone export, authentication, citation consistency, isolated source shutdown, restart and persistent index. Report:",args.output)
