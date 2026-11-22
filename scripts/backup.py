"""Encrypted consistent backup/empty-target restore for explicit Compose projects.

Pauses only the named application's API/worker, preserving volumes. Raw secrets
are never command arguments; plaintext staging is private and removed afterward.
"""
import argparse
import getpass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import shutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.backup_crypto import encrypt,decrypt

STORAGE_CODE=r'''
import hashlib,io,json,os,re,sys,tarfile
from pathlib import Path
kind=sys.argv[1];action=sys.argv[2]
if kind=='standalone':
 import app.bootstrap
 from app.engine.config import settings
 from app.engine.db import SessionLocal
 from app.engine.models import Document
else:
 from app.config import settings
 from app.db import SessionLocal
 from app.models import Document
from sqlalchemy import select
root=settings().storage_dir;root.mkdir(parents=True,exist_ok=True)
if action=='config':
 if kind=='standalone':
  from app.bootstrap import MANIFEST
  print(json.dumps(MANIFEST,sort_keys=True))
 else:
  from app.embeddings import profile
  from sqlalchemy import text
  with SessionLocal() as db: schema=db.scalar(text('SELECT version_num FROM alembic_version'))
  print(json.dumps({'embedding_profile':profile(),'schema':schema},sort_keys=True))
elif action=='empty':
 if any(root.iterdir()):raise SystemExit('Restore target storage is not empty')
elif action=='dump':
 with SessionLocal() as db:
  docs=list(db.scalars(select(Document)))
  with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
   for doc in docs:
    if not re.fullmatch(r'[a-f0-9]{32}\.(pdf|docx|txt|md|csv)',doc.storage_name):raise SystemExit('Unsafe source identity')
    path=root/doc.storage_name
    if path.is_symlink() or not path.is_file():raise SystemExit('Missing or unsafe source')
    data=path.read_bytes()
    if len(data)!=doc.size_bytes or hashlib.sha256(data).hexdigest()!=doc.sha256:raise SystemExit('Source integrity failure')
    info=tarfile.TarInfo(doc.storage_name);info.size=len(data);info.mode=0o600
    archive.addfile(info,io.BytesIO(data))
elif action=='restore':
 with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
  for info in archive:
   if not info.isfile() or not re.fullmatch(r'[a-f0-9]{32}\.(pdf|docx|txt|md|csv)',info.name) or info.size>20*1024**2:raise SystemExit('Unsafe source archive')
   path=root/info.name
   with path.open('xb') as out:
    source=archive.extractfile(info)
    while block:=source.read(1024*1024):out.write(block)
'''


def cli():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['create','restore'])
    parser.add_argument('--project',required=True)
    parser.add_argument('--directory',default=str(ROOT))
    parser.add_argument('--compose-file',action='append',default=[],help='Repeat for overlays; paths are relative to --directory')
    parser.add_argument('--env-file',help='Private Compose interpolation env file')
    parser.add_argument('--kind',choices=['hosted','standalone'],default='hosted')
    parser.add_argument('--file',required=True)
    parser.add_argument('--allow-downtime',action='store_true')
    parser.add_argument('--confirm-empty-restore',action='store_true')
    parser.add_argument('--passphrase-stdin',action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,60}',args.project):parser.error('Use an explicit safe Compose project name')
    if not args.allow_downtime:parser.error('--allow-downtime is required: API/worker will be paused for consistency')
    directory=Path(args.directory).resolve();path=Path(args.file).resolve()
    password=sys.stdin.readline().rstrip('\r\n') if args.passphrase_stdin else getpass.getpass('Backup passphrase (20+ characters): ')
    if len(password)<20:parser.error('Passphrase must contain at least 20 characters')
    env=os.environ.copy()
    # A standalone directory's own .env must control its ports/project configuration.
    if args.kind=='standalone':
        for key in ('API_PORT','WEB_PORT','APP_ORIGINS','COMPOSE_PROJECT_NAME'):env.pop(key,None)
    base=['docker','compose','-p',args.project]
    if args.env_file:base+=['--env-file',args.env_file]
    for compose_file in args.compose_file:base+=['-f',compose_file]
    def sha256(path):
        with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
    role='standalone' if args.kind=='standalone' else 'ragforge'
    def run(argv,**kwargs):return subprocess.run(base+argv,cwd=directory,env=env,check=True,**kwargs)
    running=run(['ps','--services','--filter','status=running'],capture_output=True,text=True).stdout.split()
    restore_services=[s for s in ('api','worker') if s in running]
    if args.action=='restore' and not args.confirm_empty_restore:parser.error('--confirm-empty-restore is mandatory')
    with tempfile.TemporaryDirectory(prefix='ragforge-backup-') as temporary:
        work=Path(temporary)
        # Authenticate/decode archive before touching target services or data.
        if args.action=='restore':
            decrypt(path,work/'bundle.tar',password)
            with tarfile.open(work/'bundle.tar','r:') as archive:
                entries=archive.getmembers()
                if {e.name for e in entries}!={'database.dump','sources.tar','manifest.json'} or any(not e.isfile() or e.size>1024**3 for e in entries):raise ValueError('Unsafe backup bundle')
                for entry in entries:
                    with (work/entry.name).open('xb') as out:shutil.copyfileobj(archive.extractfile(entry),out,1024*1024)
            manifest=json.loads((work/'manifest.json').read_text())
            if manifest['schema']!='1' or manifest['kind']!=args.kind:raise ValueError('Backup type/version mismatch')
            if manifest['source_project']==args.project:raise ValueError('Restore must use a separate empty Compose project')
            for name in ('database.dump','sources.tar'):
                if sha256(work/name)!=manifest['sha256'][name]:raise ValueError('Backup component checksum mismatch')
        try:
            if restore_services:run(['stop',*restore_services])
            if args.action=='create':
                with (work/'database.dump').open('xb') as out:
                    exclusions=['sessions','rate_buckets','worker_heartbeats']
                    if args.kind=='hosted':exclusions+=['exports','pilot_participants','pilot_events','pilot_tasks','pilot_issues','pilot_deployments','pilot_operator_state']
                    run(['exec','-T','db','pg_dump','-U',role,'-d',role,'-Fc','--no-owner','--no-acl',*['--exclude-table-data='+table for table in exclusions]],stdout=out)
                with (work/'sources.tar').open('xb') as out:
                    run(['run','--rm','--no-deps','-T','--entrypoint','python','api','-c',STORAGE_CODE,args.kind,'dump'],stdout=out)
                runtime_config=json.loads(run(['run','--rm','--no-deps','-T','--entrypoint','python','api','-c',STORAGE_CODE,args.kind,'config'],capture_output=True,text=True).stdout)
                images=run(['images','--format','json'],capture_output=True,text=True).stdout.strip()
                manifest={'runtime_config':runtime_config,'compose_images':images,'schema':'1','source_project':args.project,'kind':args.kind,'created_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'sha256':{name:sha256(work/name) for name in ('database.dump','sources.tar')},'excluded':['raw API keys','session credentials','environment/provider/database secrets','model cache','ephemeral exports','hosted pilot study/consent/operator records (re-enroll/re-consent after recovery)','TLS/backup encryption keys']}
                (work/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
                with tarfile.open(work/'bundle.tar','w:') as archive:
                    for name in ('database.dump','sources.tar','manifest.json'):archive.add(work/name,arcname=name,recursive=False)
                if (work/'bundle.tar').stat().st_size>1024**3:raise ValueError('Backup exceeds the supported 1 GiB bundle limit')
                path.parent.mkdir(parents=True,exist_ok=True);encrypt(work/'bundle.tar',path,password)
                print(json.dumps({'action':'created','encrypted_bytes':path.stat().st_size,'sha256':sha256(path),'source_project':args.project}))
            else:
                if args.kind=='standalone':
                    target_config=json.loads(run(['run','--rm','--no-deps','-T','--entrypoint','python','api','-c',STORAGE_CODE,args.kind,'config'],capture_output=True,text=True).stdout)
                    if target_config!=manifest['runtime_config']:raise ValueError('Restore requires the original standalone application package/manifest')
                count=run(['exec','-T','db','psql','-U',role,'-d',role,'-tAc',"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"],capture_output=True,text=True).stdout.strip()
                if count!='0':raise ValueError('Restore target database is not empty; nothing was restored')
                run(['run','--rm','--no-deps','-T','--entrypoint','python','api','-c',STORAGE_CODE,args.kind,'empty'])
                # Validate every tar entry before restoring either component.
                with tarfile.open(work/'sources.tar','r:') as archive:
                    total=0;seen=set()
                    for entry in archive:
                        if not entry.isfile() or not re.fullmatch(r'[a-f0-9]{32}\.(pdf|docx|txt|md|csv)',entry.name) or entry.size>20*1024**2 or entry.name in seen:raise ValueError('Unsafe source backup')
                        seen.add(entry.name)
                        total+=entry.size
                        if total>1024**3:raise ValueError('Source backup exceeds restore limit')
                with (work/'sources.tar').open('rb') as inp:
                    run(['run','--rm','--no-deps','-T','--entrypoint','python','api','-c',STORAGE_CODE,args.kind,'restore'],stdin=inp)
                with (work/'database.dump').open('rb') as inp:
                    run(['exec','-T','db','pg_restore','-U',role,'-d',role,'--no-owner','--no-acl','--exit-on-error'],stdin=inp)
                # Resume interrupted durable work in this separate restored DB; old leases cannot publish here.
                run(['exec','-T','db','psql','-U',role,'-d',role,'-c',"UPDATE jobs SET status='queued',lease_token=NULL,lease_until=NULL,available_at=0 WHERE status='processing';"])
                if args.kind=='hosted':run(['exec','-T','db','psql','-U',role,'-d',role,'-c',"UPDATE exports SET status='expired',lease_token=NULL,lease_until=NULL,expires_at=0;"])
                print(json.dumps({'action':'restored','target_project':args.project,'source_project':manifest['source_project'],'sessions':'not restored; sign in again','hosted_providers':'keep disabled until operator budget/key review'}))
        finally:
            if restore_services:run(['up','-d','--no-deps',*restore_services])


if __name__=='__main__':cli()
