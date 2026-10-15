# 0005 — Background work on a PostgreSQL job queue

**Status:** Accepted

## Context

Ingestion (media processing, AI analysis, embeddings), exports, imports, re-indexing, webhook
delivery and purges must run outside requests, survive restarts, retry with back-off and be
visible per workspace.

## Decision

* Jobs are rows in `processing_jobs` (tenant-scoped, RLS like everything else). Workers claim
  with `FOR UPDATE SKIP LOCKED` through the system role, then run the job body in a tenant
  session for the job's organization.
* Retries with exponential back-off (15 s doubling, capped at 1 h); `dead` after
  `max_attempts`. Permanent errors skip retries. Stale locks are released after
  `BDNA_JOB_LOCK_TIMEOUT_SECONDS`.
* Jobs are enqueued **in the same transaction** as the change that needs them (an upload and
  its `asset.ingest` job commit together), so there is no lost or orphaned work.
* Each job records steps, progress and a result. Workspace users see the first line of an error
  only; stack traces stay in the database and logs for operators.
* A janitor in the worker expires exports and cleans import staging.

## Consequences

* No broker to run or secure; transactional enqueue for free.
* Throughput is bounded by Postgres; at the scale of brand libraries (thousands of assets per
  customer) this is ample. Scale out by running more worker containers.
