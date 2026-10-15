# 0006 — Hybrid search fused with weighted reciprocal rank

**Status:** Accepted

## Context

Creative people search with mixed intent: "videos with slow cinematic camera movements",
"approved references with organic geometry", "guidelines relevant to website design". No single
technique answers all of these: keywords miss synonyms, embeddings miss exact constraints, and
measured properties (duration, camera movement, palette) are facts, not text.

## Decision

`app/search` parses the query (asset types, "approved only", attributes such as camera
movement or lighting, project types, named concepts and principles), then runs up to five
signals over the workspace — always inside the tenant session:

| Signal | Source |
|---|---|
| keyword | PostgreSQL full-text (`tsvector`, `ts_rank_cd`) + trigram similarity on names and tags |
| semantic | pgvector HNSW over text embeddings of assets, segments (scenes, pages) and knowledge |
| relationship | entities linked to concepts/principles named in the query (approved edges only) |
| metadata | measured media properties (duration, camera movement, palette, lighting …) |
| visual | image embeddings (search by image, "similar") |

Each signal's list is normalized as half reciprocal rank (k = 60) and half relative score, then
fused with weights (keyword 1.0, semantic 1.25, relationship 1.1, metadata 0.7, visual 1.25).
Results carry their knowledge status (official / pending / inspiration / historical) and the
matching segments (e.g. "scene at 7 s", "page 3"). "Explain ranking" exposes per-signal ranks.

## Consequences

* Robust across heterogeneous scorers; easy to add a signal.
* Results are approval-aware: scope filters (official only / pending only) apply after fusion,
  and unreviewed AI interpretations never masquerade as official descriptions.
* Ranking is heuristic and needs evaluation data per customer to tune weights.
