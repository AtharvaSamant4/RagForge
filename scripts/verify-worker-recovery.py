"""Real SIGKILL/reclaim and bounded ingestion test of the isolated M4 QA worker."""
import concurrent.futures
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import httpx
ROOT=Path(__file__).resolve().parents[1]
PROJECT='ragforge-m4'
ENV={**os.environ,'API_PORT':'8031','WEB_PORT':'3031','APP_ORIGINS':'http://localhost:3031'}
BASE=['docker','compose','-p',PROJECT,'-f','compose.yaml']
QA=BASE+['-f',str(ROOT/'artifacts/m4-worker-qa.yaml')]


def command(argv):
    r=subprocess.run(argv,cwd=ROOT,env=ENV,text=True,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr[-2000:])
    return r.stdout


def checked(r):r.raise_for_status();return r.json()


def main():
    (ROOT/'artifacts/m4-worker-qa.yaml').write_text('services:\n  worker:\n    environment:\n      JOB_LEASE_SECONDS: "5"\n')
    marker='M4_PRIVATE_SOURCE_NEVER_LOG_'+secrets.token_hex(8)
    question_marker='M4_PRIVATE_QUESTION_NEVER_LOG_'+secrets.token_hex(8)
    password=secrets.token_urlsafe(24)
    report={'created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'compose_project':PROJECT,'protocol':'Actual worker SIGKILL while a new document is processing. Disposable QA-only 5-second lease, explicit 6-second crash interval, then a new worker. Normal deployment settings are restored in finally.'}
    try:
        command(QA+['up','--no-deps','--force-recreate','-d','worker'])
        command(['docker','update','--restart=no',PROJECT+'-worker-1'])
        with httpx.Client(base_url='http://localhost:8031',headers={'Origin':'http://localhost:3031'},timeout=120) as client:
            checked(client.post('/v1/auth/register',json={'email':'worker-recovery-'+secrets.token_hex(5)+'@example.com','password':password}))
            project=checked(client.post('/v1/projects',json={'name':'Real worker recovery QA'}));base='/v1/projects/'+project['id']
            text=(marker+'\n'+'Recovery policy retains all committed source bytes.\n'*16000).encode()
            doc=checked(client.post(base+'/documents',files={'file':('recovery.txt',text)}))
            deadline=time.monotonic()+30;claimed=None
            while time.monotonic()<deadline:
                jobs=checked(client.get(base+'/jobs'))
                if jobs[0]['status']=='processing':claimed=jobs[0];break
                if jobs[0]['status']=='succeeded':raise AssertionError('QA workload finished before interruption; recovery not tested')
                time.sleep(.25)
            assert claimed,'Worker never claimed the recovery document'
            started=time.perf_counter();command(['docker','kill','--signal=KILL',PROJECT+'-worker-1'])
            time.sleep(6)
            assert json.loads(command(['docker','inspect','--format','{{json .State}}',PROJECT+'-worker-1']))['Running'] is False
            command(QA+['up','--no-deps','--force-recreate','-d','worker'])
            deadline=time.monotonic()+180;final=None
            while time.monotonic()<deadline:
                docs=checked(client.get(base+'/documents'))
                if docs[0]['status']=='failed':raise AssertionError(docs[0]['error'])
                if docs[0]['status']=='ready':final=docs[0];break
                time.sleep(2)
            assert final,'Recovered job did not finish'
            jobs=checked(client.get(base+'/jobs'));assert jobs[0]['status']=='succeeded' and jobs[0]['attempts']==2,jobs
            result=checked(client.post(base+'/query',json={'question':'What does the recovery policy retain?'}));assert result['citations']
            checked(client.post(base+'/query',json={'question':question_marker}))
            report['recovery']={'killed_status':claimed['status'],'attempts_before':claimed['attempts'],'attempts_after':jobs[0]['attempts'],'final_status':final['status'],'seconds_from_kill_to_ready':round(time.perf_counter()-started,3),'document_bytes':len(text),'chunks':final['chunk_count'],'cited_query_after_recovery':True}
            project=checked(client.post('/v1/projects',json={'name':'Bounded ingestion throughput'}));base='/v1/projects/'+project['id']
            data=(ROOT/'samples/acme-handbook.pdf').read_bytes()
            started=time.perf_counter()
            def upload(i):return checked(client.post(base+'/documents',files={'file':(f'handbook-{i}.pdf',data)}))
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:docs=list(pool.map(upload,range(4)))
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                states=checked(client.get(base+'/documents'))
                if any(d['status']=='failed' for d in states):raise AssertionError('Throughput ingestion failed')
                if len(states)==4 and all(d['status']=='ready' for d in states):break
                time.sleep(1)
            else:raise TimeoutError('Bounded ingestion did not finish')
            elapsed=time.perf_counter()-started
            report['ingestion']={'documents':4,'bytes':4*len(data),'seconds_upload_to_all_ready':round(elapsed,3),'documents_per_second':round(4/elapsed,3),'chunks':sum(d['chunk_count'] for d in states),'workload':'Four concurrent uploads of the public one-page PDF; one CPU MiniLM worker, normal parser limits, 1-second completion polling. Local test, not a capacity guarantee.'}
            logs=command(BASE+['logs','--no-color','api','worker'])
            assert all(secret not in logs for secret in (password,marker,question_marker))
            report['ordinary_log_leak_check']='passed for unique source/question/password markers'
            report['resource_snapshot']=command(['docker','stats','--no-stream','--format','{{json .}}',PROJECT+'-api-1',PROJECT+'-worker-1'])
    finally:
        command(BASE+['up','--no-deps','--force-recreate','-d','worker'])
    target=ROOT/'docs/qa/m4-worker-recovery-ingestion.json';target.write_text(json.dumps(report,indent=2)+'\n');print('PASS: real worker interruption/reclaim, cited query, bounded concurrent ingestion and ordinary-log markers. Evidence:',target)


if __name__=='__main__':main()
