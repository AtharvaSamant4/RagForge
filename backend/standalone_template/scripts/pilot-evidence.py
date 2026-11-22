"""Explicit offline proof download. Never contacts the hosted application."""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

parser = argparse.ArgumentParser(description=__doc__)
root = Path(__file__).resolve().parents[1]
values=dict(line.split('=',1) for line in (root/'.env').read_text(encoding='utf-8').splitlines() if '=' in line and not line.startswith('#')) if (root/'.env').is_file() else {}
port=int(values.get('API_PORT','8020'))
if not 1024<=port<=65535:raise SystemExit('Invalid configured API port')
parser.add_argument('--url', default=f'http://127.0.0.1:{port}')
parser.add_argument('--output', default='runtime-evidence.json')
args = parser.parse_args()
if not (root/'.standalone-key').is_file():raise SystemExit('Initialize first with python scripts/init.py; keep the generated credential files private')
url = urlsplit(args.url)
if not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/') or url.scheme not in ('http', 'https') or url.scheme == 'http' and url.hostname not in ('localhost', '127.0.0.1', '::1'):
    parser.error('Use an origin URL; remote deployments require verified HTTPS')
key = (root / '.standalone-key').read_text(encoding='utf-8').strip()
request = Request(args.url.rstrip('/') + '/v1/pilot-evidence', headers={'Authorization': 'Bearer ' + key})
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise SystemExit('Refusing redirects for an authenticated evidence request')


with build_opener(NoRedirect()).open(request, timeout=30) as response:
    raw = response.read(65537)
if len(raw) > 65536:
    raise SystemExit('Evidence exceeded its size limit')
evidence = json.loads(raw)
if set(evidence) != {'payload', 'signature'}:
    raise SystemExit('Unexpected runtime evidence response')
if not isinstance(evidence['payload'], dict) or set(evidence['payload']) != {'version','deployment_id','export_id','template_sha256','challenge','boot_id','started_at','cited_query_at','database_ready'}:
    raise SystemExit('Unexpected runtime metadata fields')
target = Path(args.output)
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
    json.dump(evidence, output, indent=2); output.write('\n')
print('Saved offline runtime evidence. Import it explicitly in the opted-in hosted pilot screen. No hosted request was made.')
