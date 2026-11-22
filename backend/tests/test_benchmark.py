import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from benchmarks.metrics import score


def test_benchmark_dataset_has_explicit_valid_refs_and_separate_review_status():
    root=ROOT/"benchmarks"
    candidates=json.loads((root/"candidates.json").read_text())
    fixtures=json.loads((root/"fixtures.json").read_text())
    assert len(candidates)>=100 and len(fixtures)>=20
    assert len({c["question"] for c in candidates})==len(candidates)
    assert all(c["status"]=="candidate_unverified" for c in candidates)
    assert all(c["status"]=="fixture_contract" for c in fixtures)
    assert {"long_document","multi_document","different_sections","contradictory","unanswerable","adversarial","synonym","paraphrase","exact","repeated_terminology"} <= {c["category"] for c in fixtures}
    for case in fixtures+candidates:
        for ref in case["source_refs"]:
            assert ref["quote"] in (root/"corpus"/ref["document"]).read_text()


def test_recall_requires_the_referenced_passage_not_just_the_document():
    case={"source_refs":[{"document":"a.md","quote":"relevant passage"}],"expected_quotes":["relevant passage"],"expect_refusal":False}
    result={"retrieved":[{"chunk_id":"c","document_id":"a","document_name":"a.md","text":"irrelevant chapter"}],"citations":[],"refused":False,"retrieval_latency_ms":1,"latency_ms":2}
    metrics=score(case,result)
    assert metrics["recall_at_5"]==0 and metrics["hit_at_1"]==0 and metrics["mrr"]==0
