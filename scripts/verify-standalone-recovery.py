"""Recover the actual independent v1.1 application into a separate empty deployment."""
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
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--directory',required=True,help='Previously verified extracted standalone package')
parser.add_argument('--port',type=int,default=8023,help='Separate target loopback API port')
parser.add_argument('--legacy',action='append',default=[],help='Optional PORT=PATH of an existing v1.0 package')
args=parser.parse_args()
SOURCE_DIR=Path(args.directory).resolve()


def values(directory):return dict(line.split('=',1) for line in (directory/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))


def run(argv,directory=ROOT,*,input=None):
    env=os.environ.copy()
    for key in ('API_PORT','WEB_PORT','APP_ORIGINS','COMPOSE_PROJECT_NAME'):env.pop(key,None)
    r=subprocess.run(argv,cwd=directory,env=env,input=input,text=True,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr[-2000:])
    return r.stdout


def wait(fn,seconds=240):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:value=fn()
        except httpx.HTTPError:value=None
        if value:return value
        time.sleep(1)
    raise TimeoutError('Standalone restore did not become ready')


def main():
    target=Path(tempfile.mkdtemp(prefix='standalone-restore-',dir=ROOT/'artifacts'))
    with zipfile.ZipFile(SOURCE_DIR/'application.zip') as archive:
        assert archive.testzip() is None
        for entry in archive.infolist():assert (target/entry.filename).resolve().is_relative_to(target) and not entry.is_dir()
        archive.extractall(target)
    if not 1024<=args.port<=65535:raise ValueError('Invalid target port')
    source_port=int(values(SOURCE_DIR)['API_PORT'])
    if source_port==args.port:raise ValueError('Source and target ports must differ')
    run([sys.executable,'scripts/init.py','--port',str(args.port)],target)
    source_project=values(SOURCE_DIR)['COMPOSE_PROJECT_NAME'];target_project=values(target)['COMPOSE_PROJECT_NAME']
    for service in ('api','worker'):run(['docker','tag',source_project+'-'+service,target_project+'-'+service])
    run(['docker','compose','up','--no-build','-d','--wait','db'],target)
    key=(SOURCE_DIR/'.standalone-key').read_text().strip()
    with httpx.Client(base_url=f'http://localhost:{source_port}',headers={'Authorization':'Bearer '+key},timeout=90) as client:
        before=client.post('/v1/query',json={'question':'What is the refund period?'});before.raise_for_status();before=before.json();assert before['citations']
    backup=ROOT/('artifacts/m4-standalone-'+secrets.token_hex(4)+'.backup');password=secrets.token_urlsafe(32)
    print('Creating encrypted standalone database/source backup',flush=True)
    started=time.perf_counter()
    run([sys.executable,str(ROOT/'scripts/backup.py'),'create','--kind','standalone','--directory',str(SOURCE_DIR),'--project',source_project,'--file',str(backup),'--allow-downtime','--passphrase-stdin'],input=password+'\n')
    create_seconds=time.perf_counter()-started
    print('Restoring into the second empty standalone deployment',flush=True)
    started=time.perf_counter()
    run([sys.executable,str(ROOT/'scripts/backup.py'),'restore','--kind','standalone','--directory',str(target),'--project',target_project,'--file',str(backup),'--allow-downtime','--confirm-empty-restore','--passphrase-stdin'],input=password+'\n')
    restore_seconds=time.perf_counter()-started
    run(['docker','compose','up','--no-build','-d'],target)
    run(['docker','compose','exec','-T','api','python','-m','app.model_cache'],target)
    newkey=(target/'.standalone-key').read_text().strip();assert newkey!=key
    with httpx.Client(base_url=f'http://localhost:{args.port}',headers={'Authorization':'Bearer '+newkey},timeout=120) as client:
        wait(lambda:client.get('/health').status_code==200)
        assert client.get('/v1/status',headers={'Authorization':'Bearer '+key}).status_code==401
        after=client.post('/v1/query',json={'question':'What is the refund period?'});after.raise_for_status();after=after.json()
        assert [(c['chunk_id'],c['document_id'],c['quote']) for c in before['citations']]==[(c['chunk_id'],c['document_id'],c['quote']) for c in after['citations']]
        state=client.get('/v1/status');state.raise_for_status()
        checks=run(['docker','compose','exec','-T','api','python','-c',"import hashlib,json;from sqlalchemy import select;from app.engine.db import SessionLocal;from app.engine.models import Document;from app.engine.config import settings;\nwith SessionLocal() as db:\n print(json.dumps([{'id':d.id,'sha256':d.sha256,'source_matches':hashlib.sha256((settings().storage_dir/d.storage_name).read_bytes()).hexdigest()==d.sha256} for d in db.scalars(select(Document))]))"],target)
        checks=json.loads(checks);assert checks and all(c['source_matches'] for c in checks)
    # Keep recovery material local and excluded from source control/evidence.
    secret=ROOT/'artifacts/m4-standalone-recovery-secret.json';secret.write_text(json.dumps({'passphrase':password,'backup':str(backup),'source':str(SOURCE_DIR),'target':str(target)}));secret.chmod(0o600)
    report={'created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'generator_version':json.loads((SOURCE_DIR/'config/manifest.json').read_text())['generator_version'],'source_project':source_project,'target_project':target_project,'empty_separate_target':True,'encrypted_bytes':backup.stat().st_size,'encrypted_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'create_seconds':round(create_seconds,3),'restore_seconds':round(restore_seconds,3),'source_integrity':checks,'citation_identity_and_quotes_match':True,'independent_target_credentials':True,'restored_documents':state.json()['documents'],'old_exports':[]}
    for item in args.legacy:
        port,directory=item.split('=',1);port=int(port)
        raw=(Path(directory).resolve()/'.standalone-key').read_text().strip()
        with httpx.Client(base_url=f'http://localhost:{port}',headers={'Authorization':'Bearer '+raw},timeout=120) as client:
            health=client.get('/health');health.raise_for_status();assert health.json()['generator_version']=='1.0.0'
            assert httpx.get(f'http://localhost:{port}/v1/status').status_code==401
            state=client.get('/v1/status');state.raise_for_status()
            query=client.post('/v1/query',json={'question':'What is the refund period?'});query.raise_for_status()
            assert query.json()['refused'] or query.json()['citations']
            report['old_exports'].append({'port':port,'generator_version':'1.0.0','authenticated_status':200,'anonymous_status':401,'query_status':200,'documents':len(state.json()['documents']),'cited_or_refused':True})
    path=ROOT/'docs/qa/m4-standalone-recovery.json';path.write_text(json.dumps(report,indent=2)+'\n');print('PASS: encrypted standalone restore, source/citation integrity and independent target credentials; see report for optional legacy checks. Evidence:',path)


if __name__=='__main__':main()
