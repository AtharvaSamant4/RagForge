# Semantic model and index compatibility

The local semantic adapter uses `sentence-transformers/all-MiniLM-L6-v2`, exported as ONNX in `Qdrant/all-MiniLM-L6-v2-onnx`, revision `d13954661f83248295ba75c1ed411eef3b7b936e`. Both [the upstream model](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) and [the ONNX port](https://huggingface.co/Qdrant/all-MiniLM-L6-v2-onnx) declare Apache-2.0. Upstream documents a 384-dimensional output, mean pooling with attention masks, L2 normalization and a 256-wordpiece input limit. The implementation uses the [ONNX Runtime CPU provider](https://onnxruntime.ai/docs/api/python/api_summary.html), not remote inference or downloaded Python code. Windows/Python 3.12 and Linux/Python 3.12 execution were verified with the pinned dependency lock.

The 90,387,630-byte model file must match SHA-256 `bbd7b466f6d58e646fdc2bd5fd67b2f5e93c0b687011bd4548c420f7bd46f0c5`; the tokenizer must match `851ca67100d372ca3ae031a6abd168f53489eebfd7d89523f35c5c9b4d372c3c`. Downloads publish atomically under a cross-process file lock. Both files are verified before model initialization. Cached initialization was executed with `MODEL_LOCAL_FILES_ONLY=true`; missing/corrupt files fail explicitly. The selected dependencies and their exact versions are in `backend/requirements.lock.txt`.

| Setting | Default | Effect |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `semantic` | CPU MiniLM; `local` retains original lexical hashing; `openai` is explicitly configured hosted embeddings |
| `EMBEDDING_DIMENSIONS` | `384` | MiniLM requires 384; PostgreSQL storage must match |
| `MODEL_CACHE_DIR` | `data/models` | Persistent model files; Compose uses shared `/app/data/models` volume |
| `MODEL_LOCAL_FILES_ONLY` | `false` | When true, never download missing model files |
| `EMBEDDING_THREADS` | `2` | ONNX intra-operation CPU threads; one inter-operation thread |
| `EMBEDDING_BATCH_SIZE` | `32` | Batched inference, internally bounded to 1–128 |
| `EMBEDDING_CACHE_SIZE` | `2048` | Maximum process-memory cached vectors; content hashes as keys; no disk query cache |

One model/session is reused per process. API and worker are separate processes, so each has its own resident session. A lock prevents duplicate initialization/computation inside a process; batching deduplicates identical text before inference. Cache keys include model identity and text SHA-256. Cached vectors never bypass project-scoped database retrieval or authorization. Model/cache statistics expose only counts/timings, not text or vectors.

Semantic chunks respect both the configured word window and the tokenizer's 256-token budget. Long identifiers can consume several wordpieces, so word count alone is insufficient. Chunks retain exact extracted-text offsets and page/row/section metadata. Extraction never executes document instructions. PDF soft wraps remain inside quoted sentences rather than becoming partial answers.

## Safe transitions

The profile fingerprint includes provider, model repository/revision, weights/tokenizer checksums, dimensions, pooling, normalization, token budget and adapter version. Jobs capture that profile and the project's index generation. Chunk records carry the identity; document metadata carries the full profile, generation, embedding time and indexing time.

Migration `0002` adds nullable project profile and generation columns without deleting existing rows, vectors, keys or files. Legacy lexical IDs remain recognized as `local:hash-v1:384`. A migration test seeds a real revision-0001 database and verifies preserved source bytes and rows after upgrade.

1. Change provider configuration and restart API **and** worker.
2. Inspect **Pipeline**. A mismatched model, mixed index, changed target profile or unfinished controlled generation blocks all queries with a descriptive HTTP 409.
3. Click **Rebuild index**. The project is locked while matching work is deduplicated and superseded leases are canceled. Every source is re-enqueued with the new profile/generation.
4. Each document's chunks publish transactionally only if the lease, profile and generation still match. Old source files remain intact. Queries stay blocked during a mixed/unfinished generation.
5. Wait for readiness. Repair and retry failed jobs, or remove an invalid source. Retrying cannot silently reinterpret an older provider job.

Tests cover two documents straddling an incomplete model transition, every retrieval mode, a model change after enqueue, a superseded running generation, concurrent workers, deletion during processing, fixed PostgreSQL dimensions, missing caches and real-model cache reuse. Switching to a different PostgreSQL dimension requires a separate database or explicit operator migration; automatic destructive conversion is intentionally absent.

## Retrieval and grounding decisions

Vector, keyword and hybrid retrieval remain available. PostgreSQL keyword matching combines individual terms with OR before full-text ranking; the prior AND query missed many paraphrases. SQLite retains lexical overlap ranking. Hybrid uses reciprocal rank fusion (`k=60`), weighting semantic vector ranks 2 and keyword ranks 1. Weak semantic candidates are gated before fusion. The explicit default semantic gate is 0.32; this is a measured fixture choice, not a calibrated confidence probability or universally optimal threshold.

The primary PostgreSQL fixtures favored hybrid; SQLite fixtures favored vector search. First-upload automatic defaults reflect those observed backend-specific results. Existing project choices are preserved. See BENCHMARKS.md for the actual numbers, exploratory threshold run and limitations. No reranker, agentic planner or expensive second model was added.

Answers select exact source excerpts. Numeric time/eligibility questions receive qualified evidence rather than unsupported decisions. A narrow normalized-sentence numeric-conflict detector declines to choose between conflicting values. High similarity can still indicate only a related topic. Hosted generation also rejects nonverbatim claims even when a genuine quote is attached; a real quote alone does not validate a paraphrase. General semantic entailment and arbitrary contradictions remain unassessed.
