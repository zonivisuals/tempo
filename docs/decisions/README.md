# docs/decisions — Architecture Decision Records

Index of decisions (details in AGENTS.md §12). New decisions get a numbered file here (`NNNN-slug.md`).

- D1 CEP panel + host.jsx + Python sidecar → `0001-ae-uxp-watch.md`
- D2 Polling for project sync (no CEP push events in AE)
- D3 Dense scoring via matmul, FAISS parked — superseded by D17
- D4 No context hint in caption prompts (hint caused transcript echo)
- D5 Shared entity extractor on query + shots (junk-entity poisoning guard)
- D6 Thumbnails over HTTP (avoids CEF file-access flags)
- D7 Stale-by-default pruning (re-indexing is expensive)
- D8 Single-GPU lazy per-stage model loading (revived on the engine)
- D9 Colab-hosted pipeline → `0002-colab-remote-pipeline.md` (superseded by D11)
- D10 Drive auto-upload on AE import → `0003-drive-auto-upload.md` (transport superseded by D16)
- D11 Modal backend behind the backend seam → `0004-modal-backend.md` (superseded by D15)
- D12 Identity removed → `0005-identity.md`
- D13 Storage providers, raw retention → `0006-storage.md` (transport superseded by D16; retention kept)
- D14 Plans, entitlements, release gates → `0007-launch-gates.md` (free footage 1→3 by `0010-free-tier-3-footage.md`)
- D15 Brev L4 engine behind the backend seam → `0008-brev-engine.md`
- D16 Content-addressed cache (path → content id → stage cache) → `0008-brev-engine.md`
- D17 v4 pipeline + z-score fusion + FAISS candidates → `0009-v4-pipeline.md`
- D18 Figma-derived panel UI: motion allowed under a budget, dimensions re-derived for panel scale, Tempo ships its own two themes → `0011-figma-panel-ui.md`
- D19 Wordmark header: the real `tempo_logo` replaces the navbar text mark, the state labels become the dot's legend → `0012-wordmark-header.md`
- D20 Search field scaled by type (0.406), not frame geometry: spacing re-derived to a 107px field, `--r-field` split from `--r-lg`, `Search for anything` kept, header hairline dropped → `0013-search-field-scale-and-spacing.md`
- D21 Grid card body is two columns (description left and centred, duration + name right on the bottom edge); the list body keeps the design's single caption + duration row  → `0014-grid-card-body-columns.md`
- D22 Panel chrome re-derived: the search field 107→82px, the magnifier 21→10px (the one export below §6's 16px floor), the view pair's chips touching, the insert badge is the accent at a share of the thumbnail, the thumbnail takes `--r-md`, and `--edge` is a 180° ramp → `0015-panel-chrome-re-derived.md`
- D23 The searching frame is `loading_result` and nothing else: no card stroke or fill, both blocks on `--r-md` and inset by that stroke, the sweep's level is the design's 0.08 on both blocks in one token, and the cap is the body box rather than the design's type-driven 69 → `0016-searching-frame-two-blocks.md`


Known debt:
- K1 key-scale calibration — resolved by D17
- K2 inherited-caption ties — reduced by `caption_conf`
- K3 serialized single-GPU worker
- K4 instance uptime
- K5 upload bandwidth over the port-forward
- K6 engine library pruning
