"""Read data-only configuration before importing the frozen engine."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "config/manifest.json").read_text(encoding="utf-8"))
if MANIFEST.get("schema_version") != "1.0" or MANIFEST.get("generator_version") != "1.2.0":
    raise RuntimeError("Unsupported standalone manifest/template version")
embedding = MANIFEST["embedding"]
for key, value in {
    "EMBEDDING_PROVIDER": embedding["provider"],
    "EMBEDDING_DIMENSIONS": embedding["dimensions"],
    "OPENAI_EMBEDDING_MODEL": embedding["model"] if embedding["provider"]=="openai" else "text-embedding-3-small",
    "GENERATION_PROVIDER": MANIFEST["generation"]["provider"],
    "OPENAI_MODEL": MANIFEST["generation"].get("model", "") if MANIFEST["generation"]["provider"]=="openai" else "",
    "DATABASE_URL": "sqlite:///./runtime/standalone.db",
    "STORAGE_DIR": "./runtime/uploads",
    "MODEL_CACHE_DIR": "./runtime/models",
}.items():
    os.environ.setdefault(key, str(value))

from .engine.config import settings
from .engine.embeddings import profile
from .engine.schemas import PipelineInput

PIPELINE = PipelineInput.model_validate(MANIFEST["pipeline"]).model_dump()
if settings().embedding_dimensions != 384:
    raise RuntimeError("Standalone schema v1 requires 384 dimensions; use a separate database and explicit schema migration for a different size")
if embedding["provider"] == "semantic" and embedding["id"] != profile()["id"] and settings().embedding_provider == "semantic":
    raise RuntimeError("Manifest semantic model identity differs from this pinned engine")

COLLECTION_ID = "standalone-collection"
