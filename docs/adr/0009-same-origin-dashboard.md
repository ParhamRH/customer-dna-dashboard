# 0009 — Same-origin dashboard with cookie sessions; tokens for machines

**Status:** Accepted

## Context

The dashboard needs authenticated file previews (`<img src>`), large uploads and simple,
secure session handling. Scripts and AI clients need long-lived, revocable, narrowly scoped
credentials.

## Decision

* The browser only ever talks to **one origin**: in production Caddy routes `/v1/*` and
  `/health` to the API (streaming uploads) and everything else to Next.js; in development Next
  rewrites `/v1/*`. Next's request proxy (`proxy.ts`) is deliberately not used so uploads are
  not buffered.
* People sign in with e-mail and password (Argon2id). The session is a signed token in an
  **HttpOnly, SameSite=Lax cookie** backed by a revocable server-side session row. Mutating
  requests must send `X-BDNA-CSRF: 1` (a custom header cross-site forms cannot set). Repeated
  failures are throttled per e-mail and per IP.
* The workspace is chosen per request with `X-Organization-Id` (id or slug) and checked
  against the user's memberships; URLs are `/w/<org-slug>/<brand-slug>/…`.
* Machines use **API tokens** (`bdna_…`, stored as SHA-256, shown once) bound to one
  workspace, optionally one brand, with a role no higher than their creator's and an optional
  scope subset and expiry.
* The UI hides what a role cannot do, but every check is enforced by the API and the database.

## Consequences

* No CORS for the dashboard, no tokens in browser storage.
* Signed file URLs work in `<img>`/`<video>` without exposing credentials.
