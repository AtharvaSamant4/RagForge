"""Exercise safe frontend transport failures against the isolated M4 development stack."""
import json,os,secrets,subprocess,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
import argparse
from urllib.parse import urlparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project',choices=['ragforge-m4','ragforge-ci'],default='ragforge-m4')
parser.add_argument('--base-url',default='http://localhost:3031')
parser.add_argument('--api-port',type=int,default=8031)
args=parser.parse_args()
public=urlparse(args.base_url)
if public.scheme!='http' or public.hostname not in ('localhost','127.0.0.1') or not public.port:parser.error('Use an explicit loopback QA origin/port')
ENV={**os.environ,'API_PORT':str(args.api_port),'WEB_PORT':str(public.port),'APP_ORIGINS':args.base_url}
BASE=['docker','compose','-p',args.project]
def command(args):
 r=subprocess.run(BASE+args,cwd=ROOT,env=ENV,capture_output=True,text=True,check=True);return r.stdout+r.stderr

def wait(client):
 deadline=time.monotonic()+90
 while time.monotonic()<deadline:
  try:
   if client.get('/api/health').status_code==200:return
  except httpx.HTTPError:pass
  time.sleep(1)
 raise TimeoutError('Frontend API did not recover')

with httpx.Client(base_url=args.base_url,headers={'Origin':args.base_url},timeout=30) as c:
 wait(c)
 r=c.post('/api/v1/auth/login',content=b'x'*300000,headers={'content-type':'application/json'})
 assert r.status_code==413 and r.headers.get('x-request-id')
 r=c.post('/api/v1/projects/unknown/documents',content=iter([b'test']),headers={'content-type':'application/octet-stream'})
 assert r.status_code==411
 r=c.get('/api/v1/projects/')
 from urllib.parse import urlparse
 location=urlparse(r.headers.get('location',''))
 assert r.status_code in (307,308) and location.netloc in ('',public.netloc) and location.path.startswith('/api/')
 marker='PRIVATE_PROXY_MARKER_'+secrets.token_hex(12);key='rf_'+secrets.token_urlsafe(32)
 try:
  command(['stop','api'])
  r=c.post('/api/v1/'+marker+'/query?private='+marker,json={'question':marker},headers={'authorization':'Bearer '+key})
  assert r.status_code==503,r.status_code
  body=r.json();assert body['request_id']==r.headers['x-request-id'] and marker not in r.text and key not in r.text
  logs=command(['logs','--no-color','--tail','100','web']);assert marker not in logs and key not in logs
 finally:command(['up','--no-deps','-d','api'])
 wait(c)
 report={'status':'passed','body_limit_status':413,'undeclared_upload_status':411,'redirect_stays_on_public_api_path':True,'upstream_offline_status':503,'upstream_error_request_id':body['request_id'],'private_url_question_authorization_not_logged':True,'recovered_health':200,'protocol':'Stopped only isolated M4 API; preserved volumes; checked safe JSON/request ID/body limits and subsequent recovery. No mutation retry is automatic.'}
 (ROOT/'docs/qa/m4-api-proxy.json').write_text(json.dumps(report,indent=2)+'\n')
 print('PASS: streamed API forwarding, safe upstream outage response, log redaction, body limits and recovery.')
