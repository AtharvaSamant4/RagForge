"""Bounded final HTTP workload, aligned to one rate window; public sample only."""
import concurrent.futures
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time
import httpx
ROOT=Path(__file__).resolve().parents[1]
ORIGIN='https://localhost:8443'
creds=json.loads((ROOT/'artifacts/m4-private-credentials.json').read_text())
questions=['What is the refund period?','How long does a refund take?','Who won the Martian election in 2050?']
with httpx.Client(base_url=ORIGIN+'/api',verify=False,headers={'Origin':ORIGIN},timeout=120) as client:
    response=client.post('/v1/auth/login',json={'email':creds['recovery_email'],'password':creds['recovery_password']});response.raise_for_status()
    base='/v1/projects/'+creds['recovery_project']
    response=client.post(base+'/keys',json={'name':'Final bounded query load'});response.raise_for_status();key=response.json()['secret']
    headers={'Authorization':'Bearer '+key}
    # Bound alignment wait to <50 seconds, so all three stages use a single window.
    while time.time()%60>10:time.sleep(.5)
    window=int(time.time()//60)
    for question in questions:
        response=client.post(base+'/query',json={'question':question},headers=headers);response.raise_for_status()
    def query(i):
        start=time.perf_counter();r=client.post(base+'/query',json={'question':questions[i%3]},headers=headers)
        return {'status':r.status_code,'ms':(time.perf_counter()-start)*1000}
    rows=[]
    for concurrency,count in [(1,12),(4,24),(8,24)]:
        start=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:results=list(pool.map(query,range(count)))
        elapsed=time.perf_counter()-start;latencies=sorted(r['ms'] for r in results)
        rows.append({'concurrency':concurrency,'requests':count,'seconds':round(elapsed,3),'responses_per_second_including_rejections':round(count/elapsed,3),'median_ms':round(statistics.median(latencies),2),'p95_ms':round(latencies[math.ceil(count*.95)-1],2),'status_counts':{str(code):sum(r['status']==code for r in results) for code in {r['status'] for r in results}}})
    endwindow=int(time.time()//60)
    assert all(code in ('200','429') for row in rows for code in row['status_counts'])
    if endwindow==window:assert sum(row['status_counts'].get('429',0) for row in rows)==3
    health=client.get('/health').json()
resources=subprocess.run(['docker','stats','--no-stream','--format','{{json .}}','ragforge-m4-alpha-api-1','ragforge-m4-alpha-worker-1','ragforge-m4-alpha-db-1'],capture_output=True,text=True,check=True).stdout
report={'created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'platform':platform.platform(),'cpu_logical_count':os.cpu_count(),'embedding_profile':health['embedding_profile']['id'],'protocol':'CPU MiniLM/extractive, one public sample PDF/project/fresh project key; 3 warmups then 60 measured JSON queries. Real TLS proxy/auth/DB/metrics overhead. Nearest-rank P95. All stages run once, no deliberate competing workload; other historical stacks remain running and host contention is not fully controlled. No production capacity claim.','same_fixed_minute_window':window==endwindow,'api_key_limit_per_minute':60,'runs':rows,'resource_snapshots':resources}
p=ROOT/'docs/qa/m4-query-load-final.json';p.write_text(json.dumps(report,indent=2)+'\n');print('PASS: final bounded concurrent query load and quota behavior. Evidence:',p)
