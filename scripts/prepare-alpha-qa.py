"""Prepare internal-only alpha browser fixtures; never contacts external testers."""
import json
from pathlib import Path
import secrets
import subprocess
import httpx
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'artifacts/m4-private-credentials.json';path.parent.mkdir(exist_ok=True)
if path.exists():credentials=json.loads(path.read_text())
else:
    credentials={'admin_email':'operator-m4@example.com','admin_password':secrets.token_urlsafe(24)}
    result=subprocess.run(['docker','compose','--env-file','.env.alpha','-p','ragforge-m4-alpha','-f','compose.yaml','-f','compose.alpha.yaml','exec','-T','api','python','-m','app.ops','bootstrap-admin','--email',credentials['admin_email'],'--password-stdin'],cwd=ROOT,input=credentials['admin_password']+'\n',text=True,capture_output=True)
    if result.returncode:raise RuntimeError('Could not initialize isolated QA administrator; inspect operator state')
with httpx.Client(base_url='https://localhost:8443/api',verify=False,headers={'Origin':'https://localhost:8443'},timeout=30) as client:
    client.post('/v1/auth/login',json={'email':credentials['admin_email'],'password':credentials['admin_password']}).raise_for_status()
    for name in ('desktop','mobile'):
        response=client.post('/v1/admin/invites',json={});response.raise_for_status();credentials[name+'_invite']=response.json()['token']
path.write_text(json.dumps(credentials));path.chmod(0o600)
print('Internal QA invitations prepared in ignored local credentials file.')
