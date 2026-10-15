# Progress log

Newest first. Each entry: what was built or changed, and how it was verified. Entries before
the dated one are in build order.

## 2026-10-15 — Deployment, hardening, documentation

* **Security fixes found while documenting**
  * Failed sign-ins were never recorded: the audit row was added inside the transaction that the
    `Unauthorized` error rolled back. Failures are now written in their own transaction.
  * Added **sign-in throttling** per e-mail and per IP (migration `0003` adds the supporting
    partial indexes); `429 rate_limited` past the limit.
  * Added an **outbound URL guard** (SSRF): webhook URLs and AI base URLs may not target private,
    loopback or link-local addresses in production unless allow-listed; checked on save and
    before every delivery; redirects are not followed.
  * A workspace AI override with its own base URL could have received the **platform's API key**;
    overrides with a custom endpoint must now bring their own key.
  * Workspace users now see only the first line of job errors; tracebacks stay server-side.
  * Production refuses to start with a development `BDNA_SECRET_KEY` or without
    `BDNA_ENCRYPTION_KEY`.
* **Deployment**: backend and frontend Dockerfiles, `docker-compose.yml` (pgvector Postgres with
  role bootstrap, MinIO + private bucket, migrate + isolation check, API, worker, MCP, web,
  Caddy, optional n8n and demo profiles; least-privilege credentials per service), Caddyfile,
  `.env.example` files, S3 public endpoint/addressing settings for presigned URLs.
* **Backups**: `scripts/backup.sh` / `restore.sh` (native and Compose modes, SHA-256 manifest,
  refuses tampered backups). Verified: backup of the demo installation (87 files), restore into a
  scratch database (3 customers, 25 assets, RLS checks pass), tampered file rejected.
* **n8n**: example workflow (signature verification, asset notifications, regenerate brief on
  publish) and setup guide.
* **Docs**: README, architecture, security, API, MCP, export format, operations, ten ADRs, this
  log, unfinished features.
* **End-to-end tests** (`frontend/e2e`, 18 Playwright tests): sign-in and redirects, console
  access, tenant isolation by URL, API and forged writes, role limits (viewer, reviewer, editor,
  creative director, admin), knowledge approval by a person only, search, video measurements,
  context generator, collections, graph, export with purity check and download, customer
  onboarding and purge. Pass against `next dev` and the production standalone build.
* **Mobile layout**: wide tables and swatch rows no longer widen the page at 390 px (grid items
  may shrink; absolutely positioned screen-reader text is contained by the table scroller; tab
  bars scroll). Checked every workspace and admin page for horizontal overflow.
* Demo seed accepts AI concept links only for the brand's own official assets (off-brand and
  inspiration links stay in the review queue).
* Verified: `docker compose config` for all profiles; backend suite (108 tests); ruff;
  TypeScript; ESLint (zero warnings); `next build`; standalone server smoke test.

## Customer workspace completed

* Projects (list, create/edit, detail with brief, reference assets, relationships, context
  packages), collections (mosaic list, detail with reorder, cover, add/remove via asset picker),
  knowledge graph (force layout with shapes by type, assets as thumbnails, suggested edges dashed
  amber, list view, find, unconnected items panel), workspace exports & imports, integrations
  (API tokens with one-time display and MCP config, MCP tools from the server definition,
  webhooks with test and delivery log, AI provider overrides, prompt template overrides with
  reset), settings (profile, brands with re-index, members, audit log, processing jobs with
  retry/cancel).
* Backend additions: graph nodes carry asset thumbnails and edge origin, rejected suggestions
  never appear; collection list previews; webhook delivery log; MCP connection info; prompt reset;
  brand re-index endpoint; collection order now follows the caller's order.
* Context packages no longer repeat an entry's body when it equals its summary.
* Replaced effect-driven state resets with render-phase resets (`useResetState`) and a
  `useSyncExternalStore` preference hook; ESLint (React Compiler rules) and TypeScript clean.
* Verified with Playwright: context generator end to end (task → scope → preview → package),
  collection create + add assets, webhook create/test/log, token creation, graph find; screenshot
  review of every new page.

## Video analysis accuracy

* Scene detection now combines PySceneDetect's adaptive and histogram detectors (subtle cuts were
  missed); camera movement classified per scene from Farneback optical flow on area-downscaled
  frames with a dual baseline, steadiness (sign consistency) and dominance rules (fast pans read
  correctly; static shots no longer read as zoom). Regression tests with synthetic films.

## Platform administration and operations

* Platform users (create admins, reset passwords, revoke sessions, deactivate with lock-out
  protection), cross-customer export registry, integrations inventory, settings page without
  secrets; operations CLI (`migrate`, `check`, `create-admin`, `seed-demo`, `worker`, `drain`,
  `cleanup`, `reindex`); worker janitor (export expiry, staging cleanup); customer list shows each
  brand's approved palette.
* Admin dashboard and the first half of the customer workspace (overview, the knowledge domains,
  visual identity with palettes/contrast/typography/tokens, aesthetics explorer, principles,
  asset library and detail, AI review queue, search).

## Earlier — Backend phases 1–7

1. Multi-tenant foundation: schema, three database roles, Row Level Security forced on every
   tenant table, auth (sessions, CSRF, API tokens), six roles, migrations.
2. Admin and workspace APIs.
3. Asset management, storage backends with signed URLs, PostgreSQL job queue and worker.
4. Multimodal ingestion (image, video, document, 3D, audio metadata), provider-independent AI with
   the development adapter, review queue.
5. Governed brand knowledge for the ten domains, revisions, brand versions, ontology, graph.
6. Hybrid retrieval and the creative context generator.
7. Customer export/import, REST API, read-only MCP server.

Followed by an audit of the backend against the brief and a fictional three-customer demo seed.
