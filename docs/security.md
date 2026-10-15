# Security

What protects whom, and where it lives in the code. The design principle throughout: **the
database and the API enforce every rule; the dashboard only reflects them.**

## Threats this design addresses

| Threat | Controls |
|---|---|
| A customer sees another customer's data | Row Level Security forced on every tenant table; runtime role cannot bypass it; tenant context per transaction; same-organization foreign keys; brand-bound tokens; export purity scan; storage namespace check — [ADR 0002](adr/0002-tenant-isolation.md) |
| Unreviewed AI output becomes "official" | Separate analysis/suggestion tables; approval only by a signed-in person with `knowledge.approve`; status shown by shape in every view; context packages and MCP responses label pending material — [ADR 0003](adr/0003-governed-knowledge.md) |
| An AI client reads everything | MCP is read-only and token-bound to one workspace (optionally one brand), runs under RLS, audited — [ADR 0010](adr/0010-read-only-mcp-server.md) |
| Stolen or guessed credentials | Argon2id password hashes; sign-in throttling per e-mail and per IP; revocable server-side sessions; admin "revoke sessions" and password reset; deactivation ends sessions immediately |
| Cross-site request forgery | HttpOnly `SameSite=Lax` session cookie **and** a required `X-BDNA-CSRF: 1` header on every mutating cookie-authenticated request |
| Leaked file links | Private buckets; signed URLs expire (default 15 min) and are only issued after authorization; local file tokens are HMAC-signed and bound to one key |
| Malicious uploads | File type sniffed from content (not the extension); size limit; originals stored create-only and never executed; SVGs rasterized for previews; files served with `Content-Security-Policy: …; sandbox` and `nosniff`; archive extraction rejects path traversal |
| Server-side request forgery via webhooks / AI base URLs | Customer-supplied URLs are checked when saved and again before each request; private, loopback and link-local targets are refused in production unless allow-listed (`BDNA_OUTBOUND_ALLOWED_HOSTS`); redirects are not followed |
| A customer redirects AI calls to steal the platform's API key | A workspace AI override with its own base URL must bring its own key; platform keys are only sent to platform-configured endpoints |
| Tampered exports or backups | SHA-256 for every file in the manifest; imports and `scripts/restore.sh` refuse anything that does not verify |
| Privilege escalation through tokens or invitations | Tokens and invited members cannot exceed their creator's role; scopes must be a subset of the role; customer admins cannot create platform admins |
| Operator mistakes | `python -m app.cli check` verifies isolation on every deploy; production refuses to start with development secrets; least-privilege credentials per container |

## Authentication

* **People**: e-mail + password (Argon2id via `argon2-cffi`). Sign-in creates an `auth_sessions`
  row and a signed session token in the `bdna_session` cookie (HttpOnly, SameSite=Lax, `Secure`
  when `BDNA_COOKIE_SECURE=true`). Every request re-checks that the session is not revoked or
  expired and that the user is active.
* **Throttling**: more than `BDNA_LOGIN_MAX_FAILURES_PER_EMAIL` (default 8) failures for an
  e-mail, or `BDNA_LOGIN_MAX_FAILURES_PER_IP` (40) from one IP, within
  `BDNA_LOGIN_WINDOW_MINUTES` (15) returns `429` until the window passes. Failures are recorded
  in the audit log (in their own transaction) and shown in the platform activity log.
* **Machines**: API tokens `bdna_<random>`; only a SHA-256 is stored and the prefix is shown for
  identification. Bound to one workspace, optionally one brand; role ≤ creator's; optional scope
  subset; optional expiry; revocable; `last_used_at` tracked. Tokens can read and write within
  their permissions but can **never approve** knowledge.

## Authorization

Permissions per role (customer roles; the platform super administrator has all):

| Permission | Admin | Creative director | Editor | Reviewer | Viewer |
|---|:-:|:-:|:-:|:-:|:-:|
| Read brand, knowledge, assets; search | ✓ | ✓ | ✓ | ✓ | ✓ |
| Write knowledge, upload and edit assets, collections, projects | ✓ | ✓ | ✓ | | |
| Approve knowledge, manage concepts, publish versions, manage brands | ✓ | ✓ | | | |
| Review AI output (decide) | ✓ | ✓ | | ✓ | |
| Generate context packages | ✓ | ✓ | ✓ | ✓ | |
| Download originals | ✓ | ✓ | ✓ | ✓ | |
| Delete assets | ✓ | ✓ | | | |
| Create / download exports | ✓ | ✓ | | | |
| Run imports | ✓ | | | | |
| Members, API tokens, integrations, workspace profile | ✓ | | | | |
| Audit log | ✓ | ✓ | | | |
| Processing jobs: view | ✓ | ✓ | ✓ | ✓ | |
| Processing jobs: retry / cancel | ✓ | ✓ | | | |

The authoritative matrix is data (`roles`, `role_permissions`, seeded by migration 0002) and is
displayed in the admin console under Users.

## Data protection

* **At rest**: integration secrets (webhook signing secrets, customer AI keys) are encrypted
  with Fernet (`BDNA_ENCRYPTION_KEY`) and never returned by the API or included in exports.
  Database and bucket encryption are the responsibility of the hosting provider.
* **In transit**: Caddy terminates TLS with automatic certificates when `BDNA_SITE_ADDRESS` is a
  domain. Set `BDNA_COOKIE_SECURE=true` behind HTTPS.
* **Least privilege in Compose**: API, worker and MCP containers do not receive the PostgreSQL
  superuser password or the schema owner's URL; only the one-shot `migrate` service does.
* **Errors**: workspace users see the first line of a job error; stack traces stay in the
  database and logs.
* **Audit**: sign-ins (and failures), member and token changes, knowledge transitions, review
  decisions, asset changes, exports/imports, integration changes, MCP tool calls and platform
  administration are written to the append-only `audit_logs` table (the runtime roles may insert
  and read, never update or delete).

## Retention and deletion

Archiving a customer closes the workspace to its members. "Request deletion" (typed
confirmation of the slug) closes it immediately and schedules a purge after a grace period
(default 30 days); reactivating cancels it. The purge deletes every object under the customer's
storage prefix and the organization row, which cascades to all tenant rows. Expired exports and
abandoned import staging are cleaned by the worker's janitor. See [operations.md](operations.md).

## Reporting

Operators should review `docs/unfinished-features.md` for known gaps (for example SSO/MFA)
before exposing an installation to the internet.
