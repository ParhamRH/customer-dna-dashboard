# n8n automations

The platform emits signed webhooks for these events (Integrations → Webhooks in a workspace):

| Event | `data` fields |
|---|---|
| `asset.created` | `asset_id`, `brand_id`, `title` |
| `asset.processed` | `asset_id`, `status`, `pending_suggestions` |
| `review.decided` | `subject_type`, `subject_id`, `decision` |
| `knowledge.approved` | `entity_type`, `entity_id`, `version` |
| `brand.version_published` | `brand_id`, `version` |
| `export.completed` | `export_id`, `size_bytes` |
| `import.committed` | `import_id`, `created` |

Every delivery is a `POST` with the JSON envelope
`{"id", "type", "occurred_at", "organization_id", "data"}` and the headers `x-bdna-event`,
`x-bdna-timestamp` and — when the webhook has a secret — `x-bdna-signature: sha256=<hex>`, the
HMAC-SHA256 of `timestamp + "." + raw body`. Failed deliveries are retried with back-off (6
attempts); the workspace shows a delivery log per webhook. Payloads only ever contain the
workspace's own identifiers — fetch details with an API token bound to that workspace.

## Example workflow: `brand-dna-events.workflow.json`

1. **Brand DNA webhook** receives the event (raw body kept for signature checking).
2. **Verify signature** recomputes the HMAC and rejects bad signatures and events older than 5 minutes.
3. On `asset.processed` it **fetches the asset** and writes a short summary that says how many AI
   interpretations still need human review — connect the output to Slack, e-mail, etc.
4. On `brand.version_published` it **regenerates a website brief** from the newly published version
   (`POST /v1/context/generate` with `use_published_version: true`).

### Set up

```bash
docker compose --profile automation up -d n8n        # http://localhost:5678
```

1. In a workspace: **Integrations → API & MCP → New token** (role *Viewer* is enough to read;
   *Creative director* to generate context packages). Copy the token.
2. In n8n: **Credentials → New → Header Auth**, name it `Brand DNA API token`,
   header `Authorization`, value `Bearer bdna_…`.
3. Add the webhook's signing secret to the n8n container as `BDNA_WEBHOOK_SECRET`
   (e.g. in `docker-compose.override.yml`) and restart n8n.
4. **Import from file** → `/workflows/brand-dna-events.workflow.json` (mounted read-only), select
   the credential on both HTTP nodes and activate the workflow.
5. In the workspace: **Integrations → Webhooks → New webhook** with URL
   `http://n8n:5678/webhook/brand-dna` (inside Compose) or your public n8n URL, the same secret,
   and the events you want. Use **Test** to send `integration.test`.

`BDNA_API_URL` is preset to `http://api:8000` in the Compose file.
