"""Versioned schema initialization and idempotent knowledge-snapshot import."""
import hashlib
import os
import shutil
import uuid

from sqlalchemy import select, text
from .bootstrap import MANIFEST, PIPELINE, ROOT, COLLECTION_ID
from .engine.db import Base, engine, SessionLocal
from .engine.models import User, Project, Document
from .engine.config import settings
from .engine.ingestion import validate_file
from .engine.worker import enqueue


def initialize():
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(6743321)"))
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS standalone_schema (version INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE IF NOT EXISTS standalone_removed_sources (sha256 VARCHAR(64) PRIMARY KEY)"))
        versions = connection.execute(text("SELECT version FROM standalone_schema")).scalars().all()
        if versions and versions != [1]:
            raise RuntimeError("Unsupported standalone schema; apply a reviewed migration before startup")
        Base.metadata.create_all(connection)
        if engine.dialect.name == "postgresql":
            connection.execute(text("CREATE INDEX IF NOT EXISTS standalone_chunks_vector ON chunks USING hnsw (embedding vector_cosine_ops)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS standalone_chunks_fts ON chunks USING gin (to_tsvector('english', text))"))
        if not versions:
            connection.execute(text("INSERT INTO standalone_schema VALUES (1)"))
    settings().storage_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        if not db.get(User, "standalone-owner"):
            db.add(User(id="standalone-owner", email="disabled@standalone.invalid", password_hash="!"))
            db.flush()
        project = db.get(Project, COLLECTION_ID)
        if not project:
            project = Project(id=COLLECTION_ID, owner_id="standalone-owner", name=MANIFEST["name"], pipeline=PIPELINE, index_profile=MANIFEST["embedding"])
            db.add(project); db.flush()
        # Serial startup, even when an operator accidentally starts two API replicas.
        project = db.scalar(select(Project).where(Project.id == COLLECTION_ID).with_for_update())
        for source in MANIFEST["sources"]:
            if db.scalar(text("SELECT sha256 FROM standalone_removed_sources WHERE sha256=:sha"),{"sha":source["sha256"]}):
                continue
            if db.scalar(select(Document.id).where(Document.project_id == COLLECTION_ID, Document.sha256 == source["sha256"])):
                continue
            path = ROOT / source["path"]
            if path.is_symlink() or not path.resolve().is_relative_to((ROOT/"data/knowledge").resolve()):
                raise RuntimeError("Unsafe knowledge path")
            content = path.read_bytes()
            if len(content) != source["size_bytes"] or hashlib.sha256(content).hexdigest() != source["sha256"]:
                raise RuntimeError("Knowledge snapshot checksum mismatch")
            name, kind = validate_file(source["name"], content)
            storage_name = uuid.uuid4().hex + "." + kind
            target = settings().storage_dir / storage_name
            temporary = target.with_suffix(".part")
            with temporary.open("xb") as out:
                out.write(content)
            os.replace(temporary, target)
            doc = Document(project_id=COLLECTION_ID, name=name, kind=kind, storage_name=storage_name, sha256=source["sha256"], size_bytes=len(content))
            db.add(doc); db.flush(); enqueue(db, doc, project)
        db.commit()


if __name__ == "__main__":
    initialize()
