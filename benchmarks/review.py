"""Explicit human review queue. No automatic promotion of proposed labels."""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from benchmarks.metrics import canonical_bytes
parser = argparse.ArgumentParser()
parser.add_argument("action", choices=["list", "show", "approve", "reject"])
parser.add_argument("--id")
parser.add_argument("--reviewer")
parser.add_argument("--notes")
args = parser.parse_args()
candidates = json.loads((ROOT / "candidates.json").read_text(encoding="utf-8"))
history = ROOT / "review-history.jsonl"
reviewed = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()] if history.exists() else []
if args.action == "list":
    for candidate in candidates:
        if candidate["id"] not in {r["id"] for r in reviewed}:
            print(candidate["id"], "|", candidate["category"], "|", candidate["question"])
else:
    candidate = next((c for c in candidates if c["id"] == args.id), None)
    if not candidate:
        parser.error("Choose an existing candidate with --id")
    print(json.dumps(candidate, indent=2))
    for ref in candidate["source_refs"]:
        print("\nSOURCE: " + ref["document"] + "\n" + (ROOT / "corpus" / ref["document"]).read_text(encoding="utf-8"))
    if args.action != "show":
        if not args.reviewer or not args.notes:
            parser.error("Human approval/rejection requires --reviewer and --notes after inspecting the complete sources")
        if candidate["id"] in {r["id"] for r in reviewed}:
            parser.error("Candidate already reviewed; preserve the audit trail and create a corrected candidate instead")
        record = {**candidate, "reviewer": args.reviewer, "review_notes": args.notes, "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "source_sha256": {ref["document"]: hashlib.sha256((ROOT / "corpus" / ref["document"]).read_bytes()).hexdigest() for ref in candidate["source_refs"]}, "decision": args.action}
        record["corpus_sha256"] = hashlib.sha256(b"".join(p.name.encode()+canonical_bytes(p) for p in sorted((ROOT/"corpus").glob("*.md")))).hexdigest()
        with history.open("a", encoding="utf-8") as out:
            out.write(json.dumps(record) + "\n")
        if args.action == "approve":
            record.update(status="human_approved", split="human_approved")
            with (ROOT / "approved.jsonl").open("a", encoding="utf-8") as out:
                out.write(json.dumps(record) + "\n")
        print("Recorded " + args.action + " by " + args.reviewer)
