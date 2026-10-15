# Operations

Deploying, configuring, upgrading, backing up and looking after an installation.

## Deploy with Docker Compose

Requirements: Docker Engine with Compose v2.24+, 4 GB RAM (more for large video), disk for
PostgreSQL and object storage.

```bash
cp .env.example .env
# Replace every CHANGE-ME (see the comments in the file for generators). Passwords must be
# URL-safe (letters, digits, - and _) because they are embedded in database URLs.
docker compose up -d --build
docker compose run --rm api python -m app.cli create-admin --email you@agency.example --name "Your Name"
```

Open `http://localhost:8080` (or your domain), sign in, and create the first customer from
**Customers → New customer** — that creates the workspace, its first brand and its customer
administrator.

What starts:

| Service | Purpose | Notes |
|---|---|---|
| `postgres` | PostgreSQL 17 + pgvector | First start runs `deploy/postgres/init-roles.sh` (roles, database, extensions) |
| `minio` + `minio-init` | S3-compatible storage, private bucket | Replace with S3/R2 by setting `BDNA_S3_*` |
| `migrate` | Alembic migrations, then `cli check` | One-shot; only service that gets the owner credentials |
| `api` | FastAPI on :8000 (internal) | Health check `GET /health` |
| `worker` | Background jobs | Scale with `docker compose up -d --scale worker=3` |
| `mcp` | MCP server on :8001 (internal) | Routed at `/mcp` |
| `web` | Next.js dashboard on :3000 (internal) | |
| `caddy` | Public entry, TLS | `BDNA_HTTP_PORT` / `BDNA_HTTPS_PORT` |
| `n8n` | optional, `--profile automation` | see [n8n/README.md](../n8n/README.md) |
| `demo-seed` | optional, `--profile demo` | three fictional customers, development only |

### Public HTTPS

Set `BDNA_SITE_ADDRESS=brand.example.com`, map ports 80 and 443 (`BDNA_HTTP_PORT=80`,
`BDNA_HTTPS_PORT=443`), and set `BDNA_PUBLIC_BASE_URL` / `BDNA_MCP_PUBLIC_URL` to
`https://brand.example.com`, `BDNA_CORS_ORIGINS=["https://brand.example.com"]` and
`BDNA_COOKIE_SECURE=true`. Caddy obtains and renews the certificate.

Signed URLs for the bundled MinIO point at `BDNA_S3_PUBLIC_ENDPOINT_URL` (default
`http://localhost:9000`). In production either put MinIO behind its own TLS host name (e.g.
`files.brand.example.com` → `minio:9000`) or use S3/R2.

### Cloudflare R2 or Amazon S3

```
BDNA_STORAGE_BACKEND=s3
BDNA_S3_BUCKET=brand-dna
BDNA_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com   # empty for AWS S3
BDNA_S3_PUBLIC_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
BDNA_S3_REGION=auto                                                  # e.g. eu-central-1 for S3
BDNA_S3_ADDRESSING_STYLE=auto
BDNA_S3_ACCESS_KEY_ID=…
BDNA_S3_SECRET_ACCESS_KEY=…
```

Keep the bucket private. The credentials need get, put, delete and list on the bucket. Enable
bucket versioning or provider backups for point-in-time recovery of files. You can then remove
the `minio` services with a `docker-compose.override.yml`.

### Managed PostgreSQL (e.g. Supabase)

The platform needs PostgreSQL 15+ with `vector` and `pg_trgm`, three login roles and permission
to `SET LOCAL` custom settings — Supabase, RDS, Cloud SQL and Neon qualify.

1. Enable the extensions (Supabase: *Database → Extensions* → `vector`, `pg_trgm`).
2. Create the roles with the SQL from `deploy/postgres/init-roles.sh` (run it with `psql` as the
   provider's admin role, or paste the SQL into the SQL editor). `bdna_app` must be
   `NOBYPASSRLS`. If the provider does not let you grant `BYPASSRLS` to a new role, use the
   provider's admin role for the **system** URL only — never for the app URL.
3. Use a **direct or session-mode** connection (port 5432). Transaction-mode poolers
   (Supavisor/PgBouncer on 6543) break prepared statements and per-session state.
4. Point the services at it in `docker-compose.override.yml`:

   ```yaml
   x-db: &db
     BDNA_DATABASE_APP_URL: postgresql+psycopg://bdna_app:…@db.<project>.supabase.co:5432/postgres?sslmode=require
     BDNA_DATABASE_SYSTEM_URL: postgresql+psycopg://bdna_system:…@db.<project>.supabase.co:5432/postgres?sslmode=require
   services:
     api:    { environment: *db }
     worker: { environment: *db }
     mcp:    { environment: *db }
     migrate:
       environment:
         <<: *db
         BDNA_DATABASE_OWNER_URL: postgresql+psycopg://bdna_owner:…@db.<project>.supabase.co:5432/postgres?sslmode=require
   ```

   and disable the bundled `postgres` service (or leave it unused).
5. `docker compose run --rm migrate` must end with three `[  ok]` isolation checks.

Supabase Auth, Storage policies and the auto-generated REST API are not used; keep the platform
tables out of the exposed schemas or disable the Data API for them.

## Configuration

All settings are environment variables prefixed `BDNA_` — the annotated list is
[`.env.example`](../.env.example) (deployment) and [`backend/.env.example`](../backend/.env.example)
(native development). Precedence: real environment > `backend/.env` > repository `.env`.
Production refuses to start without a strong `BDNA_SECRET_KEY` and a `BDNA_ENCRYPTION_KEY`.

AI providers: set `BDNA_AI_VISION_PROVIDER`, `BDNA_AI_TEXT_PROVIDER`,
`BDNA_AI_EMBEDDING_PROVIDER` (and keys). Without them the clearly labelled development adapter
runs. Workspaces can override per capability in Integrations → AI providers. **After changing
the embedding model, re-index** each brand (Settings → Brands → Re-index, or
`python -m app.cli reindex --org <slug>`).

## Operations CLI

Run inside the backend image (`docker compose run --rm api python -m app.cli …`) or from
`backend/` natively:

| Command | Does |
|---|---|
| `migrate` | Apply migrations (needs the owner URL) |
| `check` | Verify database reachability, RLS forced on every tenant table, app role cannot bypass RLS, fail-closed reads, media tools, AI providers |
| `create-admin --email … [--name …]` | Create or promote a platform administrator (prompts for a password, or `--password` / `BDNA_ADMIN_PASSWORD`) |
| `worker` | Run the job worker (`BDNA_WORKER_CONCURRENCY` threads) |
| `drain` | Run all queued jobs once and exit (small installs, maintenance) |
| `cleanup` | Expire old exports, remove abandoned import staging |
| `reindex --org <slug> [--brand <slug>]` | Re-embed a workspace or brand |
| `seed-demo` | Fictional demo data — refuses in production unless `--force` |

## Upgrades

```bash
git pull
docker compose build
docker compose up -d        # `migrate` runs first; api/worker/mcp wait for it
```

Migrations are forward-only in production; take a backup first. The `migrate` service fails
the deployment if the isolation check fails.

## Backups and restore

```bash
scripts/backup.sh                 # → backups/bdna-<UTC timestamp>/
scripts/restore.sh backups/bdna-20261015T020000Z
```

A backup contains `database.dump` (pg_dump custom format, including RLS policies and grants),
`storage/` (bundled MinIO or local storage) and `MANIFEST.sha256`. With external S3/R2 the
script records that object storage must be backed up with the provider's tools (versioning,
replication or `rclone`). Restore verifies every checksum first, stops the app containers,
restores, re-runs migrations and the isolation check, and starts them again.

Schedule backups with cron or your platform's scheduler and copy them off the host. Test a
restore regularly — for example into a scratch database (the script works natively against any
`BDNA_DATABASE_OWNER_URL`).

Customer-level copies are different: a **customer export** (Exports & imports) is the portable,
per-customer archive described in [export-format.md](export-format.md).

## Retention and deletion

| Data | Lifecycle |
|---|---|
| Customer workspace | Active → archived (closed to members, data kept) → deletion requested (purge scheduled after a grace period, default 30 days; reactivate to cancel) → purged (all objects under `orgs/<id>/` and every database row) |
| Assets | Soft delete (restorable from the library's "show deleted"); removed with the customer |
| Exports | Downloadable for `BDNA_EXPORT_TTL_DAYS` (default 14), then expired and their files deleted |
| Import staging | Removed after commit or discard; abandoned uploads cleaned by the worker |
| Sessions | Expire after `BDNA_SESSION_TTL_HOURS`; revocable by the user's sign-out or an administrator |
| Audit log | Kept for the life of the workspace; append-only |

## Monitoring

* `GET /health` on the API (also the container health check); `python -m app.cli check` for a
  deeper probe.
* Admin console → **Processing** shows queue depth by status, failures by job type and average
  durations across customers; **Settings** shows configuration warnings (development secrets or
  AI adapters, insecure cookies, local file storage) and media-tool availability without
  revealing secrets.
* Logs go to stdout/stderr (`docker compose logs -f api worker`). Failed jobs keep their error
  and traceback in `processing_jobs.error`.
* Alert on: dead jobs increasing, webhook delivery failures, queue age, disk/bucket usage, and
  repeated `auth.login_failed` in the activity log.

## Scaling

* **API**: stateless; run more replicas behind Caddy (add upstreams) — sessions live in the database.
* **Workers**: scale horizontally; jobs are claimed with `SKIP LOCKED`. Video and AI analysis are
  the heavy parts; give workers CPU and memory accordingly and limit with
  `BDNA_MAX_VIDEO_KEYFRAMES`, `BDNA_AI_MAX_IMAGES_PER_ASSET`.
* **Database**: vector search uses HNSW indexes per dimensionality; size `shared_buffers` and
  `maintenance_work_mem` for the embedding volume.

## Rotating secrets

* `BDNA_SECRET_KEY`: invalidates all sessions and outstanding signed file links; people sign in
  again.
* `BDNA_ENCRYPTION_KEY`: integration secrets are encrypted with it — re-enter webhook secrets and
  AI keys after rotating (they cannot be decrypted with a new key).
* Database role passwords: `ALTER ROLE … PASSWORD`, update `.env`, `docker compose up -d`.
* API tokens: create a new token, switch the client, revoke the old one.

## Native development

```bash
# PostgreSQL 16+ with pgvector; create roles and database once:
sudo -u postgres env BDNA_DB_OWNER_PASSWORD=bdna_owner BDNA_DB_APP_PASSWORD=bdna_app \
  BDNA_DB_SYSTEM_PASSWORD=bdna_system deploy/postgres/init-roles.sh
cd backend && python -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/python -m app.cli migrate
.venv/bin/uvicorn app.main:app --reload            # API on :8000
.venv/bin/python -m app.cli worker                 # in another terminal
cd ../frontend && npm ci && npm run dev            # dashboard on :3000
scripts/reset-dev.sh                               # optional: wipe and load the fictional demo customers
```

Tests: `cd backend && .venv/bin/python -m pytest` (needs a `bdna_test` database with the same
roles — `BDNA_DB_NAME=bdna_test` for `init-roles.sh`), `cd frontend && npm run typecheck &&
npm run lint && npx playwright test`.
