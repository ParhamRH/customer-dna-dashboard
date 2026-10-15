# Export format — `brand-dna-library-export`

A customer export is a ZIP archive that is useful without this platform: readable JSON, the
original files, design tokens for developers, a README, a data dictionary and a manifest that
lets anyone verify every byte. Rationale: [ADR 0008](adr/0008-export-import-format.md).
Implementation: `backend/app/exports/exporter.py` (build) and `importer.py` (validate, commit).

## Guarantees

1. **One customer only.** Built inside that customer's Row-Level-Security session, then every
   JSON document is scanned and the export fails if any `organization_id` belongs to someone
   else (`manifest.tenant_purity_check`).
2. **Originals are byte-identical.** Each original is re-hashed while exporting and must match
   the SHA-256 recorded at upload.
3. **Independently verifiable.** `manifest.json` lists a SHA-256 for every other file.
4. **Reproducible content.** JSON is written deterministically from the database; the same data
   and options give the same documents (timestamps in the manifest differ).
5. **Self-describing.** Schema version, platform version, options, counts and included domains are
   recorded; the README explains the layout and governance semantics.

## Layout

All paths are inside a top-level `customer-export/` directory. `<brand>` is the brand slug.

```
customer-export/
├── manifest.json                     export metadata + SHA-256 of every file
├── README.md                         human-readable guide, verification snippet
├── documentation/data-dictionary.json
├── customer/profile.json             organization profile
├── brand/
│   ├── brand.json                    brands
│   ├── versions/<brand>/versions.json        published, checksummed snapshots
│   ├── foundation/<brand>/entries.json
│   ├── visual-identity/<brand>/
│   │   ├── entries.json  palettes.json  colors.json  typography.json
│   │   ├── tokens.css                CSS custom properties
│   │   └── tokens.dtcg.json          W3C Design Tokens format
│   ├── art-direction/<brand>/entries.json
│   ├── aesthetic-language/<brand>/{entries,concepts}.json
│   ├── design-language/<brand>/{entries,design-tokens}.json
│   ├── brand-language/<brand>/entries.json
│   └── guidelines/<brand>/{entries,principles,guidelines,revisions}.json
├── assets/
│   ├── metadata/<asset-id>.json      asset record + tags, segments, derivatives, external refs
│   ├── metadata/_external_references.json
│   ├── originals/<asset-id>/<original filename>
│   ├── derivatives/<asset-id>/<kind>-<derivative-id>.<ext>
│   └── collections/collections.json
├── projects/projects.json
├── relationships/relationships.json  edges whose two ends are both in the export
├── ai-knowledge/
│   ├── asset-analyses.json           interpretations with provider, model, prompt version, status
│   ├── suggestions.json  reviews.json  prompt-templates.json  context-packages.json
│   └── task-context.{json,md}        selective exports with a task type only
└── embeddings/
    ├── README.json                   which models/dimensions are included (if any)
    └── <modality>-<model>-<dims>.jsonl
```

Domain directories appear only for the domains included in the export.

## `manifest.json`

| Field | Meaning |
|---|---|
| `format` | always `brand-dna-library-export` |
| `schema_version` | data schema version; imports refuse newer versions |
| `platform_version` | version of the exporting platform |
| `export_id`, `export_date` | identity and UTC timestamp |
| `export_mode` | `full` or `selective` |
| `customer_id`, `customer_slug` | the one customer this export belongs to |
| `brand_ids`, `brand_versions` | exported brands and their current published version numbers |
| `included_domains` | knowledge domains included |
| `selection` | selective exports: brand, domains, assets, collections, project, task type |
| `export_options` | `include_originals`, `include_derivatives`, `include_embeddings`, `include_ai_knowledge`, `include_pending` |
| `counts` | records per kind (principles, assets, relationships …) |
| `asset_count`, `file_count`, `binary_file_count` | totals |
| `embeddings` | per file: modality, model, dimensions, provider, count |
| `tenant_purity_check` | documents scanned and result |
| `checksum_algorithm`, `checksums` | `sha256` and a map `path → hex digest` for every file except the manifest |

## Semantics

* **Governance.** On principles, guidelines, concepts and entries, `status = approved` means a
  person approved it; `approved_by`/`approved_at` record who and when. `revisions.json` holds
  every saved version. By default a full export includes drafts and pending items
  (`include_pending: true`) so nothing is lost; a selective export defaults to approved (and
  deprecated) items only.
* **AI output is labelled.** `asset-analyses.json` entries are interpretations with
  `objective` and `interpretive` parts, `status` (`pending_review`, `approved`, `rejected`,
  `superseded`), provider, model, prompt key/version and confidence. An asset's accepted
  interpretation is referenced by its `approved_analysis_id`.
* **Measurements vs interpretation.** `assets/metadata/*.json` → `media_metadata` holds objective
  machine measurements (dimensions, duration, palette, scenes, camera movement, page count …).
* **Embeddings are model-specific.** They are optional and only meaningful for the exact model
  and dimensionality listed; the importer regenerates them by default.

## Verifying an export

```bash
unzip export.zip && cd customer-export
python3 - <<'PY'
import hashlib, json, pathlib
m = json.load(open("manifest.json"))
bad = [p for p, h in m["checksums"].items() if hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() != h]
extra = {str(p) for p in pathlib.Path(".").rglob("*") if p.is_file()} - set(m["checksums"]) - {"manifest.json"}
print("OK" if not bad and not extra else f"mismatch: {bad} unexpected: {sorted(extra)}")
PY
```

## Importing

`POST /v1/imports` (or Exports & imports → Upload in a workspace):

1. **Stage and validate**: safe extraction (no absolute paths or `..`), `format` and
   `schema_version`, every checksum, no files outside the manifest; assets exported without their
   original file and content already present in the workspace are reported. The result is a
   report (errors, warnings) and a preview (brands, counts, domains, duplicates).
2. **Choose**: for each source brand `create` a new brand or `merge:<target brand id>`; skip
   duplicate assets (same content hash) or not; import AI knowledge or not; keep approvals or
   import everything as drafts; regenerate embeddings (default).
3. **Commit**: one database transaction. IDs are remapped to new ones, so the same export can be
   imported into any workspace; originals are copied into the target workspace's storage
   namespace and re-verified. On any error nothing is written and the report lists why.
4. **Re-index**: embeddings are regenerated for the target brands in the background.

Staging files are removed after commit or discard, and abandoned uploads are cleaned up by the
worker.
