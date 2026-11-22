"""Real opt-in funnel through an independent Docker app while QA source is stopped."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port',type=int,default=8025)
args=parser.parse_args()
credentials_path=ROOT/'artifacts/m5-pilot-credentials.json'
credentials=json.loads(credentials_path.read_text())
project=credentials['project'];origin=credentials['base_url']
if project not in ('ragforge-m5-alpha','ragforge-m5','ragforge-m4-alpha'):raise SystemExit('Disposable QA Compose namespace required')
compose=['docker','compose','--env-file',credentials['env_file'],'-p',project]
if project.endswith('alpha'):compose+=['-f','compose.yaml','-f','compose.alpha.yaml']
output=ROOT/'docs/qa/m5-pilot-runtime.json'
report={'cohort':'engineering_qa','human_participation':False,'protocol':'Public sample only; explicit synthetic QA consent, actual hosted API-key query, opted-in ZIP, own Docker DB/key/model cache, source Compose stopped during independent acceptance, restart, authenticated offline proof, signature/ownership verification and idempotent import. Signed self-hosted evidence is not remote attestation.'}


def checked(response):
    response.raise_for_status();return response.json()


def wait(fn,seconds=300):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except httpx.HTTPError:pass
        time.sleep(1)
    raise TimeoutError('Disposable pilot runtime did not reach the required state')


def command(argv):
    result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
    if result.returncode:
        (ROOT/'artifacts/m5-runtime-command-failure.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        raise RuntimeError('QA command failed; inspect the ignored runtime command log')
    return result.stdout


with httpx.Client(base_url=origin+'/api',headers={'Origin':origin},verify=False,timeout=120) as client:
    checked(client.post('/v1/auth/login',json={'email':credentials['runtime_email'],'password':credentials['runtime_password']}))
    assert checked(client.get('/v1/pilot/me'))['cohort']=='engineering_qa'
    p=checked(client.post('/v1/projects',json={'name':'Engineering-only independent pilot runtime'}));base='/v1/projects/'+p['id']
    doc=checked(client.post(base+'/documents',files={'file':('acme-handbook.pdf',(ROOT/'samples/acme-handbook.pdf').read_bytes())}))
    def indexed():
        rows=checked(client.get(base+'/documents'))
        if any(d['status']=='failed' for d in rows):raise AssertionError('Sample ingestion failed')
        return rows and all(d['status']=='ready' for d in rows)
    wait(indexed)
    questions=['What is the refund period?','How long does a refund take?','Who won the Martian election in 2050?']
    before=[{'question':q,'result':checked(client.post(base+'/query',json={'question':q}))} for q in questions]
    assert before[0]['result']['citations'] and before[-1]['result']['refused']
    key=checked(client.post(base+'/keys',json={'name':'Engineering-only external API client'}))['secret']
    with httpx.Client(base_url=origin+'/api',verify=False,timeout=120,headers={'Authorization':'Bearer '+key}) as external:
        assert checked(external.post(base+'/query',json={'question':questions[0]}))['citations']
    job=checked(client.post(base+'/exports',json={'mode':'snapshot','document_ids':[doc['id']],'acknowledge_copy':True,'include_pilot_evidence':True}))
    def exported():
        current=checked(client.get(base+'/exports/'+job['id']))
        if current['status']=='failed':raise AssertionError('Opted-in export failed')
        return current if current['status']=='ready' else None
    job=wait(exported)
    archive=ROOT/('artifacts/m5-pilot-'+secrets.token_hex(5)+'.zip')
    response=client.get(base+'/exports/'+job['id']+'/download');response.raise_for_status();archive.write_bytes(response.content);archive.chmod(0o600)
    comparison=ROOT/'artifacts/m5-runtime-before.json';comparison.write_text(json.dumps({'before':before,'export':job}),encoding='utf-8')
    pre=checked(client.get('/v1/pilot/me'))['funnel']
    # A fresh export cannot create the deployment stages; an older QA run may exist.
    report['before_runtime_funnel']=pre
    stopped=False
    try:
        print('Stopping only the disposable QA source; building/querying the independent package',flush=True)
        command(compose+['stop']);stopped=True
        try:
            httpx.get(origin+'/api/health',verify=False,timeout=3)
            raise AssertionError('QA source was expected to be unavailable')
        except httpx.HTTPError:pass
        command([sys.executable,'scripts/verify-standalone.py','--source',origin,'--origin',origin,'--port',str(args.port),'--archive',str(archive),'--comparison',str(comparison),'--output','docs/qa/m5-standalone-acceptance.json'])
        standalone=json.loads((ROOT/'docs/qa/m5-standalone-acceptance.json').read_text())
        directory=Path(standalone['extracted_directory'])
        standalone_key=(directory/'.standalone-key').read_text().strip()
        with httpx.Client(base_url=f'http://localhost:{args.port}',headers={'Authorization':'Bearer '+standalone_key},timeout=60) as independent:
            query=checked(independent.post('/v1/query',json={'question':questions[0]}));assert query['citations']
            proof=checked(independent.get('/v1/pilot-evidence'))
        proof_file=ROOT/'artifacts/m5-runtime-evidence.json';proof_file.write_text(json.dumps(proof),encoding='utf-8');proof_file.chmod(0o600)
        report['source_unavailable_during_independent_query']=True
        report['independent_cited_answer']=True
    finally:
        if stopped:command(compose+['up','--no-build','-d'])
    wait(lambda:client.get('/ready').status_code==200)
    accepted=checked(client.post('/v1/pilot/deployment-evidence',json=proof))
    assert accepted['cited_query_observed_at'] is not None
    assert checked(client.post('/v1/pilot/deployment-evidence',json=proof))['duplicate']
    after=checked(client.get('/v1/pilot/me'))['funnel']
    assert all(stage['completed'] for stage in after['stages'])
    report.update(after_runtime_funnel=after,evidence_acceptance=accepted,duplicate_import_deduplicated=True,standalone_archive_sha256=standalone['archive_sha256'],standalone_generator=json.loads((directory/'config/manifest.json').read_text())['generator_version'],source_project=project)
credentials.update(runtime_proof_path=str(proof_file),runtime_project_id=p['id'],runtime_standalone_directory=str(directory))
credentials_path.write_text(json.dumps(credentials),encoding='utf-8');credentials_path.chmod(0o600)
report['created_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS: all ten technical stages from actual engineering QA operations, independent runtime proof and replay-safe import. Human trial count remains zero.')
