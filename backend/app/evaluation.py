import statistics
import time

from sqlalchemy import select

from .models import Chunk, EvalCase, EvalRun
from .providers import lexical_score, terms
from .retrieval import answer
from .embeddings import profile


def generate_cases(db, project):
    chunks = db.scalars(select(Chunk).where(Chunk.project_id == project.id).order_by(Chunk.document_id, Chunk.ordinal).limit(5)).all()
    created = []
    for chunk in chunks:
        keywords = " ".join(list(dict.fromkeys(terms(chunk.text)))[:7])
        case = EvalCase(project_id=project.id, question=f"What do the documents say about {keywords}?", relevant_document_ids=[chunk.document_id], expected_answer=chunk.text[:400], verified=False, origin="synthetic")
        db.add(case)
        created.append(case)
    db.commit()
    return created


def run_evaluation(db, project, include_unverified: bool):
    cases = list(db.scalars(select(EvalCase).where(EvalCase.project_id == project.id).order_by(EvalCase.id).limit(50)))
    cases = [c for c in cases if c.verified or include_unverified]
    rows = []
    for case in cases:
        result = answer(db, project, case.question, "evaluation", save=False)
        relevant = set(case.relevant_document_ids)
        retrieved = {s["document_id"] for s in result["retrieved"]}
        ranked = [item["document_id"] for item in result["retrieved"]]
        first_relevant = next((i+1 for i,value in enumerate(ranked) if value in relevant), None)
        citations = result["citations"]
        valid = [bool(c["quote"] and c["quote"] in c["text"]) for c in citations]
        rows.append({"case_id": case.id, "question": case.question, "verified": case.verified, "origin": case.origin, "answer": result["answer"], "refused": result["refused"], "recall_at_k": len(relevant & retrieved) / len(relevant) if relevant else None, "hit_at_k": bool(relevant & retrieved) if relevant else None, "lexical_relevance": statistics.mean([lexical_score(case.question, s["text"]) for s in result["retrieved"]]) if result["retrieved"] else 0, "citation_validity": sum(valid) / len(valid) if valid else None, "exact_quote_support": sum(valid) / len(valid) if valid else None, "expected_answer_token_recall": lexical_score(case.expected_answer, result["answer"]) if case.expected_answer else None, "refusal_correct": result["refused"] == case.expect_refusal, "latency_ms": result["latency_ms"], "retrieval_latency_ms": result["retrieval_latency_ms"], "hit_at_1": bool(relevant & set(ranked[:1])) if relevant else None, "hit_at_3": bool(relevant & set(ranked[:3])) if relevant else None, "hit_at_5": bool(relevant & set(ranked[:5])) if relevant else None, "mrr": (1/first_relevant if first_relevant else 0) if relevant else None, "retrieved_document_ids": sorted(retrieved)})
    def mean(field):
        values = [row[field] for row in rows if row[field] is not None]
        return round(statistics.mean(values), 4) if values else None
    latency = sorted(row["latency_ms"] for row in rows)
    result = {"case_count": len(rows), "verified_count": sum(row["verified"] for row in rows), "synthetic_count": sum(row["origin"] == "synthetic" for row in rows), "top_k": project.pipeline["top_k"], "pipeline": project.pipeline, "pipeline_version": project.pipeline_version, "embedding_profile": profile(), "metrics": {field: mean(field) for field in ("recall_at_k", "hit_at_k", "lexical_relevance", "citation_validity", "exact_quote_support", "expected_answer_token_recall", "refusal_correct", "latency_ms", "retrieval_latency_ms", "hit_at_1", "hit_at_3", "hit_at_5", "mrr")}, "p95_latency_ms": latency[min(len(latency)-1, int(len(latency)*0.95))] if latency else None, "semantic_faithfulness": "not assessed", "notes": "Exact quote support verifies provenance, not semantic entailment. Synthetic cases are unverified and are not ground truth.", "cases": rows}
    run = EvalRun(project_id=project.id, result=result)
    db.add(run)
    db.commit()
    return run
