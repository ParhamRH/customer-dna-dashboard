# 0004 — Provider-independent AI with a labelled development adapter

**Status:** Accepted

## Context

Customers differ in which AI providers they may use (data residency, contracts, cost), models
change often, and a development or demo environment must work without credentials. The brief
forbids hard-coding a provider and asks for a clearly labelled development adapter when
credentials are missing.

## Decision

* `app/ai/base.py` defines small protocols: vision, text, embeddings (text and visual), OCR.
  Implementations: Anthropic, any OpenAI-compatible endpoint, an HTTP visual-embedding service
  (CLIP/SigLIP style), and the **development adapter** `dev-heuristic`.
* Resolution order per capability: an active **workspace override** (Integrations → AI
  providers; key stored Fernet-encrypted) → platform environment settings → development adapter.
* The development adapter is deterministic and derives its output from real measurements of
  the media (palette, luminance, contrast, edges, symmetry, motion) — it does not invent
  objects. Everything it produces is labelled "dev adapter" in the UI, in context packages and
  in `cli check`.
* Prompts are **versioned templates** (`app/ai/prompts.py`), overridable per workspace; every
  analysis records the prompt key and version. Model output is validated against Pydantic
  schemas before it is stored.
* Search always embeds the query with the **same model** that indexed the content; embeddings
  are stored per model and dimension, so switching models requires a re-index (Settings →
  Brands → Re-index) rather than silently mixing vector spaces.

## Consequences

* The platform runs end-to-end offline; switching to a real provider is configuration.
* Live providers are implemented against their public APIs but were not exercised with real
  credentials in this build (see `docs/unfinished-features.md`).
