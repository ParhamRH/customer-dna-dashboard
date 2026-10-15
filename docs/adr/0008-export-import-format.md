# 0008 — Self-describing, checksummed export format and staged imports

**Status:** Accepted

## Context

Customers must be able to take their library elsewhere, and exports must be reproducible and
independently verifiable. Imports must never half-apply or leak into another workspace.

## Decision

* An export is a ZIP with a readable layout (`customer/`, `brand/<domain>/<brand>/`, `assets/`,
  `projects/`, `relationships/`, `ai-knowledge/`, `embeddings/`, `documentation/`), a
  `README.md`, a data dictionary and a `manifest.json` with schema version, counts, options and
  a SHA-256 for every file. Full in [docs/export-format.md](../export-format.md).
* Built in a tenant session, then scanned: every JSON document is checked for foreign
  `organization_id` values before the archive is sealed. Originals are re-verified against their
  stored checksums.
* Embeddings are optional and labelled as model-specific.
* Imports are **staged**: upload → validate (format, schema version, every checksum, no files
  outside the manifest, zip-slip safe) → preview → the user maps brands (create / merge) and
  chooses options → commit in **one transaction** → re-index. Any failure rolls the whole import
  back; discarding removes the staging files. IDs are remapped, so an export can be imported
  into any workspace without colliding.

## Consequences

* Anyone can verify an export with a few lines of Python (included in its README).
* A committed import cannot yet be undone as a unit (see unfinished features); restore from a
  backup or delete the created brand.
