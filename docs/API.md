# Developer API

Interactive OpenAPI: http://localhost:8000/docs or dashboard `/api/docs`. All private project endpoints require a session owned by the project owner or an appropriate Bearer key. Foreign projects and resources return 404. Invalid keys return 401; insufficient scopes return 403; limits return 429. Uploaded files are multipart `file`; upload requests must include Content-Length (standard clients do).

Key scopes: `query` permits queries, `read` permits project/document/job/status/pipeline/usage inspection, `documents` permits uploads/deletes/retries. Project rename/delete, pipeline updates, reindex, keys, evaluation, manifest, widget settings and dashboard history require an owner session. API key conversations cannot access owner conversations. Each question is retrieved independently; conversation history persists for display, not model memory.

Create a key in **API & Integration**. It is only shown at creation. Store it in `RAGFORGE_API_KEY` on your application server.

```sh
curl http://localhost:8000/v1/projects/PROJECT_ID/query \
  -H "Authorization: Bearer $RAGFORGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the refund period?"}'
```

```python
# pip install httpx
import os
import httpx

response = httpx.post(
    "http://localhost:8000/v1/projects/PROJECT_ID/query",
    headers={"Authorization": "Bearer " + os.environ["RAGFORGE_API_KEY"]},
    json={"question": "What is the refund period?"},
    timeout=120,
)
response.raise_for_status()
print(response.json())
```

```js
// Node.js 24+, server side
const response = await fetch('http://localhost:8000/v1/projects/PROJECT_ID/query', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${process.env.RAGFORGE_API_KEY}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ question: 'What is the refund period?' })
});
if (!response.ok) throw new Error(await response.text());
console.log(await response.json());
```

The response includes `answer`, `refused`, `latency_ms`, `conversation_id`, `citations` and `retrieved`. Each source includes `document_id`, `document_name`, `chunk_id`, locator (`page`, `row`, paragraph, or section plus character offsets), source text and evidence score. Citations add a number and an exact quote. Evidence scores are retrieval signals, not probabilities or confidence percentages.

Milestone 2 adds `retrieval_latency_ms`, `generation_latency_ms`, `embedding_model` and `answer_kind` (`source_extract`, `qualified`, or `refused`). A qualified answer can include citations while `refused=true`, because evidence exists but individual eligibility or conflicting policy details remain unresolved. Empty evidence refusals have no citations.

`GET /pipeline` and `/status` expose the active embedding profile, indexed identities, index generation and compatibility state. Incompatible or incomplete controlled indexes return HTTP 409 before any retrieval mode executes. Owner-only `POST /retrieval/compare` accepts `{ "question": "..." }` and returns real passages and retrieval latency for vector, keyword and hybrid strategies without generation or conversation writes. `POST /reindex` captures a new model/generation, cancels superseded leases and preserves source files. See SEMANTIC_MODELS.md for migration and recovery details.

`POST /query/stream` accepts the same JSON and emits SSE `sources`, `delta` and `done` events. Generation and quote validation finish before answer deltas are emitted; this is response delivery streaming, not provider token streaming. Failures before streaming return normal error JSON.

```sh
curl http://localhost:8000/v1/projects/PROJECT_ID/status -H "Authorization: Bearer $RAGFORGE_API_KEY"
curl http://localhost:8000/v1/projects/PROJECT_ID/jobs -H "Authorization: Bearer $RAGFORGE_API_KEY"
curl http://localhost:8000/v1/projects/PROJECT_ID/usage -H "Authorization: Bearer $RAGFORGE_API_KEY"
curl http://localhost:8000/v1/projects/PROJECT_ID/documents -H "Authorization: Bearer $RAGFORGE_API_KEY" -F file=@samples/acme-handbook.pdf
```

The repository's `scripts/smoke.py` executes the full flow over real HTTP with an actual worker. Credentials are randomly generated and not printed. Smoke accounts remain in the local database; smoke projects and uploaded files are removed.
