# MCP server

The platform includes a **read-only** [Model Context Protocol](https://modelcontextprotocol.io)
server so AI assistants (Claude, Cursor, custom agents) can use a customer's brand knowledge
while they work. Design rationale: [ADR 0010](adr/0010-read-only-mcp-server.md).

## Access model

* Each client authenticates with a **workspace API token** (`bdna_…`). Create one in the
  workspace under **Integrations → API & MCP → New token**; the *Viewer* role is enough and is
  recommended. Optionally restrict it to one brand and give it an expiry.
* The token fixes the workspace (and brand, if restricted). Every tool runs in a
  Row-Level-Security tenant session — there is no tool, parameter or resource that reaches
  another workspace or the database directly.
* There are **no write tools**. Changes happen through people in the dashboard.
* Every tool call is written to the workspace audit log (actor = the token).
* Responses separate official knowledge from unreviewed material: approved principles,
  guidelines, concepts and entries are official; asset interpretations carry their review status
  and pending ones are marked as unreviewed AI output.

## Connecting

### Remote (Streamable HTTP)

Behind the Compose stack the server is at `https://<your-domain>/mcp` (Caddy routes `/mcp` to
the `mcp` container). The workspace shows the exact URL and a ready-made configuration under
Integrations → API & MCP.

```json
{
  "mcpServers": {
    "brand-dna": {
      "type": "http",
      "url": "https://brand.example.com/mcp",
      "headers": { "Authorization": "Bearer bdna_…" }
    }
  }
}
```

### Local (stdio)

Run the server next to the assistant with the backend installed and database access:

```json
{
  "mcpServers": {
    "brand-dna": {
      "command": "python",
      "args": ["-m", "app.mcp"],
      "cwd": "/path/to/brand-dna-platform/backend",
      "env": { "BDNA_MCP_TOKEN": "bdna_…" }
    }
  }
}
```

Running the HTTP server yourself:
`python -m app.mcp --transport streamable-http --host 0.0.0.0 --port 8001 --public-url https://brand.example.com`
(`BDNA_MCP_PUBLIC_URL` sets the public URL used in OAuth protected-resource metadata).

## Tools

`brand_id` is optional whenever the token is bound to one brand or the workspace has only one.

| Tool | Arguments | Returns |
|---|---|---|
| `list_brands` | — | Brands this token can access |
| `get_brand_identity` | `brand_id?` | Foundation (mission, vision, positioning, personality, values, audience …), core aesthetic concepts, published version |
| `get_visual_identity` | `brand_id?` | Approved palettes (HEX/RGB/HSL/OKLCH/CMYK), typography, logo assets, visual-identity rules, design tokens |
| `get_design_guidelines` | `brand_id?`, `domain?`, `project_type?` | Official principles grouped by classification, and guidelines |
| `get_brand_language` | `brand_id?` | Tone of voice, vocabulary, preferred/restricted expressions, writing examples, language principles |
| `search_brand_assets` | `query`, `brand_id?`, `asset_types?`, `approved_only?`, `limit?` | Hybrid search, e.g. "videos with slow cinematic camera movement"; matched scenes/pages |
| `search_aesthetic_concepts` | `query?`, `brand_id?` | Official concepts with definitions, synonyms, related and opposing concepts |
| `get_asset_details` | `asset_id` | Technical metadata, accepted or pending interpretation (labelled), tags, segments, relationships |
| `find_related_assets` | `asset_id?`, `concept_id?`, `principle_id?`, `modality?`, `limit?` | Visually or semantically similar assets, or assets linked to a concept/principle |
| `get_color_palette` | `brand_id?` | Approved palettes with all colour spaces and a WCAG contrast matrix |
| `get_typography_system` | `brand_id?` | Typography systems with hierarchy and typographic tokens |
| `generate_brand_context` | `task_type`, `brand_id?`, `mode?`, `creative_direction?`, `output_medium?`, `concept_ids?`, `project_id?`, `format?` | A task-specific brief (Markdown or JSON) with sources; not saved |

`task_type`: `website_design`, `website_development`, `social_media`, `brand_campaign`,
`graphic_design`, `product_design`, `image_generation`, `video_generation`, `presentation`,
`copywriting`, `other`. `mode`: `compact`, `standard`, `comprehensive`.

## Resources

| URI | Contents |
|---|---|
| `brand://{brand_id}/identity` | Official brand identity |
| `brand://{brand_id}/guidelines` | Official principles and guidelines |
| `brand://{brand_id}/visual-identity` | Palettes, typography, tokens |
| `brand://{brand_id}/language` | Brand language |

## Guidance given to clients

The server's instructions tell the assistant to treat *mandatory* and *prohibited* principles as
hard constraints, never to present pending interpretations as brand rules, to cite source ids
(e.g. `principle:<id>`) and suggest the flow: `get_brand_identity` →
`get_design_guidelines` / `get_visual_identity` → `search_brand_assets` →
`generate_brand_context`.

## Revoking access

Revoke the token (Integrations → API & MCP). The next request from that client is refused.
