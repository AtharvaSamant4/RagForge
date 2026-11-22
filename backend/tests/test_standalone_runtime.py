"""Execute the compiled package in a new interpreter without repository imports."""
import hashlib
import io
import os
from pathlib import Path
import secrets
import subprocess
import sys
import zipfile

from app.config import settings
from app import exports
from test_workflow import ingest


def test_compiled_configuration_app_import_auth_model_guards_and_restart(owner,project,monkeypatch,tmp_path):
    monkeypatch.setattr(settings(),'embedding_provider','semantic')
    base=f'/v1/projects/{project["id"]}/exports'
    response=owner.post(base,json={});assert response.status_code==202
    assert exports.run_once()
    response=owner.get(base+'/'+response.json()['id']+'/download');assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:archive.extractall(tmp_path)
    raw=secrets.token_urlsafe(32)
    env={**os.environ,'PYTHONPATH':str(tmp_path),'DATABASE_URL':'sqlite:///'+(tmp_path/'runtime/test.db').as_posix(),'STORAGE_DIR':str(tmp_path/'runtime/uploads'),'MODEL_CACHE_DIR':str(settings().model_cache_dir.resolve()),'MODEL_LOCAL_FILES_ONLY':'true','EMBEDDING_PROVIDER':'semantic','STANDALONE_API_KEY_HASH':hashlib.sha256(raw.encode()).hexdigest(),'TEST_KEY':raw}
    program=r'''
import hashlib,json,os
from pathlib import Path
from fastapi.testclient import TestClient
from app.initialize import initialize
from app.main import app
from app.engine import worker
from app.engine.config import settings
from app.engine.db import SessionLocal
from app.engine.models import Chunk
from sqlalchemy import select
initialize()
headers={'Authorization':'Bearer '+os.environ['TEST_KEY']}
with TestClient(app,headers=headers) as client:
 assert client.get('/v1/status').json()['documents']==[]
 assert client.get('/v1/config',headers={'Authorization':'Bearer wrong'}).status_code==401
 assert client.post('/v1/query',json={'question':'what is unknown?'}).json()['refused']
 text=b'Customers may return eligible products within 30 calendar days of receiving their order.'
 r=client.post('/v1/documents',files={'file':('../../returns.txt',text)});assert r.status_code==202,r.text
 assert worker.run_once()
 result=client.post('/v1/query',json={'question':'What is the return period?'}).json()
 assert not result['refused'] and result['citations'][0]['quote']==text.decode()
 assert result['citations'][0]['document_name']=='returns.txt'
 assert client.post('/v1/query',json={'question':'Who won the Martian election in 2050?'}).json()['refused']
 settings().embedding_provider='local'
 assert client.post('/v1/query',json={'question':'What is the return period?'}).status_code==409
 assert client.post('/v1/reindex').status_code==202
 assert worker.run_once()
 assert client.post('/v1/query',json={'question':'What is the return period?'}).status_code==200
 settings().embedding_provider='semantic'
 assert client.post('/v1/query',json={'question':'What is the return period?'}).status_code==409
 assert client.post('/v1/reindex').status_code==202
 assert worker.run_once()
 first=client.post('/v1/query',json={'question':'What is the return period?'}).json()
 initialize()
 after=client.post('/v1/query',json={'question':'What is the return period?'}).json()
 assert first['citations']==after['citations']
 assert len(client.get('/v1/status').json()['documents'])==1
 settings().model_cache_dir=Path('missing-model-cache')
 r=client.post('/v1/query',json={'question':'What is the return period?'})
 assert r.status_code==503 and 'missing or corrupt' in r.json()['detail']
 assert client.post('/v1/query',content=b'x'*300000,headers={'Content-Type':'application/json'}).status_code==413
 print('PASS compiled runtime: real semantic import/query, credentials, model changes, controlled rebuild, persistence, missing model and body limits')
'''
    result=subprocess.run([sys.executable,'-c',program],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+'\n'+result.stderr


def test_generated_credentials_rotation_disabled_imports_and_dimension_guard(owner,project,tmp_path):
    base=f'/v1/projects/{project["id"]}/exports'
    response=owner.post(base,json={'allow_imports':False});assert response.status_code==202
    assert exports.run_once()
    data=owner.get(base+'/'+response.json()['id']+'/download').content
    with zipfile.ZipFile(io.BytesIO(data)) as archive:archive.extractall(tmp_path)
    def init(*arguments):
        return subprocess.run([sys.executable,'scripts/init.py',*arguments],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert init().returncode==0
    first_key=(tmp_path/'.standalone-key').read_text().strip()
    def values():return dict(line.split('=',1) for line in (tmp_path/'.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    first=values()
    assert first['STANDALONE_API_KEY_HASH']==hashlib.sha256(first_key.encode()).hexdigest()
    assert first_key not in (tmp_path/'.env').read_text()
    assert init().returncode!=0
    assert init('--rotate').returncode==0
    rotated=values()
    assert rotated['POSTGRES_PASSWORD']==first['POSTGRES_PASSWORD']
    assert rotated['COMPOSE_PROJECT_NAME']==first['COMPOSE_PROJECT_NAME']
    assert rotated['STANDALONE_API_KEY_HASH']!=first['STANDALONE_API_KEY_HASH']
    key=(tmp_path/'.standalone-key').read_text().strip()
    env={**os.environ,'PYTHONPATH':str(tmp_path),'DATABASE_URL':'sqlite:///'+(tmp_path/'runtime/test.db').as_posix(),'STORAGE_DIR':str(tmp_path/'runtime/uploads'),'EMBEDDING_PROVIDER':'local','STANDALONE_API_KEY_HASH':rotated['STANDALONE_API_KEY_HASH'],'TEST_KEY':key}
    program=r'''
import os
from fastapi.testclient import TestClient
from app.initialize import initialize
from app.main import app
initialize()
with TestClient(app,headers={'Authorization':'Bearer '+os.environ['TEST_KEY']}) as client:
 r=client.post('/v1/documents',files={'file':('text.txt',b'Cannot import this')})
 assert r.status_code==403,r.text
 del os.environ['STANDALONE_API_KEY_HASH']
 assert client.get('/v1/config').status_code==503
'''
    result=subprocess.run([sys.executable,'-c',program],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    env['EMBEDDING_DIMENSIONS']='512'
    result=subprocess.run([sys.executable,'-c','import app.bootstrap'],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode!=0 and 'requires 384 dimensions' in result.stderr


def test_removed_snapshot_stays_removed_and_explicit_import_restores_it(owner,project,tmp_path):
    _,doc=ingest(owner,project,b'The support desk operates from nine until five.','support.txt')
    base=f'/v1/projects/{project["id"]}/exports'
    response=owner.post(base,json={'mode':'snapshot','document_ids':[doc['id']],'acknowledge_copy':True})
    assert response.status_code==202
    assert exports.run_once()
    data=owner.get(base+'/'+response.json()['id']+'/download').content
    with zipfile.ZipFile(io.BytesIO(data)) as archive:archive.extractall(tmp_path)
    raw=secrets.token_urlsafe(32)
    env={**os.environ,'PYTHONPATH':str(tmp_path),'DATABASE_URL':'sqlite:///'+(tmp_path/'runtime/test.db').as_posix(),'STORAGE_DIR':str(tmp_path/'runtime/uploads'),'EMBEDDING_PROVIDER':'local','STANDALONE_API_KEY_HASH':hashlib.sha256(raw.encode()).hexdigest(),'TEST_KEY':raw}
    program=r'''
import os
from fastapi.testclient import TestClient
from app.initialize import initialize
from app.main import app
from app.engine.worker import run_once
initialize()
assert run_once()
with TestClient(app,headers={'Authorization':'Bearer '+os.environ['TEST_KEY']}) as client:
 docs=client.get('/v1/documents').json();assert len(docs)==1
 assert client.delete('/v1/documents/'+docs[0]['id']).status_code==200
 initialize()
 assert client.get('/v1/documents').json()==[]
 r=client.post('/v1/documents',files={'file':('support.txt',b'The support desk operates from nine until five.')})
 assert r.status_code==202,r.text
 assert run_once()
 initialize()
 assert len(client.get('/v1/documents').json())==1
'''
    result=subprocess.run([sys.executable,'-c',program],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
