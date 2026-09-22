# 0006 — Storage providers, presigned uploads, raw retention

**Status:** accepted. **Date:** 2026-09-22.

## Context

Indexing needs footage bytes on the backend; the manual Drive copy proved
the flow but cannot ship. Requirements: no new cards to start, presigned
direct uploads (bytes never proxy through our servers), real byte progress
in the existing `upload` stage, and a locked retention call (delete raw
post-index). Any SigV4 code must be verifiable without trusting memory.

## Decision

- **Provider seam:** `service/tempo_service/storage/` (`base.py` ABC,
  `S3Backend`, `get_storage` factory). `provider="none"` (default) keeps
  today's manual-copy behavior; `"s3"` + endpoint/bucket/credentials
  enables uploads. Unknown names raise; incomplete credentials fall back
  with a warning — never a silent stall.
- **SigV4 in stdlib** (`storage/s3.py`): presigned PUT/GET/DELETE per the
  AWS SigV4 spec, path-style `/bucket/key`, `UNSIGNED-PAYLOAD`. No boto3
  dependency; **byte-parity against botocore is asserted in tests**
  (frozen clock), so signing behavior cannot drift silently. boto3 itself
  is a test-only dev dependency (never imported by the service).
- **Day-zero store: Modal Volumes** (in-stack, 1 TiB free, no card):
  sidecar uploads through the Modal endpoint until presigned flow lands.
- **Step-up store: Backblaze B2** (S3-compatible, 10 GB free, no card at
  signup, egress free to 3× stored). R2 later, when cards are acceptable
  and egress dominates.
- **Upload wiring:** proxy streams the registry's local file through
  `upload_file` with per-chunk `progress("upload", done, total)` — the
  first honest byte progress this stage has ever shown. Missing local
  file errors before any handoff.
- **Retention (locked): delete raw post-index.** After job `done`, the
  worker deletes the raw key; delete failure warns but never fails
  indexed work. `storage_retention=keep` exists only for debugging.

## Consequences

- `upload` stage finally means bytes sent. Panel/progress code unchanged.
- R2 migration later = endpoint + credentials, no code changes.

## Revisit when

Egress bills appear (→ R2), or resumable multipart is needed for
multi-GB studio files (→ multipart presign + part tracking).
