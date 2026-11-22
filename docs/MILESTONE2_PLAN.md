# Milestone 2 implementation and evidence plan

Branch: `feat/semantic-benchmarks-qa`. Preserve main, existing database volumes and uploaded files. Verification uses the independent Compose project `ragforge-m2` on ports 3010/8010.

1. Pin the Apache-2.0 MiniLM ONNX model, tokenizer, revision and checksums; execute CPU inference, verify 384 dimensions and paraphrase similarity. Keep lexical hashing and hosted adapters.
2. Persist embedding profiles and index generations. Reject incompatible indexes before retrieval; capture profiles in durable jobs and rebuild through a controlled generation transition. Preserve old source files and index data until replacement succeeds.
3. Add token-budget-aware chunks, semantic evidence gates and benchmark-tested rank fusion. Keep exact-source citations and conservative answer boundaries.
4. Create a versioned synthetic corpus, a deterministic fixture-contract set, at least 100 unverified review candidates, review CLI and reproducible lexical/semantic benchmark runner. Report retrieval, grounding, refusals, latency, indexing throughput and measurable resources. Separate calibration, fixtures, candidates and human approvals.
5. Expose model compatibility, timing and strategy comparison without complicating basic uploads/chat.
6. Execute the existing and new backend tests, real-model tests, SQLite and Docker PostgreSQL tests, smoke tests, frontend typecheck/build, and Playwright desktop/mobile workflows. Inspect screenshots and fix observed issues. Record exact commands/results, limitations and the five return-policy outcomes in BENCHMARKS.md and browser QA documentation.
7. Audit the mission requirements, commit and push only this feature branch. Do not merge or publicly deploy. No paid AI calls.

Evidence is actual command output and generated JSON reports, not expected results. Fixture contracts describe deliberately authored synthetic sources, not independently human-verified real-world truth. Human review is a separate explicit workflow.
