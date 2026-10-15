# 0007 — Immutable originals in object storage, served by short-lived signed URLs

**Status:** Accepted

## Context

Originals must be preserved byte-for-byte (the brief: "preserve original media"), files are
large, and URLs must not become a side door into another customer's library.

## Decision

* Storage backends: local filesystem (development, single host) and S3-compatible (S3, R2,
  MinIO). Keys are `orgs/<org>/brands/<brand>/assets/<asset>/original/<file>` and
  `…/derivatives/<kind>/…`; `TenantStorage` refuses keys outside its organization prefix.
* Originals are written **create-only** (S3 `If-None-Match: *`), their SHA-256 is stored, and
  exports re-verify it. Processing only ever writes derivatives (thumbnails, previews,
  keyframes, page renders, proxies).
* Browsers receive **short-lived signed URLs** (default 15 minutes) generated only after the API
  authorized the request in the tenant session. For S3 they are presigned for the public
  endpoint (`BDNA_S3_PUBLIC_ENDPOINT_URL`); for local storage they are HMAC-signed `/v1/files/…`
  tokens that encode key, expiry and disposition.
* Downloading an original needs `assets.download_original`; previews need only `assets.read`.

## Consequences

* Leaked URLs expire quickly; buckets stay private.
* Re-processing never risks the original. Deleting an asset is a soft delete that can be
  restored; files are removed when the customer's data is purged.
