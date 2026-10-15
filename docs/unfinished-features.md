# Unfinished features and known limitations

Honest status of what is not done, not verified, or deliberately simplified. Items are roughly
ordered by how much they matter for a production launch.

## Not verified in this build environment

| Area | Status |
|---|---|
| Docker images | Dockerfiles and Compose are written and `docker compose config` validates, but images were **not built or run** here (no Docker daemon or registry access). Expect to fix small issues on first build. |
| Live AI providers | Anthropic and OpenAI-compatible adapters are implemented against the public APIs but were **not exercised with real credentials** (no network/keys). All automated tests use the labelled development adapter. |
| S3 / R2 / MinIO storage | The S3 backend (create-only writes, presigned URLs with a public endpoint) is implemented; automated tests run on local storage only. |
| Visual-embedding service | The HTTP CLIP/SigLIP adapter is an interface; no real service was connected. Visual similarity in the demo uses the development descriptor. |
| Docling | Optional extra (`WITH_DOCLING=1`); not installed or tested here. PyMuPDF + Tesseract is the tested path. |
| Supabase / managed Postgres | Documented (roles, pooler mode); not deployed. |
| n8n workflow | Valid workflow JSON written to the n8n 1.x format; not imported into a running n8n. |

## Missing features

* **Single sign-on and MFA** (SAML/OIDC, TOTP/WebAuthn). Only e-mail + password with throttling.
* **E-mail**: no outgoing mail. Invitations create the account with a password chosen by the
  inviter (or a one-time temporary password); no self-service "forgot password" — an
  administrator resets it.
* **Undo a committed import** as one operation. Commits are atomic (a failed import changes
  nothing), but rolling back a successful import means deleting the created brand or restoring a
  backup.
* **Audio understanding**: audio assets get technical metadata only — no transcription or
  audio-based analysis. Video analysis is visual (scenes, camera movement, keyframes), not
  speech.
* **Asset versions**: replacing an asset's file with a new version (keeping history) is not
  supported; upload a new asset and deprecate the old one.
* **HEIC images** are detected but need `pillow-heif` installed to be decoded.
* **Real-time updates**: the dashboard polls (processing status, review counts); there are no
  websockets/server-sent events.
* **Search ranking evaluation**: fusion weights are heuristic; there is no relevance-feedback or
  evaluation set per customer.
* **Large graphs**: the graph endpoint returns up to 2,000 relationships and the map renders
  everything client-side; very large brands need server-side clustering or paging.
* **Internationalisation**: the dashboard is English only; knowledge content may be in any
  language (each brand records its primary language).
* **Per-customer quotas** exist for storage; there are no AI cost budgets or rate limits per
  workspace.
* **Fine-grained token scopes** are supported by the API, but the dashboard's token dialog only
  offers role, brand and expiry.

## Development-only features (clearly labelled)

* The **development AI adapter** (`dev-heuristic`): deterministic, measurement-based output,
  labelled "dev adapter" in the UI, packages, `cli check` and the admin settings.
* **Demo data** (`seed-demo`, `scripts/reset-dev.sh`, Compose `demo` profile): three fictional
  customers (Aurora Atelier, Northwind Mobility, Kiln & Thread) with generated media, marked
  "DEMO DATA" in their profiles; refuses to run in production without `--force`.
