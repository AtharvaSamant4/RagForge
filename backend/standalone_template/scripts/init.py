"""No dependencies required. Secrets stay in ignored local files, outside the image."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets

ROOT=Path(__file__).resolve().parents[1]


def initialize(port=8020,rotate=False):
    env=ROOT/".env"
    key=ROOT/".standalone-key"
    if env.is_symlink() or key.is_symlink():
        raise SystemExit("Refusing symlink credential files")
    if env.exists() and not rotate:
        raise SystemExit("Already initialized. Use --rotate to rotate only the API key; keep the database password.")
    lines=env.read_text(encoding="utf-8").splitlines() if env.exists() else (ROOT/".env.example").read_text(encoding="utf-8").splitlines()
    raw="sa_"+secrets.token_urlsafe(32)
    values={"STANDALONE_API_KEY_HASH":hashlib.sha256(raw.encode()).hexdigest()}
    if not env.exists():
        values.update(POSTGRES_PASSWORD=secrets.token_hex(32),API_PORT=str(port),COMPOSE_PROJECT_NAME="rag-"+secrets.token_hex(5))
    names=set(values)
    lines=[line for line in lines if line.partition("=")[0] not in names]
    text="\n".join(lines+[f"{k}={v}" for k,v in values.items()])+"\n"
    for target,content in [(key,raw+"\n"),(env,text)]:
        temporary=target.with_suffix(target.suffix+".tmp-"+secrets.token_hex(4))
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as out:out.write(content)
        os.replace(temporary,target)
    print("Initialized. API key is in .standalone-key; .env contains its hash and an independent database password. Keep both private.")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8020)
    parser.add_argument("--rotate",action="store_true")
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error("Port must be between 1024 and 65535")
    initialize(args.port,args.rotate)
