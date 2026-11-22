"""API client for import, query, status and explicit index rebuild."""
import argparse
from pathlib import Path
import httpx

parser=argparse.ArgumentParser()
parser.add_argument("action",choices=["status","import","query","reindex"])
parser.add_argument("value",nargs="?")
parser.add_argument("--url",default="http://localhost:8020")
args=parser.parse_args()
key=(Path(__file__).resolve().parents[1]/".standalone-key").read_text().strip()
with httpx.Client(base_url=args.url,headers={"Authorization":"Bearer "+key},timeout=120) as client:
    if args.action=="import":
        path=Path(args.value or "")
        with path.open("rb") as source:response=client.post("/v1/documents",files={"file":(path.name,source)})
    elif args.action=="query":response=client.post("/v1/query",json={"question":args.value})
    elif args.action=="reindex":response=client.post("/v1/reindex")
    else:response=client.get("/v1/status")
    response.raise_for_status()
    print(response.text)
