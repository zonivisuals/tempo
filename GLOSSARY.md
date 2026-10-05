# Glossary

The domain language for Tempo lives in [`docs/agents/domain.md`](docs/agents/domain.md).
Read that file; this pointer exists because tooling looks for `GLOSSARY.md` at the
repository root.

Decision records live in [`docs/decisions/`](docs/decisions/). `docs/adr/README.md`
is a pointer to the same directory.

## The short version

| Term | Means |
|---|---|
| **content id** | `sha1(size + first 4 MiB + last 4 MiB)[:16]`. Keys the engine library. Two paths holding the same bytes get the same id |
| **footage key** | First 10 hex chars of `sha1(resolved_path)`. Keys the sidecar registry. A path's identity, not the file's |
| **signature** | Hash of pipeline version, models, and indexing parameters. Decides whether a library index is `ready` or `stale` |
| **stage** | One unit of pipeline work (`shots`, `visual`, `transcribe`, `ocr`, `captions`, `text`, `index`). Cached by a hash of its inputs |
| **shot** | A scene between two cuts. The unit every retrieval key is built from |
| **retrieval key** | One searchable representation of a shot: visual, dialogue, caption, bm25, entity, anchor. Six of them, fused by weight |
| **library** | The engine's content-addressed store, `library/<content_id>/` |
| **handoff** | The sidecar's whole engine interaction for one footage: library hit, or upload, index, poll, thumbs |
| **contract entry point** | One of the three `host.jsx` globals the panel may call. Everything else in `host.jsx` is internal |
| **reused** | A footage whose content id already has a `ready` index. No upload, no GPU work |
