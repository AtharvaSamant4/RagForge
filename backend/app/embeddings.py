"""Pinned CPU MiniLM inference. No remote code, torch, or paid inference service."""
import hashlib
import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

import httpx
from filelock import FileLock

from .config import settings

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REPOSITORY = "Qdrant/all-MiniLM-L6-v2-onnx"
REVISION = "d13954661f83248295ba75c1ed411eef3b7b936e"
FILES = {
    "model.onnx": "bbd7b466f6d58e646fdc2bd5fd67b2f5e93c0b687011bd4548c420f7bd46f0c5",
    "tokenizer.json": "851ca67100d372ca3ae031a6abd168f53489eebfd7d89523f35c5c9b4d372c3c",
}
_lock = threading.RLock()
_instance = None
_instance_key = None
_cache: OrderedDict[str, list[float]] = OrderedDict()
_stats = {"loads": 0, "cache_hits": 0, "computed_texts": 0, "embedding_ms": 0.0, "load_ms": 0.0}


class EmbeddingError(RuntimeError):
    pass


def profile() -> dict:
    s = settings()
    if s.embedding_provider == "local":
        return {"id": f"local:hash-v1:{s.embedding_dimensions}", "provider": "local", "model": "lexical feature hashing", "dimensions": s.embedding_dimensions, "implementation": "hash-v1", "normalization": "l2", "semantic": False}
    if s.embedding_provider == "openai":
        return {"id": f"openai:{s.openai_embedding_model}:{s.embedding_dimensions}", "provider": "openai", "model": s.openai_embedding_model, "dimensions": s.embedding_dimensions, "semantic": True, "revision": "provider-managed"}
    if s.embedding_dimensions != 384:
        raise EmbeddingError("MiniLM requires EMBEDDING_DIMENSIONS=384. Restore that setting before indexing.")
    data = {"provider": "semantic", "model": MODEL, "repository": REPOSITORY, "revision": REVISION, "files": FILES, "dimensions": 384, "max_tokens": 256, "pooling": "attention-mask-mean", "normalization": "l2", "implementation": "minilm-onnx-v1", "semantic": True, "license": "Apache-2.0"}
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return {**data, "id": "semantic:minilm-onnx-v1:" + fingerprint[:32]}


def checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def model_files() -> Path:
    directory = settings().model_cache_dir / "minilm" / REVISION
    directory.mkdir(parents=True, exist_ok=True)
    # Shared across API/worker containers through a named volume. Atomic publication.
    with FileLock(str(directory / ".download.lock"), timeout=1200):
        for name, expected in FILES.items():
            target = directory / name
            if target.is_file() and checksum(target) == expected:
                continue
            if settings().model_local_files_only:
                raise EmbeddingError("Pinned MiniLM files are missing or corrupt. Run python -m app.model_cache online, then restart with MODEL_LOCAL_FILES_ONLY=true.")
            temporary = directory / (name + "." + uuid.uuid4().hex + ".part")
            try:
                with httpx.stream("GET", f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}", follow_redirects=True, timeout=httpx.Timeout(120, connect=15)) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as out:
                        for chunk in response.iter_bytes(1024 * 1024):
                            out.write(chunk)
                if checksum(temporary) != expected:
                    raise EmbeddingError("Pinned model checksum validation failed. No model was loaded.")
                os.replace(temporary, target)
            except httpx.HTTPError:
                raise EmbeddingError("Could not download the pinned MiniLM model. Check connectivity or prefill MODEL_CACHE_DIR. No lexical fallback was used.") from None
            finally:
                temporary.unlink(missing_ok=True)
    return directory


def model():
    global _instance, _instance_key
    s = settings()
    key = (str(s.model_cache_dir.resolve()), max(1, s.embedding_threads), profile()["id"])
    with _lock:
        if _instance is not None and _instance_key == key:
            return _instance
        start = time.perf_counter()
        try:
            import numpy as np
            import onnxruntime as ort
            ort.disable_telemetry_events()  # Vendor diagnostics are not pilot consent.
            from tokenizers import Tokenizer
            directory = model_files()
            tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
            tokenizer.enable_truncation(max_length=256)
            tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
            counter = Tokenizer.from_file(str(directory / "tokenizer.json"))
            counter.no_truncation()
            counter.no_padding()
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, s.embedding_threads)
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            session = ort.InferenceSession(str(directory / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
            _instance = (session, tokenizer, counter, np)
            _instance_key = key
            _cache.clear()
            _stats["loads"] += 1
            _stats["load_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return _instance
        except EmbeddingError:
            raise
        except Exception:
            raise EmbeddingError("MiniLM CPU initialization failed. Install the pinned dependencies and verify the model cache. No fallback was used.") from None


def semantic_embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    with _lock:
        session, tokenizer, _, np = model()
        start = time.perf_counter()
        identity = profile()["id"]
        keys = [hashlib.sha256((identity + "\0" + text).encode()).hexdigest() for text in texts]
        missing = dict((key, text) for key, text in zip(keys, texts) if key not in _cache)
        found = {key: _cache[key] for key in keys if key in _cache}
        _stats["cache_hits"] += len(texts) - len(missing)
        items = list(missing.items())
        batch_size = max(1, min(settings().embedding_batch_size, 128))
        input_names = {x.name for x in session.get_inputs()}
        for offset in range(0, len(items), batch_size):
            batch = items[offset:offset + batch_size]
            encoded = tokenizer.encode_batch([text for _, text in batch])
            arrays = {"input_ids": np.asarray([e.ids for e in encoded], dtype=np.int64), "attention_mask": np.asarray([e.attention_mask for e in encoded], dtype=np.int64), "token_type_ids": np.asarray([e.type_ids for e in encoded], dtype=np.int64)}
            output = session.run(None, {k: v for k, v in arrays.items() if k in input_names})[0]
            if output.ndim == 3:
                mask = arrays["attention_mask"][..., None]
                output = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
            output = output / np.maximum(np.linalg.norm(output, axis=1, keepdims=True), 1e-9)
            if output.shape != (len(batch), 384) or not np.isfinite(output).all():
                raise EmbeddingError("MiniLM returned invalid vectors")
            for (key, _), vector in zip(batch, output.tolist(), strict=True):
                found[key] = vector
                _cache[key] = vector
            _stats["computed_texts"] += len(batch)
        while len(_cache) > max(0, settings().embedding_cache_size):
            _cache.popitem(last=False)
        for key in keys:
            if key in _cache:
                _cache.move_to_end(key)
        _stats["embedding_ms"] += (time.perf_counter() - start) * 1000
        return [list(found[key]) for key in keys]


def token_count(text: str) -> int:
    with _lock:
        return len(model()[2].encode(text).ids)


def runtime_stats() -> dict:
    return {**_stats, "cached_vectors": len(_cache), "loaded": _instance is not None, "threads": settings().embedding_threads, "batch_size": settings().embedding_batch_size, "cache_capacity": settings().embedding_cache_size}
