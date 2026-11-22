import time

from fastapi import HTTPException
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, func, select

from .config import settings
from .models import Chunk, Conversation, Document, QueryRecord
from .providers import embed, embedding_id, generate, lexical_score, terms
from .indexing import require_compatible


def retrieve(db, project, question: str, strategy: str | None = None, top_k: int | None = None) -> list[dict]:
    require_compatible(db, project)
    config = {**project.pipeline, **({"strategy": strategy} if strategy else {}), **({"top_k": top_k} if top_k else {})}
    base = select(Chunk, Document.name).join(Document, Chunk.document_id == Document.id).where(Chunk.project_id == project.id, Document.status == "ready")
    vector = embed([question])[0] if config["strategy"] != "keyword" else None
    limit = config["top_k"] * 5
    if db.bind.dialect.name == "postgresql":
        distance = cast(Chunk.embedding, Vector(settings().embedding_dimensions)).cosine_distance(vector) if vector else None
        vector_rows = list(db.execute(base.where(Chunk.embedding_model == embedding_id()).order_by(distance).limit(limit))) if vector else []
        ts = func.to_tsvector("english", Chunk.text)
        tokens = list(dict.fromkeys(terms(question)))[:24]
        query = func.plainto_tsquery("english", tokens[0] if tokens else "")
        for token in tokens[1:]:
            query = query.op("||")(func.plainto_tsquery("english", token))
        keyword_rows = list(db.execute(base.where(ts.op("@@")(query)).order_by(func.ts_rank_cd(ts, query).desc()).limit(limit))) if config["strategy"] != "vector" else []
    else:
        # Local mode intentionally uses an exact scan. Bound collection size at upload.
        rows = list(db.execute(base))
        vector_rows = sorted([r for r in rows if r[0].embedding_model == embedding_id()], key=lambda r: sum(a*b for a, b in zip(vector, r[0].embedding)), reverse=True)[:limit] if vector else []
        keyword_rows = sorted([r for r in rows if lexical_score(question, r[0].text) > 0], key=lambda r: lexical_score(question, r[0].text), reverse=True)[:limit] if config["strategy"] != "vector" else []
    fused, by_id = {}, {}
    lists = [vector_rows] if config["strategy"] == "vector" else [keyword_rows] if config["strategy"] == "keyword" else [vector_rows, keyword_rows]
    semantic = settings().embedding_provider != "local"
    # Gate each ranked list before fusion; low-quality vector tails cannot gain rank by fusion.
    if semantic and vector is not None:
        threshold = config.get("semantic_min_score", 0.32)
        lists = [[row for row in ranked if sum(a*b for a,b in zip(vector, row[0].embedding)) >= threshold] for ranked in lists]
    for list_index, ranked in enumerate(lists):
        weight = 2.0 if semantic and config["strategy"] == "hybrid" and list_index == 0 else 1.0
        for rank, row in enumerate(ranked):
            chunk = row[0]
            by_id[chunk.id] = row
            fused[chunk.id] = fused.get(chunk.id, 0) + weight / (60 + rank + 1)
    result = []
    for id_ in sorted(fused, key=fused.get, reverse=True):
        chunk, name = by_id[id_]
        lex = lexical_score(question, chunk.text)
        similarity = sum(a*b for a, b in zip(vector, chunk.embedding)) if vector is not None else lex
        # Local hash collisions cannot pass the evidence gate without lexical support.
        evidence = similarity if semantic and vector is not None else lex
        if evidence < (config.get("semantic_min_score", 0.32) if semantic and vector is not None else config["min_score"]):
            continue
        result.append({"chunk_id": chunk.id, "document_id": chunk.document_id, "document_name": name, "text": chunk.text, "locator": chunk.locator, "score": round(evidence, 4), "vector_similarity": round(similarity, 4), "rank_score": round(fused[id_], 6)})
        if len(result) == config["top_k"]:
            break
    return result


def answer(db, project, question: str, principal: str, conversation_id: str | None = None, save: bool = True, public: bool = False) -> dict:
    start = time.perf_counter()
    conversation = None
    if conversation_id:
        conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.project_id == project.id, Conversation.principal == principal))
        if not conversation or public:
            raise HTTPException(404, "Conversation not found")
    sources = retrieve(db, project, question)
    retrieval_ms = round((time.perf_counter() - start)*1000, 2)
    text, citations, refused = generate(question, sources)
    latency = round((time.perf_counter() - start) * 1000, 2)
    if save and not public and not conversation:
        conversation = Conversation(project_id=project.id, principal=principal, title=question[:100])
        db.add(conversation)
        db.flush()
    result = {"answer": text, "citations": citations, "retrieved": sources, "refused": refused, "latency_ms": latency, "retrieval_latency_ms": retrieval_ms, "generation_latency_ms": round(latency-retrieval_ms, 2), "conversation_id": conversation.id if conversation else None, "generation_provider": settings().generation_provider, "embedding_provider": settings().embedding_provider, "embedding_model": embedding_id(), "answer_kind": "qualified" if refused and citations else "refused" if refused else "source_extract"}
    if save:
        if not public:
            from .pilot import emit_batch
            operation = str(__import__('uuid').uuid4())
            events = [('query_completed', operation, latency)]
            if citations and not refused:
                events.append(('first_cited_answer', 'first', None))
            if principal.startswith('key:'):
                events.append(('external_api_query', operation, None))
            emit_batch(db, project.owner_id, events)
        db.add(QueryRecord(project_id=project.id, conversation_id=result["conversation_id"], question=question if not public else "[public widget query]", result=result if not public else {"refused": refused}, latency_ms=latency, refused=refused))
        db.commit()
    return result
