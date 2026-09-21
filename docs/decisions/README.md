# docs/decisions — Architecture Decision Records

Index of decisions (details in AGENTS.md §12). New decisions get a numbered file here (`NNNN-slug.md`).

- D1 CEP panel + host.jsx + Python sidecar → `0001-ae-uxp-watch.md`
- D2 Polling for project sync (no CEP push events in AE)
- D3 Dense scoring via matmul, FAISS parked (scale path >~100k shots, behind flag, with index mapping)
- D4 No context hint in BLIP-2 prompts (hint caused transcript echo)
- D5 Shared `_extract_entities` on query + shots (junk-entity poisoning guard)
- D6 Thumbnails over HTTP (avoids CEF file-access flags)
- D7 Stale-by-default pruning (re-indexing is expensive)
- D8 Single-GPU lazy per-stage model loading (8–12GB VRAM)

Known debt: K1 key-scale calibration, K2 inherited-caption ties, K3 serialized single-GPU worker.
