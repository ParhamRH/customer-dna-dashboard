# 0001 — Stack and repository layout

**Status:** Accepted

## Context

The platform must serve an agency (platform administrators) and many customers, each with
isolated brand libraries, ingest heavy media (video, PDFs, 3D), call AI models, and expose the
result to people (dashboard), programs (REST, webhooks) and AI clients (MCP). The brief named
Next.js + TypeScript + Tailwind + shadcn/ui, FastAPI + Pydantic, PostgreSQL + pgvector, S3/R2,
n8n, FFmpeg/PySceneDetect and Docling/PyMuPDF.

## Decision

One repository with three deployable parts:

| Path | Part | Notes |
|---|---|---|
| `backend/` | FastAPI API, worker, MCP server, CLI | One Python package (`app`), one Docker image, process chosen by command |
| `frontend/` | Next.js 16 dashboard | App Router, client components, TanStack Query, hand-written shadcn-style components on Radix |
| `deploy/`, `docker-compose.yml` | Postgres (pgvector), MinIO, Caddy, optional n8n | |

* Python 3.12+ with SQLAlchemy 2 (sync) and Alembic migrations; Pydantic v2 for every request
  body and for validating AI output.
* PostgreSQL is the system of record *and* the vector store (pgvector, HNSW) *and* the job
  queue (ADR 0005). No Redis, no separate vector database.
* Media: FFmpeg/ffprobe, PySceneDetect + OpenCV, Pillow, PyMuPDF (+ Tesseract OCR), trimesh for
  3D; Docling is an optional extra because it pulls PyTorch.

## Consequences

* Fewer moving parts: a working deployment is Postgres + object storage + one image.
* Synchronous SQLAlchemy keeps transactions and the per-transaction tenant context simple; the
  API runs in a thread pool. Long work never runs in a request — it is a job.
* shadcn components are written into the repository (the registry was not reachable while
  building) with `components.json` kept, so the CLI can still add components later.
