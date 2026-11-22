"""Measure real concurrent HTTP behavior without paid generation or shared test data."""
import argparse
import json
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

parser=argparse.ArgumentParser()
parser.add_argument("--url",default="http://localhost:8010")
parser.add_argument("--origin",default="http://localhost:3010")
parser.add_argument("--output",default="benchmarks/results/http-performance.json")
args=parser.parse_args()
client=httpx.Client(base_url=args.url,headers={"Origin":args.origin},timeout=120)
assert client.get("/health").json()["embedding_provider"]=="semantic", "Use the unpaid semantic deployment for this measurement"
response=client.post("/v1/auth/register",json={"email":f"perf-{uuid.uuid4().hex}@example.com","password":uuid.uuid4().hex});response.raise_for_status()
response=client.post("/v1/projects",json={"name":"Disposable concurrency benchmark"});response.raise_for_status()
project=response.json();base="/v1/projects/"+project["id"]
try:
    corpus=Path(__file__).resolve().parents[1]/"benchmarks/corpus/operations.md"
    text="\n\n".join(f"# Facility {i}\n"+corpus.read_text() for i in range(12))
    response=client.post(base+"/documents",files={"file":("load.md",text.encode())});response.raise_for_status();doc=response.json()
    started=time.perf_counter();processing_seen=False
    while time.perf_counter()-started<30:
        response=client.get(base+"/documents/"+doc["id"]);response.raise_for_status();state=response.json()
        if state["status"]=="processing":processing_seen=True;break
        if state["status"] in ("ready","failed"):break
        time.sleep(.5)
    def health(_):
        start=time.perf_counter();response=client.get("/health");return {"status":response.status_code,"ms":round((time.perf_counter()-start)*1000,2)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        health_results=list(pool.map(health,range(16)))
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        response=client.get(base+"/documents/"+doc["id"]);response.raise_for_status();state=response.json()
        if state["status"] in ("ready","failed"):break
        time.sleep(1)
    assert state["status"]=="ready",state
    questions=["What should I do if my device recovery phrase is lost?","Which checks precede service restoration?","What checks follow restoring the service?"]
    def query(i):
        start=time.perf_counter();response=client.post(base+"/query",json={"question":questions[i%len(questions)]});result=response.json();return {"status":response.status_code,"ms":round((time.perf_counter()-start)*1000,2),"retrieval_ms":result.get("retrieval_latency_ms"),"refused":result.get("refused"),"citations":len(result.get("citations",[]))}
    start=time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(query,range(24)))
    wall=time.perf_counter()-start
    assert all(r["status"]==200 for r in results),results
    metrics={"schema_version":"1.0","concurrency":8,"requests":24,"wall_seconds":round(wall,4),"requests_per_second":round(24/wall,3),"http_p50_ms":statistics.median(r["ms"] for r in results),"http_p95_ms":sorted(r["ms"] for r in results)[22],"processing_observed_before_health_load":processing_seen,"health_during_indexing":health_results,"indexing_metadata":state["metadata_json"],"query_results":results,"notes":"Same three questions repeat across 24 requests; the bounded model cache is enabled. Health requests began immediately after processing was observed, but indexing may finish during that burst. This is a local measurement, not a production capacity claim."}
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(metrics,indent=2)+"\n")
    print(json.dumps({k:metrics[k] for k in ("requests","concurrency","requests_per_second","http_p50_ms","http_p95_ms","processing_observed_before_health_load")}))
finally:
    client.delete(base);client.close()
