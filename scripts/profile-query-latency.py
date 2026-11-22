"""Bounded M4/M5 comparison in fresh, equally limited local Compose namespaces.

Requires the verified M4 images and current M5 images. No quotas are raised.
Other historical stacks remain intact; this controls deployments/workloads,
not physical host exclusivity. Results never establish production capacity.
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import secrets
import statistics
import subprocess
import sys
import time
import httpx
import psutil

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline-prefix',default='ragforge-m4')
parser.add_argument('--candidate-prefix',default='ragforge-m5-alpha')
parser.add_argument('--repeats',type=int,default=3,choices=[1,2,3])
parser.add_argument('--transport',choices=['ipv4','host-default'],default='ipv4',help='IPv4 retains the HTTPS host identity and avoids measured Windows ::1 refusal; host-default reproduces the original client')
args=parser.parse_args()
questions=['What is the refund period?','How long does a refund take?','Who won the Martian election in 2050?']
report={'schema_version':1,'baseline_commit':'04f6ef26420fe188aba93c30de5b07ac95ca31ad','platform':platform.platform(),'logical_cpus':os.cpu_count(),'host_memory_total':psutil.virtual_memory().total,'protocol':'Fresh isolated DB/source/model volumes per version; identical public one-page PDF, pinned MiniLM/hybrid/extractive, TLS proxy, API/worker 2 CPU and 1 GiB each, DB 1 CPU/512 MiB. Three question types. Model-file download/setup outside timed queries. Each measured stage uses a fresh key under the unchanged 60/minute cap. Cold API process and warm text-cache cases separate. Repeated runs and an actual competing ingestion probe; quota responses measured separately. Other historical stacks remain running; physical host activity is inventoried, not exclusively controlled. No production capacity extrapolation.','runs':[],'cold':[],'worker_interference':[]}


def command(argv,**kwargs):
    result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,**kwargs)
    if result.returncode:raise RuntimeError('Profiling command failed: '+result.stderr[-1000:])
    return result.stdout.strip()


def wait(fn,seconds=300):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except httpx.HTTPError:pass
        time.sleep(1)
    raise TimeoutError('Profile namespace did not reach required state')


def checked(response):response.raise_for_status();return response.json()
def p95(values):return sorted(values)[math.ceil(len(values)*.95)-1] if values else None


def stats(container):
    data=json.loads(command(['docker','inspect',container]))[0]
    raw=command(['docker','exec',container,'python','-c',"import json,pathlib; p=pathlib.Path('/sys/fs/cgroup'); print(json.dumps({n:(p/n).read_text() for n in ['cpu.stat','memory.current','memory.peak'] if (p/n).exists()}))"])
    return {'container':container,'memory_limit':data['HostConfig']['Memory'],'cpu_limit':data['HostConfig']['NanoCpus']/1e9,'cgroup':json.loads(raw),'host_cpu_percent':psutil.cpu_percent(interval=.2),'host_available_memory':psutil.virtual_memory().available}


class Deployment:
    def __init__(self,name,prefix,origin,api,web):
        self.name=name;self.origin=origin;self.project='ragforge-m5-profile-'+name+'-'+secrets.token_hex(3)
        env=ROOT/'artifacts'/('m5-'+self.project+'.env')
        command([sys.executable,'scripts/init-alpha.py','--file',str(env),'--origin',origin])
        env.write_text(env.read_text().replace('API_PORT=8040','API_PORT='+str(api)).replace('WEB_PORT=3040','WEB_PORT='+str(web)))
        override=ROOT/'artifacts'/('m5-'+self.project+'-images.json')
        override.write_text(json.dumps({'services':{service:{'image':prefix+'-'+service} for service in ('api','worker','web')}}))
        self.compose=['docker','compose','--env-file',str(env),'-p',self.project,'-f','compose.yaml','-f','compose.alpha.yaml','-f',str(override)]
        for service in ('api','worker','web'):command(['docker','image','inspect',prefix+'-'+service])
        command(self.compose+['up','--no-build','-d'])
        limits=httpx.Limits(max_connections=16,max_keepalive_connections=16)
        transport=httpx.HTTPTransport(local_address='0.0.0.0',verify=False,limits=limits) if args.transport=='ipv4' else None
        self.client=httpx.Client(base_url=origin+'/api',verify=False,timeout=120,headers={'Origin':origin},limits=limits,transport=transport)
        wait(lambda:self.client.get('/ready').status_code==200)
        email='engineering-profile-'+secrets.token_hex(4)+'@example.com';password=secrets.token_urlsafe(32)
        command(self.compose+['exec','-T','api','python','-m','app.ops','bootstrap-admin','--email',email,'--password-stdin'],input=password+'\n')
        checked(self.client.post('/v1/auth/login',json={'email':email,'password':password}))
        self.email=email
        project=checked(self.client.post('/v1/projects',json={'name':'Public profiling sample'}));self.base='/v1/projects/'+project['id'];self.project_id=project['id']
        checked(self.client.put(self.base+'/pipeline',json={**project['pipeline'],'auto':False,'strategy':'hybrid'}))
        checked(self.client.post(self.base+'/documents',files={'file':('acme-handbook.pdf',(ROOT/'samples/acme-handbook.pdf').read_bytes())}))
        wait(lambda:all(d['status']=='ready' for d in checked(self.client.get(self.base+'/documents'))))
        self.image=json.loads(command(['docker','inspect',self.project+'-api-1']))[0]['Image']
        self.health=checked(self.client.get('/health'))
        command(self.compose+['exec','-T','db','psql','-U','ragforge','-d','ragforge','-c','ALTER SYSTEM SET track_wal_io_timing = on'])
        command(self.compose+['exec','-T','db','psql','-U','ragforge','-d','ragforge','-c','SELECT pg_reload_conf()'])
    def key(self):return checked(self.client.post(self.base+'/keys',json={'name':'Bounded engineering profile'}))['secret']
    def query(self,key,i):
        wall=time.time();start=time.perf_counter();r=self.client.post(self.base+'/query',json={'question':questions[i%3]},headers={'Authorization':'Bearer '+key})
        elapsed=(time.perf_counter()-start)*1000
        result=r.json() if r.status_code==200 else {}
        return {'status':r.status_code,'http_ms':round(elapsed,3),'request_id':r.headers.get('x-request-id'),'service_ms':result.get('latency_ms'),'retrieval_ms':result.get('retrieval_latency_ms'),'generation_ms':result.get('generation_latency_ms'),'wall_start':wall,'wall_end':time.time(),'cited_or_refused':bool(result.get('citations') or result.get('refused')) if r.status_code==200 else None}
    def batch(self,variant,concurrency,count=24,key=None):
        key=key or self.key()
        sampler_code="""import collections,json,select,sys,time
from sqlalchemy import text
from app.db import SessionLocal
counts=collections.Counter();samples=0
with SessionLocal() as db:
 def wal():
  db.execute(text('SELECT pg_stat_clear_snapshot()'))
  return db.scalar(text('SELECT to_jsonb(s) FROM pg_stat_wal s'))
 before=wal();print('READY',flush=True);end=time.monotonic()+180
 while time.monotonic()<end:
  if select.select([sys.stdin],[],[],.1)[0]:break
  db.execute(text('SELECT pg_stat_clear_snapshot()'))
  rows=db.execute(text(\"SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state='active' AND wait_event IS NOT NULL\")).all()
  samples+=1
  for kind,event in rows:counts[str(kind)+'|'+str(event)]+=1
 after=wal()
 print(json.dumps({'sample_interval_seconds':.1,'samples':samples,'active_wait_observations':dict(counts),'wal_before':before,'wal_after':after,'wal_io_timing_enabled':db.scalar(text('SHOW track_wal_io_timing'))}),flush=True)
"""
        sampler=subprocess.Popen(self.compose+['exec','-T','api','python','-c',sampler_code],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if sampler.stdout.readline().strip()!='READY':
            sampler.terminate();raise RuntimeError('PostgreSQL wait/WAL sampler failed to initialize')
        start=time.perf_counter()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:rows=list(pool.map(lambda i:self.query(key,i),range(count)))
            seconds=time.perf_counter()-start
        finally:
            sampled,errors=sampler.communicate('stop\n',timeout=20)
        if sampler.returncode:raise RuntimeError('PostgreSQL wait/WAL sampler failed')
        db_observation=json.loads(sampled)
        # Docker sends log records on stderr in some engines; get both streams.
        raw=subprocess.run(['docker','logs','--tail','2000',self.project+'-api-1'],capture_output=True,text=True)
        lookup={}
        for line in (raw.stdout+'\n'+raw.stderr).splitlines():
            try:event=json.loads(line)
            except ValueError:continue
            if event.get('event')=='request_completed':lookup[event.get('request_id')]=event
        for row in rows:
            event=lookup.get(row['request_id'],{})
            row['api_pre_metric_ms']=event.get('latency_ms')
            row['post_api_log_ms']=(row['wall_end']-event['time'])*1000 if event.get('time') else None
            row['transport_proxy_finalization_ms']=round(row['http_ms']-row['api_pre_metric_ms'],3) if row['api_pre_metric_ms'] is not None else None
        success=[r['http_ms'] for r in rows if r['status']==200];quota=[r['http_ms'] for r in rows if r['status']==429]
        return {'variant':variant,'concurrency':concurrency,'requests':count,'elapsed_seconds':round(seconds,3),'successful_responses_per_second':round(len(success)/seconds,3),'status_counts':{str(s):sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})},'successful_median_ms':statistics.median(success) if success else None,'successful_p95_ms':p95(success),'quota_p95_ms':p95(quota),'postgres_observation':db_observation,'rows':rows}
    def cold_and_warm(self,variant,repeat):
        command(self.compose+['restart','api'])
        wait(lambda:self.client.get('/health').status_code==200)
        before=checked(self.client.get('/health'))['embedding_runtime'];assert not before['loaded']
        key=self.key();cold=self.query(key,0);assert cold['status']==200 and cold['cited_or_refused']
        after=checked(self.client.get('/health'))['embedding_runtime']
        report['cold'].append({'variant':variant,'repeat':repeat,'first_query':cold,'runtime_before':before,'runtime_after':after})
        for i in range(3):assert self.query(key,i)['status']==200
        for concurrency in (1,4,8):
            row=self.batch(variant,concurrency);row['repeat']=repeat;report['runs'].append(row)
        report.setdefault('warm_cache_snapshots',[]).append({'variant':variant,'repeat':repeat,'runtime':checked(self.client.get('/health'))['embedding_runtime']})
        report.setdefault('resource_snapshots',[]).append(stats(self.project+'-api-1'))
    def worker_probe(self):
        extra=checked(self.client.post('/v1/projects',json={'name':'Public controlled worker interference'}));base='/v1/projects/'+extra['id']
        text='\n'.join(f'Section {i}. Public profiling fixture: a refund request is processed within seven business days and the sample refund period is thirty days.' for i in range(5500)).encode()
        doc=checked(self.client.post(base+'/documents',files={'file':('public-interference.txt',text)}))
        wait(lambda:any(d['status']=='processing' for d in checked(self.client.get(base+'/documents'))),60)
        before=stats(self.project+'-worker-1')
        row=self.batch(self.name+'-worker-active',4)
        end_state=checked(self.client.get(base+'/documents'))[0]['status']
        wait(lambda:all(d['status']=='ready' for d in checked(self.client.get(base+'/documents'))),300)
        report['worker_interference'].append({'workload_bytes':len(text),'query_burst':row,'worker_before':before,'status_at_burst_end':end_state,'worker_after':stats(self.project+'-worker-1')})
    def quota_probe(self):
        key=self.key()
        while time.time()%60>5:time.sleep(.5)
        window=int(time.time()//60)
        for i in range(3):assert self.query(key,i)['status']==200
        rows=[self.batch(self.name+'-fixed-window-quota',c,n,key) for c,n in [(1,12),(4,24),(8,24)]]
        same=int(time.time()//60)==window
        if same:assert sum(r['status_counts'].get('429',0) for r in rows)==3
        report.setdefault('quota_probes',[]).append({'variant':self.name,'same_window':same,'limit_unchanged':60,'runs':rows})
    def profiles(self):
        code="""import cProfile,json,pstats,sys
from app.db import SessionLocal
from app.models import Project
from app.retrieval import answer
from app.embeddings import model
model()
with SessionLocal() as db:
 p=db.get(Project,sys.argv[1]);q='What is the refund period?';answer(db,p,q,'engineering-profile',save=False)
 profile=cProfile.Profile();profile.enable()
 for _ in range(20):answer(db,p,q,'engineering-profile',save=False)
 profile.disable();stats=pstats.Stats(profile)
 rows=sorted(stats.stats.items(),key=lambda x:x[1][3],reverse=True)[:25]
 print(json.dumps({'scope':'Separate warm function process; excludes HTTP/auth/metric finalization and is not API-server sampling','calls':20,'total_seconds':stats.total_tt,'functions':[{'file':k[0].split('/')[-1],'function':k[2],'calls':v[1],'self_ms':v[2]*1000,'cumulative_ms':v[3]*1000} for k,v in rows]}))
"""
        profile=json.loads(command(self.compose+['exec','-T','api','python','-c',code,self.project_id]))
        plan=command(self.compose+['exec','-T','db','psql','-U','ragforge','-d','ragforge','-tAc',"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT id FROM chunks WHERE project_id='"+self.project_id+"' ORDER BY embedding <=> (SELECT embedding FROM chunks WHERE project_id='"+self.project_id+"' LIMIT 1) LIMIT 25"])
        profile['vector_plan']=json.loads(plan)
        report.setdefault('function_and_database_profiles',{})[self.name]=profile
    def stop(self):command(self.compose+['stop'])


deployments=[]
try:
    report['other_running_container_count_before']=len(command(['docker','ps','-q']).splitlines())
    for name,prefix,origin,api,web in [('baseline',args.baseline_prefix,'https://localhost:8446',8043,3043),('candidate',args.candidate_prefix,'https://localhost:8447',8044,3044)]:
        print('Preparing fresh controlled '+name+' deployment',flush=True)
        deployments.append(Deployment(name,prefix,origin,api,web))
    baseline,candidate=deployments
    assert baseline.health['embedding_profile']['id']==candidate.health['embedding_profile']['id']
    report['images']={d.name:d.image for d in deployments};report['embedding_profile']=baseline.health['embedding_profile']['id']
    report['client_transport']=args.transport
    for repeat in range(args.repeats):
        order=deployments if repeat%2==0 else list(reversed(deployments))
        for d in order:
            print('Cold/warm '+d.name+' repeat '+str(repeat+1),flush=True)
            d.cold_and_warm(d.name+'-consent-off',repeat+1)
    checked(candidate.client.post('/v1/admin/pilot/participants',json={'email':candidate.email,'cohort':'engineering_qa','authorization_obtained':True,'authorization_reference':'Synthetic controlled performance fixture only'}))
    checked(candidate.client.put('/v1/pilot/consent',json={'accepted':True,'version':'pilot-v1'}))
    candidate.cold_and_warm('candidate-consent-on',1)
    for d in deployments:
        print('Worker interference and fixed-window quota probe: '+d.name,flush=True)
        d.worker_probe();d.quota_probe();d.profiles()
    assert all(all(status=='200' for status in row['status_counts']) and all(r['cited_or_refused'] for r in row['rows']) for row in report['runs'])
    assert all(set(r['status_counts'])=={'200'} for p in report['worker_interference'] for r in [p['query_burst']])
    assert all(set(r['status_counts'])<={'200','429'} for p in report['quota_probes'] for r in p['runs'])
    report['status']='completed'
finally:
    report.setdefault('status','failed_before_completion')
    report['created_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    report['profile_namespaces']=[d.project for d in deployments]
    for d in deployments:
        d.client.close();d.stop()
    (ROOT/'docs/qa/m5-query-profiling.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS: controlled before/after cold/warm, worker, cache, DB, scheduling/transport and quota evidence recorded.')
