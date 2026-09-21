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
- D9 Colab-hosted pipeline, local service as proxy → `0002-colab-remote-pipeline.md`
  (D8's local-GPU assumption superseded; `indexer/` deleted in P9 per §8)
- D10 Drive auto-upload on AE import → `0003-drive-auto-upload.md`
  (deterministic `tempo/<key>/<basename>`, `uploading` + `queued-for-colab` states)

Known debt: K1 key-scale calibration, K2 inherited-caption ties, K3 serialized single-GPU worker.
- **K4 Tunnel churn + free-tier preemption:** ngrok URL per session (panel setting);
  Colab death mid-index resumes from Drive checkpoints; search needs Colab alive.
- **K5 Upload bandwidth:** Drive upload is the first-leg bottleneck; measured in P10 trial.
