"""Create ignored private-alpha deployment settings without fixed credentials."""
import argparse
import json
import os
from pathlib import Path
import secrets

parser=argparse.ArgumentParser()
parser.add_argument('--file',default='.env.alpha')
parser.add_argument('--origin',default='https://localhost:8443')
args=parser.parse_args()
from urllib.parse import urlparse
origin=urlparse(args.origin)
if origin.scheme!='https' or not origin.hostname or origin.path not in ('','/') or origin.username or origin.password or origin.query or origin.fragment:parser.error('Use an HTTPS origin without credentials, path or query')
target=Path(args.file)
if target.exists() or target.is_symlink():raise SystemExit('Private settings already exist; preserve their database password')
fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as out:
    out.write('RAGFORGE_ENV_FILE='+json.dumps(target.resolve().as_posix())+'\n')
    out.write('POSTGRES_PASSWORD='+secrets.token_hex(32)+'\nALPHA_HOST='+origin.hostname+'\nALPHA_ORIGIN='+args.origin.rstrip('/')+'\nALPHA_HTTPS_PORT='+str(origin.port or 443)+'\nAPI_PORT=8040\nWEB_PORT=3040\n')
print('Private-alpha environment initialized. Keep this file private; bootstrap the administrator with app.ops after startup.')
