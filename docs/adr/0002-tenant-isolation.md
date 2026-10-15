# 0002 — Tenant isolation with Row Level Security and three database roles

**Status:** Accepted

## Context

Customer data must never reach another customer: not through an API bug, a forgotten filter, a
search query, an export or an AI client. Filtering in application code alone fails open — one
missing `WHERE organization_id = …` leaks data. The brief also forbids relying on frontend
filtering and forbids unfiltered global access for AI clients.

## Decision

1. **Every tenant-owned table has `organization_id NOT NULL`** and Row Level Security is
   **enabled and forced** on it (36 tables). Policies compare `organization_id` with the
   transaction setting `app.org_id`.
2. **Three PostgreSQL roles** (`deploy/postgres/init-roles.sh`):
   * `bdna_owner` owns the schema and runs migrations only.
   * `bdna_app` — `NOBYPASSRLS`, used by every request, the worker's tenant work, exports and the
     MCP server. Without `app.org_id` it sees **no** tenant rows (fails closed).
   * `bdna_system` — `BYPASSRLS`, used only by a short list of platform functions: sign-in,
     platform administration and aggregates, job claiming, organization purge.
3. **The tenant context is set per transaction** (`SET LOCAL app.org_id / app.user_id`) by the
   request dependency after authorization. The organization comes from the session membership
   (header `X-Organization-Id`) or is fixed by the API token.
4. **Same-organization foreign keys**: child rows reference `(organization_id, id)` of their
   parents, so a row cannot point at another tenant's brand or asset even with a forged id.
5. **Defence in depth** on top of RLS: brand restriction for brand-bound tokens, permission
   checks per endpoint, export "tenant purity" scan of every exported document, storage keys
   prefixed `orgs/<org_id>/` and checked on every signed URL, audit log of sensitive actions.
6. `python -m app.cli check` (also run by the Compose `migrate` service) verifies at deploy time
   that RLS is forced on every tenant table, that the app role cannot bypass it, and that no
   tenant rows are visible without a context.

## Consequences

* A missing filter in new code returns nothing instead of another customer's data; tests in
  `tests/test_tenant_isolation_db.py` exercise this directly against the database.
* Platform-wide features must be written deliberately against `bdna_system` and are kept few
  and reviewed; they are listed in `app/db/session.py`.
* Cross-tenant joins are impossible by construction — the platform admin console aggregates
  through narrow system functions rather than ad-hoc queries.
* Managed Postgres must allow custom roles and `SET LOCAL` of custom settings (Supabase,
  RDS, Cloud SQL, Neon do).
