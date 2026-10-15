# REST API

Base path `/v1` on the platform origin (e.g. `https://brand.example.com/v1`). The interactive
reference generated from the code is at **`/docs`** (Swagger UI) and `/openapi.json`; this page
explains the conventions and gives a map of the 111 operations.

## Authentication

| Client | How |
|---|---|
| Dashboard (browser) | `POST /v1/auth/login` sets the HttpOnly `bdna_session` cookie. Every non-GET request must also send `X-BDNA-CSRF: 1`. |
| Scripts, n8n, CI | `Authorization: Bearer bdna_…` — a workspace API token (Integrations → API & MCP). No CSRF header needed. |

Tokens are bound to one workspace (and optionally one brand). Their role and optional scopes
limit what they can do; they can never approve knowledge.

## Choosing the workspace

Send `X-Organization-Id: <organization id or slug>` with workspace requests. Signed-in people
must be members of that workspace; for API tokens the header is optional (the token already fixes
the workspace) and must match if sent. Platform endpoints (`/v1/platform/*`, `/v1/organizations`)
need a platform administrator and no workspace header.

## Conventions

* JSON in, JSON out; IDs are UUIDs; timestamps are ISO 8601 UTC.
* **Lists** take `limit` (1–500, default 50) and `offset` and return
  `{"items": [...], "total": n, "limit": l, "offset": o}`; small fixed lists return `{"items": [...]}`.
* **Errors** always look like
  `{"error": {"code": "validation_failed", "message": "…", "details": …}}`. Codes:
  `bad_request` 400, `unauthorized` 401, `forbidden` 403, `not_found` 404 (also used when a
  record exists in another workspace — existence is never revealed), `conflict` 409,
  `validation_failed` 422, `rate_limited` 429.
* **Long work is asynchronous**: uploads, re-processing, exports, imports and re-indexing return
  quickly and create jobs. Poll the resource or `GET /v1/jobs/{id}`, or subscribe to webhooks.
* **Files** are never streamed through JSON. Endpoints return short-lived **signed URLs**
  (`thumbnail_url`, `preview_url`, `GET /v1/assets/{id}/download` → `{"url": …}`); fetch them
  without credentials before they expire (default 15 minutes).
* **Governed knowledge** has a `status` (`draft`, `in_review`, `approved`, `rejected`,
  `deprecated`, `archived`) and a `version`. Only `approved` is official.

## Operations

### Session and account
`POST /auth/login` · `POST /auth/logout` · `GET /auth/me` (user, memberships) · `POST /auth/password`

### Workspace
`GET|PATCH /workspace` (profile, your role and permissions, brands) · `GET /workspace/overview` ·
members `GET|POST /workspace/members`, `PATCH|DELETE /workspace/members/{id}` ·
API tokens `GET|POST /workspace/api-tokens`, `POST /workspace/api-tokens/{id}/revoke` (the
plaintext token is returned once, on creation) · `GET /workspace/audit-log?action=<prefix>`

### Brands and versions
`GET|POST /brands` · `GET|PATCH /brands/{id}` (includes coverage overview) ·
`POST /brands/{id}/reindex` · `GET|POST /brands/{id}/versions` (publish a snapshot of approved
knowledge) · `GET /brand-versions/{id}` (snapshot + checksum)

### Knowledge (domains, principles, guidelines, concepts, entries)
* `GET /knowledge/registry` — the ten domains and every entry type with its structured fields.
* `GET /brands/{id}/domains/{domain_key}` — one domain: entries, principles, guidelines, coverage.
* Collections `entries | principles | guidelines | concepts`:
  `GET|POST /brands/{id}/knowledge/{collection}`, `GET|PATCH|DELETE /knowledge/{collection}/{item}`,
  `POST /knowledge/{collection}/{item}/{action}` with action `submit | approve | reject |
  deprecate | archive | restore` (approve/reject/deprecate need a person with
  `knowledge.approve`), `GET …/revisions`, `GET …/export?format=json|yaml`.
* `GET /principles` (filter by brand, classification, domain, project type) · `GET /brands/{id}/guidelines`
* Graph: `POST /relationships`, `DELETE /relationships/{id}`,
  `GET /entities/{type}/{id}/relationships`, `GET /brands/{id}/graph?include_suggested=true`
  (nodes, edges; asset nodes carry thumbnails).

### Visual identity
Palettes `GET|POST /brands/{id}/palettes`, `PATCH|DELETE /palettes/{id}`, colors
`POST /palettes/{id}/colors`, `PATCH|DELETE /colors/{id}`, `GET /colors/convert?hex=…&against=…`
(all colour spaces + WCAG contrast) · typography `GET|POST /brands/{id}/typography`,
`PATCH|DELETE /typography/{id}` · design tokens `GET|POST /brands/{id}/design-tokens`,
`PATCH|DELETE /design-tokens/{id}`, `GET /brands/{id}/design-tokens/export?format=dtcg|css|tailwind|flat`

### Assets
* Upload: `POST /brands/{id}/assets` (multipart: `file` plus optional `title`, `description`,
  `asset_type`, `reference_role`, `folder_path`, `tags` (comma-separated), `license` (JSON),
  `curated_metadata` (JSON), `allow_duplicate`). Identical content already in the brand returns
  `409 duplicate_asset` with `details.existing_asset_id` unless `allow_duplicate=true`.
* External reference (no file): `POST /brands/{id}/references`.
* `GET /assets` — filters: `brand_id`, `q`, `asset_type`*, `approval_status`*, `reference_role`*,
  `tag`*, `collection_id`, `concept_id`, `principle_id`, `folder`, `processing_status`, `deleted`,
  `sort` (`newest|oldest|title|size|updated|relevance`); * = repeatable. Returns facets.
* `GET|PATCH|DELETE /assets/{id}` (soft delete) · `POST /assets/{id}/restore` ·
  `POST /assets/{id}/approval` · tags `POST /assets/{id}/tags`,
  `POST /assets/{id}/tags/{tag}/{accept|reject}`, `DELETE /assets/{id}/tags/{tag}` ·
  `GET /assets/{id}/download` (original; needs `assets.download_original`) ·
  `POST /assets/{id}/reprocess` · `GET /assets/{id}/similar?modality=visual|text` ·
  `POST /assets/bulk` (tags, approval, role, folder, collections, reprocess, delete) ·
  `GET /brands/{id}/folders`
* Collections: `GET|POST /brands/{id}/collections`, `GET|PATCH|DELETE /collections/{id}`,
  `POST /collections/{id}/assets`, `DELETE /collections/{id}/assets/{asset}`, `PUT /collections/{id}/order`

### AI review
`GET /review/summary` · `GET /review/analyses` and `POST /review/analyses/{id}`
(`{"decision": "approve" | "reject", "interpretive"?: edited interpretation, "brand_relevance"?, "accept_suggested_tags"?, "notes"?}`) ·
`GET /review/suggestions`, `POST /review/suggestions/{id}`
(`{"decision": "accept" | "reject", "edits"?: {...}, "notes"?}`), `POST /review/suggestions-bulk` ·
`GET /review/history`

### Search
* `POST /search` — `{"query": "videos with slow cinematic camera movement", "brand_id": …,
  "scope": "all|official|pending", "entity_types": [...], "asset_types": [...],
  "include_historical": true, "explain": true, "limit": 20}` → items with knowledge status,
  matched segments (scene / page), per-signal ranks when `explain`, and how the query was
  understood.
* `POST /search/visual` — multipart `image` (or `asset_id`) → visually similar assets.
* `GET /search/related?entity_type=…&entity_id=…&depth=1..3&relation_type=…` — graph neighbourhood
  (e.g. every asset associated with a principle).

### Projects and context generation
Projects `GET|POST /brands/{id}/projects`, `GET|PATCH|DELETE /projects/{id}` (PATCH accepts
`asset_ids`, `concept_ids`, `principle_ids` to link more) ·
`GET /context/templates` · `POST /context/preview` (what would be included) ·
`POST /context/generate` · `GET /context/packages`, `GET /context/packages/{id}`,
`GET /context/packages/{id}/download?format=md|json|yaml|zip`

### Exports and imports
`POST /exports` (`{"mode": "full" | "selective", "selection": {"brand_id", "domains", "asset_ids", "collection_ids", "project_id"}, "include_originals", "include_derivatives", "include_embeddings", "include_ai_knowledge", "include_pending"}`) ·
`GET /exports`, `GET /exports/{id}`, `GET /exports/{id}/download` (signed URL) ·
`POST /imports` (multipart ZIP) → validation report and preview · `GET /imports`, `GET /imports/{id}` ·
`POST /imports/{id}/commit` (`brand_mapping`: `{source_brand_id: "create" | "merge:<brand_id>"}`, options) ·
`DELETE /imports/{id}` (discard). Format: [export-format.md](export-format.md).

### Integrations
`GET|POST /integrations`, `PATCH|DELETE /integrations/{id}` (kinds `webhook`, `ai_provider`;
secrets are write-only) · `POST /integrations/{id}/test` · `GET /integrations/{id}/deliveries` ·
prompts `GET|POST /prompts`, `POST /prompts/{key}/reset`

### Jobs
`GET /jobs?status=…&job_type=…&entity_id=…` · `GET /jobs/{id}` · `POST /jobs/{id}/retry` · `POST /jobs/{id}/cancel`

### Platform administration (platform administrators only)
Customers `GET|POST /organizations`, `GET|PATCH /organizations/{id}`,
`POST /organizations/{id}/archive | reactivate | request-deletion` ·
`GET /platform/overview | activity | jobs | roles | exports | integrations | settings` ·
users `GET|POST /platform/users`, `PATCH /platform/users/{id}`,
`POST /platform/users/{id}/reset-password | revoke-sessions`

## Examples

```bash
BASE=https://brand.example.com
TOKEN=bdna_…            # Integrations → API & MCP → New token

# Find approved references for a brief
curl -s "$BASE/v1/search" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query": "approved references with organic geometry", "limit": 10}' | jq '.items[] | {title, knowledge_status}'

# Upload an asset (processing and AI analysis continue in the background)
curl -s "$BASE/v1/brands/$BRAND/assets" -H "Authorization: Bearer $TOKEN" \
  -F file=@hero.jpg -F title="Hero still" -F reference_role=official -F tags="ritual,still life"

# Generate a website brief from the published brand version, as Markdown
PKG=$(curl -s "$BASE/v1/context/generate" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"brand_id\": \"$BRAND\", \"task_type\": \"website_design\", \"mode\": \"standard\", \"use_published_version\": true}" | jq -r .id)
curl -s "$BASE/v1/context/packages/$PKG/download?format=md" -H "Authorization: Bearer $TOKEN" -o brief.md

# Full export, then download when ready
EXP=$(curl -s "$BASE/v1/exports" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"mode":"full"}' | jq -r .id)
curl -s "$BASE/v1/exports/$EXP" -H "Authorization: Bearer $TOKEN" | jq .status   # → completed
curl -sL "$(curl -s "$BASE/v1/exports/$EXP/download" -H "Authorization: Bearer $TOKEN" | jq -r .url)" -o export.zip
```
