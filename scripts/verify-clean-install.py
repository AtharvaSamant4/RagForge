"""Install an exact remote commit in a fresh clone and fresh Docker volumes.

The Python/httpx driver is test infrastructure. The installed application uses
Docker-built dependencies, not a host virtualenv, model cache or secret file.
No historical Compose application or volume is removed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
(ROOT/'artifacts').mkdir(exist_ok=True)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repository',default='https://github.com/AtharvaSamant4/RagForge.git')
parser.add_argument('--commit',default=None)
parser.add_argument('--port',type=int,default=8026)
args=parser.parse_args()
commit=args.commit or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
nonce=secrets.token_hex(4);project='ragforge-m5-clean-'+nonce
directory=ROOT/'artifacts'/('m5-clean-install-'+nonce)
origin='http://localhost:3060'
settings_names={'DATABASE_URL','POSTGRES_PASSWORD','API_PORT','WEB_PORT','APP_ORIGINS','RAGFORGE_ENV_FILE','EMBEDDING_PROVIDER','GENERATION_PROVIDER','HOSTED_DAILY_REQUESTS','HOSTED_DAILY_INPUT_CHARS','HOSTED_CALL_INPUT_CHARS','COMPOSE_PROJECT_NAME','OPENAI_API_KEY','REGISTRATION_MODE','ALLOW_REGISTRATION','ALLOW_PUBLIC_WIDGETS','COOKIE_SECURE'}
env={k:v for k,v in os.environ.items() if k not in settings_names}
report={'schema_version':1,'cohort':'engineering_qa','human_trial':False,'source_commit':commit,'compose_project':project,'protocol':'Actual remote clone at exact commit; no inherited app .env/virtualenv/node_modules or model/database volume. Docker build --no-cache --pull installs pinned app dependencies. Public sample through hosted frontend proxy and external API, then generated Docker app with hosted source stopped. Driver Python/httpx is verification infrastructure, not an application dependency assumption.'}
started=time.perf_counter();compose=None;independent_directory=None


def command(argv,cwd=ROOT):
    result=subprocess.run(argv,cwd=cwd,env=env,text=True,capture_output=True)
    with (ROOT/'artifacts/m5-clean-install-commands.log').open('a',encoding='utf-8') as log:
        log.write(result.stdout+result.stderr+'\n')
    if result.returncode:raise RuntimeError('Clean installation command failed; inspect the ignored installation command log')
    return result.stdout.strip()


def checked(response):response.raise_for_status();return response.json()
def wait(fn,seconds=360):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except httpx.HTTPError:pass
        time.sleep(1)
    raise TimeoutError('Clean application failed to reach required state')


try:
    print('Cloning exact remote source into a new directory',flush=True)
    command(['git','clone','--no-checkout',args.repository,str(directory)])
    # Pull-request CI uses a temporary merge commit, which need not be reachable
    # from a normal branch clone. Fetch that exact object before checking out.
    command(['git','fetch','origin',commit],directory)
    command(['git','checkout','--detach',commit],directory)
    assert command(['git','rev-parse','HEAD'],directory)==commit
    assert (directory/'backend/app/pilot.py').is_file(), 'Expected M5 source commit'
    assert all(not (directory/name).exists() for name in ('.env','.venv','frontend/node_modules','data'))
    values={line.split('=',1)[0]:line.split('=',1)[1] for line in (directory/'.env.example').read_text(encoding='utf-8-sig').splitlines() if '=' in line and not line.startswith('#')}
    values.update(POSTGRES_PASSWORD=secrets.token_hex(32),API_PORT='8060',WEB_PORT='3060',APP_ORIGINS=origin,RAGFORGE_ENV_FILE=json.dumps((directory/'.env').as_posix()),EMBEDDING_PROVIDER='semantic',GENERATION_PROVIDER='extractive',HOSTED_DAILY_REQUESTS='0',OPENAI_API_KEY='',REGISTRATION_MODE='development',ALLOW_REGISTRATION='true',COOKIE_SECURE='false')
    private=directory/'.env';private.write_text(''.join(k+'='+v+'\n' for k,v in values.items()),encoding='utf-8');private.chmod(0o600)
    compose=['docker','compose','--env-file',str(private),'-p',project]
    print('Building application dependencies without cached build steps',flush=True)
    command(compose+['build','--no-cache','--pull'],directory)
    report['fresh_dependency_build_seconds']=round(time.perf_counter()-started,3)
    cache=project+'_model_cache';command(['docker','volume','create','--label','com.docker.compose.project='+project,'--label','com.docker.compose.volume=model_cache',cache])
    command(['docker','run','--rm','-v',cache+':/cache',project+'-api','python','-c',"from pathlib import Path; assert not any(Path('/cache').iterdir()); print('Verified empty model volume')"])
    report['model_volume_verified_empty_before_start']=True
    assert subprocess.run(['docker','volume','inspect',project+'_postgres_data'],capture_output=True).returncode!=0
    report['database_volume_absent_before_start']=True
    command(compose+['up','--no-build','-d'],directory)
    with httpx.Client(base_url=origin+'/api',timeout=120,headers={'Origin':origin}) as client:
        wait(lambda:client.get('/ready').status_code==200)
        report['ready_seconds_from_clone_start']=round(time.perf_counter()-started,3)
        email='engineering-clean-'+nonce+'@example.com';password=secrets.token_urlsafe(32)
        checked(client.post('/v1/auth/register',json={'email':email,'password':password}))
        p=checked(client.post('/v1/projects',json={'name':'Clean installation public sample'}));base='/v1/projects/'+p['id']
        doc=checked(client.post(base+'/documents',files={'file':('acme-handbook.pdf',(directory/'samples/acme-handbook.pdf').read_bytes())}))
        def indexed():
            docs=checked(client.get(base+'/documents'))
            if any(d['status']=='failed' for d in docs):raise AssertionError('Fresh sample parsing/indexing failed')
            return docs and all(d['status']=='ready' for d in docs)
        wait(indexed)
        questions=['What is the refund period?','How long does a refund take?','Who won the Martian election in 2050?']
        before=[{'question':q,'result':checked(client.post(base+'/query',json={'question':q}))} for q in questions]
        assert before[0]['result']['citations'] and before[-1]['result']['refused']
        report['time_to_first_cited_answer_seconds_from_clone_start']=round(time.perf_counter()-started,3)
        key=checked(client.post(base+'/keys',json={'name':'Clean external Python client'}))['secret']
        with httpx.Client(base_url='http://localhost:8060',timeout=90,headers={'Authorization':'Bearer '+key}) as external:
            assert checked(external.post(base+'/query',json={'question':questions[0]}))['citations']
        report['external_api_client']='Python/httpx with project key and no session cookie; passed'
        job=checked(client.post(base+'/exports',json={'mode':'snapshot','document_ids':[doc['id']],'acknowledge_copy':True}))
        def exported():
            state=checked(client.get(base+'/exports/'+job['id']))
            if state['status']=='failed':raise AssertionError('Clean snapshot export failed')
            return state if state['status']=='ready' else None
        job=wait(exported)
        response=client.get(base+'/exports/'+job['id']+'/download');response.raise_for_status()
        (directory/'artifacts').mkdir(exist_ok=True)
        archive=directory/'artifacts/clean-application.zip';archive.write_bytes(response.content)
        comparison=directory/'artifacts/clean-before.json';comparison.write_text(json.dumps({'before':before,'export':job}))
    command(compose+['stop'],directory)
    command([sys.executable,str(directory/'scripts/verify-standalone.py'),'--source','http://localhost:8060','--origin',origin,'--archive',str(archive),'--comparison',str(comparison),'--port',str(args.port),'--output',str(ROOT/'docs/qa/m5-clean-standalone-acceptance.json')],directory)
    acceptance=json.loads((ROOT/'docs/qa/m5-clean-standalone-acceptance.json').read_text())
    independent_directory=Path(acceptance['extracted_directory'])
    report.update(status='passed',source_stopped_during_independent_query=True,independent_restart_and_clients='passed',time_to_independent_deployment_seconds_from_clone_start=round(time.perf_counter()-started,3),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),model_runtime='Pinned CPU MiniLM, downloaded into a verified initially empty volume',pilot_collection_default_off=True)
finally:
    if compose:command(compose+['stop'],directory)
    if independent_directory:command(['docker','compose','stop'],independent_directory)
    report['created_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    report['checkout_directory']=str(directory)
    (ROOT/'docs/qa/m5-clean-install.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS: clean remote installation, fresh model/DB, PDF/citations, external API, export and independent Docker query/restart. No human usability claim.')
