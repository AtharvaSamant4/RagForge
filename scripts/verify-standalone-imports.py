"""Run a configuration-only export as a second independent Docker application."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

import httpx

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--archive',required=True)
parser.add_argument('--port',type=int,default=8021)
parser.add_argument('--output',default='artifacts/standalone-imports.json')
args=parser.parse_args()
directory=Path(tempfile.mkdtemp(prefix='standalone-empty-',dir=ROOT/'artifacts'))
report={'created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'extracted_directory':str(directory),'port':args.port}
with zipfile.ZipFile(args.archive) as archive:
    assert archive.testzip() is None
    manifest=json.loads(archive.read('config/manifest.json'))
    assert manifest['mode']=='configuration' and manifest['sources']==[]
    assert '.env' not in archive.namelist() and '.standalone-key' not in archive.namelist()
    for info in archive.infolist():assert (directory/info.filename).resolve().is_relative_to(directory) and (info.external_attr>>16)&0o170000==0o100000
    archive.extractall(directory)
report['manifest']=manifest
report['archive_sha256']=hashlib.sha256(Path(args.archive).read_bytes()).hexdigest()
env={k:v for k,v in os.environ.items() if k not in ('API_PORT','WEB_PORT','APP_ORIGINS','COMPOSE_PROJECT_NAME')}


def command(arguments):subprocess.run(arguments,cwd=directory,env=env,check=True)


def wait(check):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        try:
            result=check()
            if result:return result
        except httpx.HTTPError:pass
        time.sleep(2)
    raise TimeoutError('Standalone import state did not settle')


command([sys.executable,'scripts/init.py','--port',str(args.port)])
started=time.perf_counter();command(['docker','compose','up','--build','-d'])
report['compose_build_start_seconds']=round(time.perf_counter()-started,3)
started=time.perf_counter();command(['docker','compose','exec','-T','api','python','-m','app.model_cache'])
report['prefetch_seconds']=round(time.perf_counter()-started,3)
key=(directory/'.standalone-key').read_text().strip()
with httpx.Client(base_url=f'http://localhost:{args.port}',headers={'Authorization':'Bearer '+key},timeout=120) as client:
    def status():
        r=client.get('/v1/status');r.raise_for_status();return r.json()
    assert status()['documents']==[]
    assert client.post('/v1/query',json={'question':'What is the refund period?'}).json()['refused']
    bad=client.post('/v1/documents',files={'file':('broken.pdf',b'%PDF-1.7\ninvalid')});bad.raise_for_status()
    bad_id=bad.json()['id']
    failed=wait(lambda:next((d for d in status()['documents'] if d['id']==bad_id and d['status']=='failed'),None))
    assert failed['error']
    client.delete('/v1/documents/'+bad_id).raise_for_status()
    content=b'Engineers receive 25 paid leave days each year.'
    response=client.post('/v1/documents',files={'file':('team.txt',content)});response.raise_for_status()
    doc_id=response.json()['id']
    ready=wait(lambda:next((d for d in status()['documents'] if d['id']==doc_id and d['status']=='ready'),None))
    report['document']=ready
    def query():
        r=client.post('/v1/query',json={'question':'How many paid leave days do engineers receive?'});r.raise_for_status();return r.json()
    first=query();assert '25' in first['answer'] and first['citations'][0]['document_name']=='team.txt'
    report['query']=first
    assert client.post('/v1/query',json={'question':'What is the refund period?'}).json()['refused']
    command(['docker','compose','restart','api','worker'])
    wait(lambda:client.get('/health').status_code==200)
    after=query();assert [(c['chunk_id'],c['quote']) for c in first['citations']]==[(c['chunk_id'],c['quote']) for c in after['citations']]
    assert len(status()['documents'])==1
    report['restart_query']=after
    report['status']=status()
report['database_evidence']=subprocess.check_output(['docker','compose','exec','-T','db','psql','-U','standalone','-d','standalone','-tAc',"SELECT current_database(),(SELECT count(*) FROM chunks),(SELECT count(*) FROM pg_indexes WHERE indexname='standalone_chunks_vector');"],cwd=directory,env=env,text=True).strip()
report['resources']=subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}',*subprocess.check_output(['docker','compose','ps','-q'],cwd=directory,env=env,text=True).split()],env=env,text=True)
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
Path(args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS: configuration-only startup, empty refusal, failed-file removal, semantic import/query, isolated data and persistence. Report:',args.output)
