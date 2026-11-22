"""Disposable HTTPS alpha acceptance, encrypted recovery, and bounded local load.

Never points at existing user deployments: project names are fixed QA namespaces.
Secrets remain in ignored artifacts, subprocess stdin, or memory; reports omit them.
"""
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

ROOT=Path(__file__).resolve().parents[1]
SOURCE='ragforge-m4-alpha'
import argparse,re
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--restore-project',default='ragforge-m4-restore',help='Separate empty disposable target; choose a fresh suffix when rerunning')
args=parser.parse_args()
if not re.fullmatch(r'ragforge-m4-restore(?:-[a-z0-9]+)?',args.restore_project):parser.error('Use the disposable ragforge-m4-restore namespace')
TARGET=args.restore_project
ALPHA=['docker','compose','--env-file','.env.alpha','-p',SOURCE,'-f','compose.yaml','-f','compose.alpha.yaml']
RESTORE=['docker','compose','-p',TARGET]
ORIGIN='https://localhost:8443'
RECOVERY_SETTINGS=ROOT/'artifacts/m4-recovery.env'
RESTORE_ENV={**os.environ,'RAGFORGE_ENV_FILE':str(RECOVERY_SETTINGS),'REGISTRATION_MODE':'disabled','ALLOW_REGISTRATION':'false','ALLOW_PUBLIC_WIDGETS':'false','API_PORT':'8050','WEB_PORT':'3050','APP_ORIGINS':'http://localhost:3050','HOSTED_DAILY_REQUESTS':'0'}
credentials_path=ROOT/'artifacts/m4-private-credentials.json'
report={'created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'source':SOURCE,'restore_target':TARGET,'scope':'Isolated local CPU MiniLM/extractive; no paid provider, public service or external testers.'}


def command(argv,*,env=None,input=None,check=True):
    result=subprocess.run(argv,cwd=ROOT,env=env,input=input,text=True,capture_output=True)
    if check and result.returncode:raise RuntimeError('Operator command failed: '+result.stderr[-2000:])
    return result


def wait(fn,seconds=240):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:value=fn()
        except httpx.HTTPError:value=None
        if value:return value
        time.sleep(1)
    raise TimeoutError('Expected QA state did not become ready')


def checked(response,code=None):
    response.raise_for_status()
    if code:assert response.status_code==code
    return response.json()


def main():
    RECOVERY_SETTINGS.write_text('GENERATION_PROVIDER=extractive\n',encoding='utf-8')
    credentials=json.loads(credentials_path.read_text())
    headers={'Origin':ORIGIN}
    with httpx.Client(base_url=ORIGIN+'/api',verify=False,headers=headers,timeout=120) as admin, httpx.Client(base_url=ORIGIN+'/api',verify=False,headers=headers,timeout=120) as client:
        checked(admin.post('/v1/auth/login',json={'email':credentials['admin_email'],'password':credentials['admin_password']}))
        assert client.get('/v1/projects').status_code==401
        assert client.post('/v1/auth/register',json={'email':'uninvited@example.com','password':'uninvited-qa-test-password'}).status_code==403
        credentials['recovery_email']='recovery-'+secrets.token_hex(5)+'@example.com'
        credentials['recovery_password']=secrets.token_urlsafe(24)
        invitation=checked(admin.post('/v1/admin/invites',json={}))['token']
        r=client.post('/v1/auth/register',json={'email':credentials['recovery_email'],'password':credentials['recovery_password'],'invite_token':invitation})
        checked(r,201);assert 'Secure' in r.headers['set-cookie'] and 'HttpOnly' in r.headers['set-cookie']
        assert client.get('/v1/admin/diagnostics').status_code==403
        project=checked(client.post('/v1/projects',json={'name':'Encrypted recovery QA'}),201);base='/v1/projects/'+project['id']
        pipeline={**project['pipeline'],'strategy':'hybrid','auto':False}
        checked(client.put(base+'/pipeline',json=pipeline))
        data=(ROOT/'samples/acme-handbook.pdf').read_bytes()
        doc=checked(client.post(base+'/documents',files={'file':('acme-handbook.pdf',data)}),202)
        def ready():
            state=checked(client.get(base+'/documents'))
            if any(d['status']=='failed' for d in state):raise AssertionError('Source ingestion failed')
            return state if state and all(d['status']=='ready' for d in state) else None
        wait(ready)
        questions=['What is the refund period?','How long does a refund take?','Who won the Martian election in 2050?']
        before=[{'question':q,'result':checked(client.post(base+'/query',json={'question':q}))} for q in questions]
        assert not before[0]['result']['refused'] and before[0]['result']['citations']
        assert before[-1]['result']['refused']
        key=checked(client.post(base+'/keys',json={'name':'Recovery QA'}))['secret']
        credentials['recovery_project']=project['id'];credentials['recovery_key']=key
        credentials_path.write_text(json.dumps(credentials));credentials_path.chmod(0o600)
        old_cookie=client.cookies.get('ragforge_session')
        backup=ROOT/'artifacts/m4-hosted.backup'
        if backup.exists():backup=ROOT/('artifacts/m4-hosted-'+secrets.token_hex(4)+'.backup')
        password=secrets.token_urlsafe(32)
        credentials['backup_passphrase']=password;credentials['backup_file']=str(backup)
        credentials_path.write_text(json.dumps(credentials));credentials_path.chmod(0o600)
        print('Backing up the indexed disposable account/project',flush=True)
        backup_cmd=[sys.executable,'scripts/backup.py','create','--project',SOURCE,'--file',str(backup),'--allow-downtime','--passphrase-stdin','--env-file','.env.alpha','--compose-file','compose.yaml','--compose-file','compose.alpha.yaml']
        started=time.perf_counter();created=command(backup_cmd,input=password+'\n')
        report['backup']={'create_seconds':round(time.perf_counter()-started,3),'encrypted_bytes':backup.stat().st_size,'sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'ciphertext_contains_sample':b'30 day refund' in backup.read_bytes()}
        for service in ('api','worker','web'):command(['docker','tag',SOURCE+'-'+service,TARGET+'-'+service])
        command(RESTORE+['up','--no-build','-d','--wait','db'],env=RESTORE_ENV)
        restore_cmd=[sys.executable,'scripts/backup.py','restore','--project',TARGET,'--file',str(backup),'--allow-downtime','--confirm-empty-restore','--passphrase-stdin']
        wrong=command(restore_cmd,input='incorrect-long-backup-passphrase\n',env=RESTORE_ENV,check=False)
        assert wrong.returncode and 'authentication' in wrong.stderr
        assert command(RESTORE+['exec','-T','db','psql','-U','ragforge','-d','ragforge','-tAc',"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"],env=RESTORE_ENV).stdout.strip()=='0'
        print('Restoring encrypted backup into the separate empty target',flush=True)
        started=time.perf_counter();command(restore_cmd,input=password+'\n',env=RESTORE_ENV)
        command(RESTORE+['up','--no-build','-d'],env=RESTORE_ENV)
        report['backup']['restore_start_seconds']=round(time.perf_counter()-started,3)
        with httpx.Client(base_url='http://localhost:8050',headers={'Origin':'http://localhost:3050'},timeout=120) as restored:
            wait(lambda:restored.get('/health').status_code==200)
            assert restored.get('/v1/projects',cookies={'ragforge_session':old_cookie}).status_code==401
            checked(restored.post('/v1/auth/login',json={'email':credentials['recovery_email'],'password':credentials['recovery_password']}))
            projects=checked(restored.get('/v1/projects'));assert any(p['id']==project['id'] for p in projects)
            restored_docs=checked(restored.get(base+'/documents'));assert restored_docs[0]['sha256']==hashlib.sha256(data).hexdigest() and restored_docs[0]['id']==doc['id']
            after=checked(restored.post(base+'/query',json={'question':questions[0]}))
            assert [(c['document_id'],c['quote']) for c in after['citations']]==[(c['document_id'],c['quote']) for c in before[0]['result']['citations']]
            external=checked(restored.post(base+'/query',json={'question':questions[0]},headers={'Authorization':'Bearer '+key}));assert external['citations']
            refusal=command(restore_cmd,input=password+'\n',env=RESTORE_ENV,check=False)
            assert refusal.returncode and 'database is not empty' in refusal.stderr
            wait(lambda:restored.get('/health').status_code==200)
            assert checked(restored.post(base+'/query',json={'question':questions[0]}))['citations']
            report['backup'].update(wrong_passphrase_before_writes='passed',nonempty_target_refused='passed',sessions_excluded='passed',restored_project=project['id'],source_sha256=restored_docs[0]['sha256'],citations_after_restore=after['citations'],api_key_hash_restored='passed')
        # Keep password only in a local ignored operator secret file, never the evidence report.
        credentials['backup_passphrase']=password;credentials['backup_file']=str(backup)
        credentials_path.write_text(json.dumps(credentials));credentials_path.chmod(0o600)
        report['readiness']=checked(admin.get('/v1/admin/diagnostics'))['readiness']
        assert report['readiness']['ready']
        print('Restored citations matched; starting bounded local query load',flush=True)
        # A bounded, warm mixed query workload; question text is the public sample only.
        health=checked(client.get('/health'))
        keyheaders={'Authorization':'Bearer '+key}
        for i in range(3):checked(client.post(base+'/query',json={'question':questions[i%3]},headers=keyheaders))
        def request(i):
            start=time.perf_counter()
            r=client.post(base+'/query',json={'question':questions[i%3]},headers=keyheaders)
            return {'status':r.status_code,'ms':(time.perf_counter()-start)*1000,'cited':bool(r.json().get('citations')),'refused':r.json().get('refused')}
        loads=[]
        for concurrency,count in [(1,12),(4,24),(8,24)]:
            start=time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:rows=list(pool.map(request,range(count)))
            elapsed=time.perf_counter()-start;values=sorted(r['ms'] for r in rows)
            loads.append({'concurrency':concurrency,'requests':count,'seconds':round(elapsed,3),'requests_per_second':round(count/elapsed,3),'median_ms':round(statistics.median(values),2),'p95_ms':round(values[math.ceil(len(values)*.95)-1],2),'status_counts':{str(status):sum(r['status']==status for r in rows) for status in {r['status'] for r in rows}},'sampled_cited_or_refused':all(r['cited'] or r['refused'] for r in rows)})
        report['load']={'platform':platform.platform(),'cpu_logical_count':os.cpu_count(),'model':health['embedding_profile']['id'],'workload':'60 warm requests, 3 sample questions, real semantic retrieval/extractive generation, shared project key, no streaming; sequential stages. Other development stacks remained running; host contention was not controlled. No deliberate competing load. HTTP includes auth, durable query storage and metric overhead.','runs':loads,'resources':command(['docker','stats','--no-stream','--format','{{json .}}',SOURCE+'-api-1',SOURCE+'-worker-1',SOURCE+'-db-1']).stdout}
        # Export this same source; independently executed by verify-standalone.py afterwards.
        export=checked(client.post(base+'/exports',json={'mode':'snapshot','document_ids':[doc['id']],'acknowledge_copy':True}),202)
        def exported():
            state=checked(client.get(base+'/exports/'+export['id']))
            if state['status']=='failed':raise AssertionError(state['error'])
            return state if state['status']=='ready' else None
        job=wait(exported);archive=client.get(base+'/exports/'+job['id']+'/download');archive.raise_for_status()
        assert hashlib.sha256(archive.content).hexdigest()==job['sha256']
        (ROOT/'artifacts/m4-application.zip').write_bytes(archive.content)
        (ROOT/'artifacts/m4-export-before.json').write_text(json.dumps({'before':before,'export':job},indent=2))
    target=ROOT/'docs/qa/m4-hosted-recovery-load.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: private-alpha controls, encrypted hosted backup/empty-target restore, cited retrieval, bounded query load and standalone export. Evidence:',target)


if __name__=='__main__':main()
