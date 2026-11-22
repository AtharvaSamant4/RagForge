import math
import statistics
import hashlib


def canonical_bytes(path):
    return path.read_bytes().replace(b"\r\n",b"\n").removeprefix(b"\xef\xbb\xbf")


def percentile(values, percent):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percent * len(ordered))-1)] if ordered else None


def score(case, result):
    references = case["source_refs"]
    retrieved = result["retrieved"]
    def matches(source, ref):
        return source["document_name"] == ref["document"] and ref["quote"] in source["text"]
    relevant = [any(matches(source, ref) for ref in references) for source in retrieved]
    matched = sum(any(matches(source, ref) for source in retrieved) for ref in references)
    citations = result["citations"]
    actual = {(s["chunk_id"], s["document_id"]): s for s in retrieved}
    citation_checks = [bool((s := actual.get((c["chunk_id"],c["document_id"]))) and c.get("quote") and c["quote"] in s["text"]) for c in citations]
    rank = next((i+1 for i, value in enumerate(relevant) if value), None)
    return {"hit_at_1": float(any(relevant[:1])) if references else None, "hit_at_3": float(any(relevant[:3])) if references else None, "hit_at_5": float(any(relevant[:5])) if references else None, "recall_at_5": matched/len(references) if references else None, "mrr": 1/rank if rank else 0.0 if references else None, "citation_validity": statistics.mean(citation_checks) if citation_checks else None, "expected_quote_coverage": sum(any(q in c.get("quote", "") for c in citations) for q in case.get("expected_quotes", []))/len(references) if references else None, "refusal_correct": float(result["refused"] == case["expect_refusal"]), "retrieval_latency_ms": result["retrieval_latency_ms"], "end_to_end_latency_ms": result["latency_ms"]}


def aggregate(rows):
    metrics = {}
    for key in ("hit_at_1","hit_at_3","hit_at_5","recall_at_5","mrr","citation_validity","expected_quote_coverage","refusal_correct","retrieval_latency_ms","end_to_end_latency_ms"):
        values = [row["metrics"][key] for row in rows if row["metrics"][key] is not None]
        metrics[key] = round(statistics.mean(values), 5) if values else None
    for field in ("retrieval_latency_ms", "end_to_end_latency_ms"):
        metrics[field+"_p95"] = percentile([row["metrics"][field] for row in rows], .95)
    return {"count": len(rows), "metrics": metrics}
