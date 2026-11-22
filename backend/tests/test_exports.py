import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import time
import zipfile

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Document, ExportJob, QueryRecord
from app.export_compiler import ExportError, compile_archive, scan, template_files
from app import exports
from test_workflow import ingest


def create(owner,project,**body):
    return owner.post(f'/v1/projects/{project["id"]}/exports',json=body)


def complete(owner,project,response):
    assert response.status_code==202,response.text
    assert exports.run_once()
    path=f'/v1/projects/{project["id"]}/exports/{response.json()["id"]}'
    result=owner.get(path).json()
    assert result["status"]=="ready",result
    downloaded=owner.get(path+"/download")
    assert downloaded.status_code==200
    assert hashlib.sha256(downloaded.content).hexdigest()==result["sha256"]
    return result,downloaded.content


def test_configuration_only_is_deterministic_complete_and_secret_free(owner,project,monkeypatch):
    base,doc=ingest(owner,project,b'Confidential source should not be exported.','private.txt')
    key=owner.post(base+'/keys',json={'name':'existing','scopes':['query','read']}).json()['secret']
    secret='sk-proj-'+('sensitive'*8)
    monkeypatch.setattr(settings(),'openai_api_key',secret)
    owner.post(base+'/query',json={'question':'Private conversation wording not in any package'})
    first,data=complete(owner,project,create(owner,project))
    second,again=complete(owner,project,create(owner,project))
    assert data==again and first['sha256']==second['sha256']
    assert key.encode() not in data and secret.encode() not in data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        names=set(archive.namelist())
        assert {'app/main.py','app/retrieval/__init__.py','Dockerfile','compose.yaml','requirements.lock.txt','README.md','scripts/init.py','tests/test_api.py','config/manifest.json'}<=names
        assert not {'.env','.standalone-key','data/ragforge.db'}&names
        manifest=json.loads(archive.read('config/manifest.json'))
        assert manifest['sources']==[] and manifest['mode']=='configuration'
        for info in archive.infolist():
            assert not PurePosixPath(info.filename).is_absolute() and '..' not in PurePosixPath(info.filename).parts
            assert stat.S_IFMT(info.external_attr>>16)==stat.S_IFREG
            content=archive.read(info)
            assert b'Confidential source should not be exported.' not in content
            assert b'Private conversation wording' not in content
            assert key.encode() not in content and secret.encode() not in content


def test_snapshot_only_selected_owner_sources_no_template_injection(owner,project):
    base,doc=ingest(owner,project,b'The refund period is thirty days.','../../$(touch pwned).txt')
    ingest(owner,project,b'Excluded document content must stay private.','other.txt')
    response=create(owner,project,mode='snapshot',document_ids=[doc['id']],acknowledge_copy=True)
    result,data=complete(owner,project,response)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest=json.loads(archive.read('config/manifest.json'))
        assert len(manifest['sources'])==1
        source=manifest['sources'][0]
        assert source['name']=='$(touch pwned).txt'
        assert archive.read(source['path'])==b'The refund period is thirty days.'
        assert all('touch' not in n for n in archive.namelist())
        assert all(b'Excluded document content' not in archive.read(n) for n in archive.namelist())
        assert b'$(touch pwned)' not in archive.read('README.md')
        assert b'$(touch pwned)' not in archive.read('compose.yaml')


def test_export_requires_owner_and_correct_project_selection(owner,project,client):
    base,doc=ingest(owner,project)
    key=owner.post(base+'/keys',json={'name':'scoped','scopes':['query','read','documents']}).json()['secret']
    assert owner.post(base+'/exports',headers={'Authorization':'Bearer '+key},json={}).status_code==403
    second=owner.post('/v1/projects',json={'name':'Another collection'}).json()
    assert create(owner,second,mode='snapshot',document_ids=[doc['id']],acknowledge_copy=True).status_code==404
    response=create(owner,project)
    assert response.status_code==202
    job_id=response.json()['id']
    assert owner.get(f'/v1/projects/{second["id"]}/exports/{job_id}').status_code==404
    owner.post('/v1/auth/logout')
    owner.post('/v1/auth/register',json={'email':'other@example.com','password':'different-user-password'})
    assert owner.get(base+'/exports/'+job_id).status_code==404
    assert owner.get(base+'/exports/'+job_id+'/download').status_code==404


@pytest.mark.parametrize('body',[
    {'mode':'unknown'}, {'mode':'snapshot'},
    {'mode':'snapshot','document_ids':['x'],'acknowledge_copy':False},
    {'mode':'configuration','document_ids':['x']},
    {'mode':'snapshot','document_ids':['x','x'],'acknowledge_copy':True},
    {'provider_secret':'do-not-accept'},
])
def test_invalid_export_inputs(owner,project,body):
    assert create(owner,project,**body).status_code==422


def test_limits_expiry_cleanup_and_duplicate_jobs(owner,project,monkeypatch):
    response=create(owner,project)
    assert create(owner,project).status_code==409
    result,data=complete(owner,project,response)
    with SessionLocal() as db:
        job=db.get(ExportJob,result['id']);job.expires_at=time.time()-1;db.commit()
    path=f'/v1/projects/{project["id"]}/exports/{result["id"]}'
    assert owner.get(path+'/download').status_code==410
    assert not exports.artifact(result['id']).exists()
    monkeypatch.setattr(settings(),'export_storage_mb',1)
    assert create(owner,project).status_code==429


def test_deleted_or_changed_sources_fail_without_publishing(owner,project):
    base,doc=ingest(owner,project)
    response=create(owner,project,mode='snapshot',document_ids=[doc['id']],acknowledge_copy=True)
    owner.delete(base+'/documents/'+doc['id'])
    assert exports.run_once()
    result=owner.get(base+'/exports/'+response.json()['id']).json()
    assert result['status']=='failed'
    assert not exports.artifact(result['id']).exists()


def test_archive_size_checksum_and_symlink_safeguards(owner,project,monkeypatch,tmp_path):
    base,doc=ingest(owner,project)
    response=create(owner,project,mode='snapshot',document_ids=[doc['id']],acknowledge_copy=True)
    with SessionLocal() as db:
        stored=db.get(Document,doc['id'])
        path=settings().storage_dir/stored.storage_name
        original=path.read_bytes();path.write_bytes(b'changed source')
    assert exports.run_once()
    assert owner.get(base+'/exports/'+response.json()['id']).json()['status']=='failed'
    path.write_bytes(original)
    with pytest.raises(ExportError):scan('../outside.py',b'')
    with pytest.raises(ExportError):scan('C:/outside.py',b'')
    with pytest.raises(ExportError):scan('.env',b'')
    with pytest.raises(ExportError):scan('app/main.py',b'sk-proj-'+b'A'*32)
    with pytest.raises(ExportError):scan('config/manifest.json',b'private-secret-123',['private-secret-123'])
    from app.export_compiler import safe_source
    with pytest.raises(ExportError):safe_source('../escape.txt',0,'0'*64)
    link=settings().storage_dir/('a'*32+'.txt')
    try:link.symlink_to(path)
    except OSError:pass # Windows without symlink permission; reparse guards also run in Linux CI.
    else:
        try:
            with pytest.raises(ExportError):safe_source(link.name,len(original),hashlib.sha256(original).hexdigest())
        finally:link.unlink()
    response=create(owner,project)
    monkeypatch.setattr(settings(),'export_max_archive_mb',0)
    assert exports.run_once()
    assert owner.get(base+'/exports/'+response.json()['id']).json()['status']=='failed'


def test_expired_lease_recovers_and_template_changes_are_visible(owner,project,monkeypatch):
    response=create(owner,project)
    with SessionLocal() as db:
        job=db.get(ExportJob,response.json()['id'])
        job.status='generating';job.lease_until=time.time()-1;job.lease_token='old';job.attempts=1
        db.commit()
    complete(owner,project,response)
    response=create(owner,project)
    with SessionLocal() as db:
        job=db.get(ExportJob,response.json()['id']);config=json.loads(json.dumps(job.config))
        config['manifest']['template_sha256']='0'*64;job.config=config;db.commit()
    assert exports.run_once()
    result=owner.get(f'/v1/projects/{project["id"]}/exports/{response.json()["id"]}').json()
    assert result['status']=='failed' and 'template version changed' in result['error']
