"""Real indexing/retrieval benchmark. Does not call paid AI or erase a database.

Run from repository root. Optional DATABASE_URL must refer to a dedicated benchmark DB.
Only the uniquely created benchmark user/projects are deleted by this script.
"""
import argparse
import hashlib
import json
import os
import platform
import random
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///./artifacts/benchmark.db")
os.environ.setdefault("STORAGE_DIR", "./artifacts/benchmark-uploads")
os.environ["GENERATION_PROVIDER"] = "extractive"
os.environ["EMBEDDING_PROVIDER"] = "local"

from sqlalchemy import select
import psutil
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.embeddings import profile, runtime_stats, model
from app.models import User, Project, Document, Chunk
from app.worker import enqueue, run_once
from app.retrieval import answer
from benchmarks import baseline
from benchmarks.metrics import score, aggregate, canonical_bytes


def run(output: str, include_candidates: bool, thresholds: list[float], *, frozen_config=None, cases_override=None, dataset_kind=None):
    fixtures = json.loads((ROOT / "benchmarks/fixtures.json").read_text(encoding="utf-8"))
    candidates = json.loads((ROOT / "benchmarks/candidates.json").read_text(encoding="utf-8")) if include_candidates else []
    approved_path = ROOT / "benchmarks/approved.jsonl"
    approved = [json.loads(line) for line in approved_path.read_text(encoding="utf-8").splitlines() if line.strip()] if approved_path.exists() else []
    cases = fixtures + candidates + approved if cases_override is None else cases_override
    corpus = sorted((ROOT / "benchmarks/corpus").glob("*.md"))
    corpus_hash = hashlib.sha256(b"".join(p.name.encode() + canonical_bytes(p) for p in corpus)).hexdigest()
    if any(record.get("corpus_sha256") != corpus_hash for record in approved):
        raise ValueError("Human approvals refer to an older corpus. Review the changed sources and renew approvals before benchmarking them.")
    dataset_hash = hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()
    # Schema creation is limited to this explicitly configured benchmark database.
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    process = psutil.Process()
    report = {"schema_version": "1.0", "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "platform": platform.platform(), "python": platform.python_version(), "database": engine.dialect.name, "cpu_logical_count": os.cpu_count(), "corpus_sha256": corpus_hash, "dataset_sha256": dataset_hash, "source_count": len(corpus), "case_count": len(cases), "label_warning": "Fixture contracts are authored synthetic specifications; candidates are unverified proposed labels. Human-approved records are a separate split.", "latency_protocol": "Warm model, sequential queries, batch size configured in profile runtime. Bounded process embedding cache stays enabled across strategies. No paid generation.", "runs": []}
    report["source_hash_normalization"]="UTF-8 without BOM; LF line endings"
    report["source_sha256"]={str(path.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(canonical_bytes(path)).hexdigest() for path in [*sorted((ROOT/"backend/app").glob("*.py")),ROOT/"benchmarks/run.py",ROOT/"benchmarks/baseline.py",ROOT/"benchmarks/metrics.py",ROOT/"backend/requirements.lock.txt"]}
    report["dataset_kind"]=dataset_kind or "development_sweep"
    report["frozen_config"]=frozen_config
    report["status"]="completed" if cases else "not_run_no_cases"
    for provider in (("semantic",) if frozen_config else ("local", "semantic")) if cases else ():
        settings().embedding_provider = provider
        if frozen_config and profile()["id"]!=frozen_config["embedding_profile"]:raise ValueError("Frozen embedding profile mismatch")
        cold_start = time.perf_counter()
        if provider == "semantic":
            model()
        model_load_ms = (time.perf_counter()-cold_start)*1000
        with SessionLocal() as db:
            user = User(email=f"benchmark-{uuid.uuid4().hex}@example.com", password_hash="disabled-benchmark-account")
            db.add(user); db.flush()
            project = Project(owner_id=user.id, name="Benchmark " + provider)
            if frozen_config:project.pipeline={**(project.pipeline or {}),**frozen_config["pipeline"],"auto":False}
            db.add(project); db.commit()
            project_id, user_id = project.id, user.id
            paths = []
            indexing_start = time.perf_counter()
            cpu_start = sum(process.cpu_times()[:2])
            rss_samples = [process.memory_info().rss]
            try:
                settings().storage_dir.mkdir(parents=True, exist_ok=True)
                for path in corpus:
                    data = path.read_bytes()
                    storage_name = uuid.uuid4().hex + ".md"
                    target = settings().storage_dir / storage_name
                    target.write_bytes(data); paths.append(target)
                    doc = Document(project_id=project.id, name=path.name, kind="md", storage_name=storage_name, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))
                    db.add(doc);db.flush();enqueue(db, doc, project);db.commit()
                    assert run_once(project_id), "No benchmark job claimed"
                    db.expire_all();db.refresh(doc)
                    if doc.status != "ready":
                        raise RuntimeError(f"Benchmark ingestion failed for {path.name}: {doc.error}")
                    rss_samples.append(process.memory_info().rss)
                indexing_seconds = time.perf_counter()-indexing_start
                docs = list(db.scalars(select(Document).where(Document.project_id == project_id)))
                indexing = {"seconds": round(indexing_seconds,4), "documents_per_second": round(len(docs)/indexing_seconds,3), "characters_per_second": round(sum(d.metadata_json["characters"] for d in docs)/indexing_seconds,2), "chunks": sum(d.chunk_count for d in docs), "embedding_ms_sum": round(sum(d.metadata_json["embedding_ms"] for d in docs),2), "sampled_peak_rss_mb": round(max(rss_samples)/1024**2,2), "cpu_seconds": round(sum(process.cpu_times()[:2])-cpu_start,3), "model_load_ms_cached_files": round(model_load_ms,2)}
                for threshold in (thresholds if provider == "semantic" else [.12]):
                    for strategy in ((frozen_config["pipeline"]["strategy"],) if frozen_config else ("vector", "keyword", "hybrid")):
                        project.pipeline = {**project.pipeline, "strategy": strategy, "top_k": 5, "min_score": .12, "semantic_min_score": threshold}
                        db.commit()
                        ordered = list(cases);random.Random(42).shuffle(ordered)
                        rows = []
                        for case in ordered:
                            if provider == "local":
                                start = time.perf_counter()
                                retrieved = baseline.retrieve(db, project, case["question"])
                                retrieval_ms = (time.perf_counter()-start)*1000
                                text, citations, refused = baseline.generate(case["question"], retrieved)
                                result = {"answer": text, "citations": citations, "retrieved": retrieved, "refused": refused, "retrieval_latency_ms": round(retrieval_ms,2), "latency_ms": round((time.perf_counter()-start)*1000,2)}
                            else:
                                result = answer(db, project, case["question"], "benchmark", save=False)
                            rows.append({"id": case["id"], "question": case["question"], "split": case["split"], "status": case["status"], "category": case["category"], "metrics": score(case, result), "answer": result["answer"], "refused": result["refused"], "retrieved": [{"document": s["document_name"], "text": s["text"], "score": s["score"], "locator": s["locator"]} for s in result["retrieved"]], "citations": [{"document": c["document_name"], "quote": c["quote"]} for c in result["citations"]]})
                            rss_samples.append(process.memory_info().rss)
                        splits = {split: aggregate([row for row in rows if row["split"] == split]) for split in sorted({row["split"] for row in rows})}
                        categories = {category: aggregate([row for row in rows if row["category"] == category and row["split"] == "evaluation"]) for category in sorted({row["category"] for row in rows if row["split"] == "evaluation"})}
                        run = {"provider": "lexical-original-ad103d5" if provider == "local" else "semantic", "profile": profile(), "strategy": strategy, "semantic_threshold": threshold if provider == "semantic" else None, "fusion": "reciprocal rank fusion k=60; vector weight 2, keyword weight 1" if provider=="semantic" and strategy=="hybrid" else "original equal-weight RRF k=60" if strategy=="hybrid" else "single rank list", "chunk_words": project.pipeline["chunk_size"], "chunk_overlap_words": project.pipeline["overlap"], "indexing": indexing, "splits": splits, "evaluation_categories": categories, "sampled_peak_rss_mb": round(max(rss_samples)/1024**2,2), "runtime": runtime_stats() if provider == "semantic" else None, "cases": rows}
                        report["runs"].append(run)
                        print(json.dumps({"provider": run["provider"], "strategy": strategy, "threshold": threshold, "evaluation": splits.get("evaluation")}))
            finally:
                db.delete(db.get(User,user_id));db.commit()
                for path in paths:
                    path.unlink(missing_ok=True)
    target = Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print("Saved " + str(target))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="benchmarks/results/sqlite.json")
    parser.add_argument("--candidates", action="store_true")
    parser.add_argument("--thresholds", default="0.32")
    args = parser.parse_args()
    run(args.output, args.candidates, [float(x) for x in args.thresholds.split(",")])
