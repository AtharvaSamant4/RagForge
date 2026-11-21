"""Approval CLI tests use a disposable fake-review dataset, never real approvals."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_review_approval_rejection_and_duplicate_guard_in_disposable_fixture(tmp_path):
    root=Path(__file__).resolve().parents[2]
    target=tmp_path/"benchmarks";target.mkdir();(target/"corpus").mkdir()
    for name in ("review.py","metrics.py","__init__.py"):
        shutil.copyfile(root/"benchmarks"/name,target/name)
    (target/"corpus/source.md").write_text("A deliberately fake test source.")
    candidates=[{"id":f"fake-{i}","question":"A fake question?","category":"test_fixture","source_refs":[{"document":"source.md","quote":"A deliberately fake test source."}],"expected_quotes":["A deliberately fake test source."],"expect_refusal":False,"status":"candidate_unverified","split":"candidate"} for i in range(2)]
    (target/"candidates.json").write_text(json.dumps(candidates))
    command=[sys.executable,str(target/"review.py")]
    assert subprocess.run(command+["approve","--id","fake-0"],capture_output=True).returncode!=0
    options=["--reviewer","AUTOMATED TEST FIXTURE, not a human","--notes","Synthetic CLI test only"]
    subprocess.run(command+["approve","--id","fake-0",*options],capture_output=True,check=True)
    record=json.loads((target/"approved.jsonl").read_text())
    assert record["reviewer"].startswith("AUTOMATED TEST") and record["corpus_sha256"]
    assert record["status"]=="human_approved" and record["split"]=="human_approved"
    duplicate=subprocess.run(command+["approve","--id","fake-0",*options],capture_output=True,text=True)
    assert duplicate.returncode!=0 and "already reviewed" in duplicate.stderr
    subprocess.run(command+["reject","--id","fake-1",*options],capture_output=True,check=True)
    assert len((target/"review-history.jsonl").read_text().splitlines())==2
    assert len((target/"approved.jsonl").read_text().splitlines())==1


def test_changed_corpus_invalidates_approvals_before_any_benchmark_work(tmp_path,monkeypatch):
    from benchmarks import run
    target=tmp_path/"benchmarks";target.mkdir();(target/"corpus").mkdir()
    (target/"corpus/source.md").write_text("Changed fixture source")
    (target/"fixtures.json").write_text("[]")
    (target/"approved.jsonl").write_text(json.dumps({"id":"fake-approval","corpus_sha256":"old-corpus"})+"\n")
    monkeypatch.setattr(run,"ROOT",tmp_path)
    with pytest.raises(ValueError,match="older corpus"):
        run.run(str(tmp_path/"never-written.json"),False,[.32])
    assert not (tmp_path/"never-written.json").exists()
