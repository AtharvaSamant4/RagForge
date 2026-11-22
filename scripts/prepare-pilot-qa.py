"""Enroll synthetic engineering QA accounts only; never sends external messages."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlsplit
import httpx

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project',default='ragforge-m5-alpha',choices=['ragforge-m5-alpha','ragforge-m5','ragforge-m4-alpha'])
parser.add_argument('--base-url',default='https://localhost:8445')
parser.add_argument('--env-file',default='.env.m5-alpha')
parser.add_argument('--admin-file',help='Existing ignored QA administrator credentials; required for M4 CI namespace')
parser.add_argument('--reset-study-accounts',action='store_true',help='Erase only desktop/mobile synthetic QA study records before a rerun; preserve runtime proof account')
args=parser.parse_args()
url=urlsplit(args.base_url)
if url.hostname not in ('localhost','127.0.0.1') or url.scheme not in ('http','https') or url.path not in ('','/') or url.username or url.password:parser.error('QA is restricted to a loopback origin')
if args.project=='ragforge-m4-alpha' and not args.admin_file:parser.error('M4 namespace requires existing CI QA credentials')
command=['docker','compose','--env-file',args.env_file,'-p',args.project]
if args.project.endswith('alpha'):command+=['-f','compose.yaml','-f','compose.alpha.yaml']
target=ROOT/'artifacts/m5-pilot-credentials.json'
target.parent.mkdir(exist_ok=True)
credentials=json.loads(target.read_text()) if target.exists() else {'base_url':args.base_url,'project':args.project,'env_file':args.env_file}
if credentials['base_url']!=args.base_url or credentials['project']!=args.project:raise SystemExit('Use a separate checkout/artifact directory for another QA deployment')
if args.admin_file:
    existing=json.loads(Path(args.admin_file).read_text())
    credentials.update(admin_email=existing['admin_email'],admin_password=existing['admin_password'])
if not credentials.get('admin_email'):
    credentials.update(admin_email='engineering-pilot-operator-'+secrets.token_hex(5)+'@example.com',admin_password=secrets.token_urlsafe(32))
    result=subprocess.run(command+['exec','-T','api','python','-m','app.ops','bootstrap-admin','--email',credentials['admin_email'],'--password-stdin'],input=credentials['admin_password']+'\n',text=True,capture_output=True)
    if result.returncode:raise SystemExit('QA administrator initialization failed; no existing credentials were overwritten')
    target.write_text(json.dumps(credentials),encoding='utf-8');target.chmod(0o600)


def request(client,method,path,**kwargs):
    end=time.monotonic()+130
    while True:
        response=client.request(method,path,**kwargs)
        if response.status_code!=429 or time.monotonic()>=end:
            response.raise_for_status();return response.json()
        # Respect fixed-window auth limits; do not raise quotas for QA.
        time.sleep(min(5,max(1,int(response.headers.get('Retry-After','5')))))


with httpx.Client(base_url=args.base_url+'/api',verify=False,timeout=120,headers={'Origin':args.base_url}) as operator:
    request(operator,'POST','/v1/auth/login',json={'email':credentials['admin_email'],'password':credentials['admin_password']})
    mode=request(operator,'GET','/health')['registration_mode']
    for profile in ('desktop','mobile','runtime'):
        with httpx.Client(base_url=args.base_url+'/api',verify=False,timeout=120,headers={'Origin':args.base_url}) as client:
            if profile+'_email' not in credentials:
                credentials[profile+'_email']='engineering-pilot-'+profile+'-'+secrets.token_hex(5)+'@example.com'
                credentials[profile+'_password']=secrets.token_urlsafe(32)
                body={'email':credentials[profile+'_email'],'password':credentials[profile+'_password']}
                if mode=='invite':body['invite_token']=request(operator,'POST','/v1/admin/invites',json={})['token']
                request(client,'POST','/v1/auth/register',json=body)
            else:request(client,'POST','/v1/auth/login',json={'email':credentials[profile+'_email'],'password':credentials[profile+'_password']})
            state=request(client,'GET','/v1/pilot/me')
            if args.reset_study_accounts and profile!='runtime' and state['enrolled']:
                if state['cohort']!='engineering_qa':raise SystemExit('Refusing to reset a human participant')
                request(client,'DELETE','/v1/pilot/me');state={'enrolled':False}
            if not state['enrolled']:
                request(operator,'POST','/v1/admin/pilot/participants',json={'email':credentials[profile+'_email'],'cohort':'engineering_qa','authorization_obtained':True,'authorization_reference':'Synthetic engineering QA automation only; no external participant'})
            if profile=='runtime':request(client,'PUT','/v1/pilot/consent',json={'accepted':True,'version':'pilot-v1'})
        target.write_text(json.dumps(credentials),encoding='utf-8');target.chmod(0o600)
print('Prepared engineering-only QA accounts. Human participant/trial counts remain zero; credentials are in ignored private artifacts.')
