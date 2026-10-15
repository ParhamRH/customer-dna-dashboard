# 0003 — Governed knowledge: human approval, immutable revisions, published versions

**Status:** Accepted

## Context

Brand knowledge is only valuable if people can trust it. AI models produce plausible but
unreviewed interpretations; editors draft rules that are not yet agreed. The brief requires
that unreviewed AI output is never treated as official brand knowledge.

## Decision

* Principles, guidelines, aesthetic concepts and knowledge entries share one lifecycle:
  `draft → in_review → approved | rejected → deprecated | archived` (plus `restore`).
  Approve/reject/deprecate need the `knowledge.approve` permission **and a signed-in person** —
  API tokens can never approve.
* Every save writes an **immutable revision** (full snapshot, status, author and change note). The
  "official view" is the latest approved revision; editing an approved item creates a new draft
  revision without changing what is official until it is approved.
* **AI output lives apart from knowledge.** Asset analyses are stored as interpretations with
  provider, model, prompt version, schema version and confidence, split into *objective*
  observations (measured or directly visible) and *interpretation*. They start as
  `pending_review`. Accepting an interpretation makes it the asset's description for search and
  context; it never creates or changes a rule.
* AI **suggestions** (tags, concept links, new concepts, principle candidates) are a separate
  queue. Accepting one creates a *draft* (or a relationship), which still needs approval.
* A **brand version** is a published, checksummed snapshot of the approved knowledge. Context
  packages and exports can be generated from the live approved state or from a published version.

## Consequences

* Search, context generation, exports and the MCP server can tell official from pending
  material everywhere (the UI shows status by shape; packages label pending interpretations).
* Reviewing is real work; the review queue with keyboard shortcuts and bulk decisions exists to
  keep it fast.
* Revisions grow with every save; they are small JSON documents and are exported with the brand.
