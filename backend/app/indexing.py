"""Compatibility gates apply to every retrieval mode, including keyword search."""
from fastapi import HTTPException
from sqlalchemy import select, text

from .embeddings import profile
from .models import Chunk, Document


def storage_dimensions(db) -> int | None:
    if db.bind.dialect.name != "postgresql":
        return None
    value = db.scalar(text("SELECT format_type(a.atttypid,a.atttypmod) FROM pg_attribute a WHERE a.attrelid='chunks'::regclass AND a.attname='embedding' AND NOT a.attisdropped"))
    return int(value.split("(")[1].split(")")[0]) if value and "(" in value else None


def index_status(db, project) -> dict:
    active = profile()
    models = list(db.scalars(select(Chunk.embedding_model).where(Chunk.project_id == project.id).distinct()))
    documents = list(db.scalars(select(Document).where(Document.project_id == project.id)))
    dimensions = storage_dimensions(db)
    wrong_dimensions = dimensions is not None and dimensions != active["dimensions"]
    mismatched = [identity for identity in models if identity != active["id"]]
    target_changed = bool(project.index_profile and project.index_profile.get("id") != active["id"])
    waiting = [d.id for d in documents if project.index_generation > 0 and d.metadata_json.get("index_generation", 0) != project.index_generation]
    incompatible = bool(mismatched or target_changed or wrong_dimensions)
    state = "incompatible" if incompatible else "rebuilding" if waiting else "ready" if models else "empty"
    return {"state": state, "compatible": not incompatible, "query_ready": not incompatible and not waiting, "active_profile": active, "indexed_profiles": models, "target_profile": project.index_profile, "index_generation": project.index_generation, "pending_document_ids": waiting, "storage_dimensions": dimensions, "dimension_mismatch": wrong_dimensions, "message": "The database vector dimension differs from the configured model. Use a separate database or an explicit vector-column migration; existing data has been preserved." if wrong_dimensions else "Embedding configuration changed. Rebuild the project index to resume queries. Existing source files are preserved." if incompatible else "Controlled index rebuild is incomplete. Wait for jobs or repair failed documents and retry." if waiting else "Index matches the active embedding configuration."}


def require_compatible(db, project, for_upload: bool = False):
    status = index_status(db, project)
    if not status["compatible"] or (not for_upload and not status["query_ready"]):
        raise HTTPException(409, {"code": "embedding_dimension_mismatch" if status["dimension_mismatch"] else "embedding_index_incompatible" if not status["compatible"] else "index_rebuilding", "message": status["message"], "index": status})
    return status
