# 0010 — A read-only MCP server bound to one workspace per token

**Status:** Accepted

## Context

AI assistants should be able to use brand knowledge while working, but the brief forbids
unfiltered global database access for external AI clients, and unreviewed AI output must not
be presented as brand rules.

## Decision

* `python -m app.mcp` exposes 12 read-only tools (identity, visual identity, guidelines,
  language, asset search, concepts, asset details, related assets, palette, typography,
  context generation). There are no write tools.
* Authentication is a workspace **API token** (Bearer over Streamable HTTP, `BDNA_MCP_TOKEN`
  over stdio). The token fixes the organization and optionally the brand; every tool runs in an
  RLS tenant session with the token's permissions.
* Responses distinguish official knowledge from pending interpretations; the server
  instructions tell the client to treat mandatory/prohibited principles as hard constraints and
  to cite source ids.
* Every tool call is audited in the workspace audit log.

## Consequences

* Connecting an assistant is a token and a URL; revoking access is revoking the token.
* AI clients cannot change the library — changes go through people in the dashboard.
