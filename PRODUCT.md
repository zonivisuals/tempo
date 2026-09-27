# PRODUCT.md — Tempo for After Effects

## Vision

Tempo is a semantic search engine for footage inside After Effects. Editors with long video files (interviews, vlogs, rushes, documentaries) index them once, offline, then type natural language ("vending machine", "japan road trip") in a docked panel and get ranked shots with thumbnails, timecodes, and a transparent *why-it-matched* breakdown. One click places the exact range on the timeline at the playhead, trimmed and ready for fine-tuning.

## What it is / is not

- Is: dense local tool — fast, offline, transparent, undo-safe.
- Not: generative-AI gimmick, chat interface, cloud product.

## Design principles (binding, see AGENTS.md §1)

1. Every click does exactly one obvious thing. No hidden modes.
2. All project mutations are undoable (single undo group per action).
3. Never block the AE UI. Never block the panel UI.
4. Every score shown is decomposable — no black-box ranking.
5. Efficiency first: indexing is expensive and cached; searching is milliseconds.

## Scope — MVP = F1–F5 core, F6 minimal

- **F1 Automatic footage indexing:** import in AE → `uploading` (direct to the engine, byte progress, resumable) → `indexing` (Brev L4 engine stages) → searchable. Zero clicks. Fingerprint `(path, size, mtime_ns)`; added/changed auto-enqueue, removed → stale, unchanged → skip. Same content anywhere (moved, copied, other project) → ready instantly from the engine library. Explicit prune only.
- **F2 Fast search + preview:** Enter submits (proxied to the engine); cards show keyframe, footage name, comp-fps timecode range, duration, transcript snippet, caption, and one Insert action. Footage filter dropdown when >1 footage. Thumbs render from the local cache instantly; results arrive on engine time with a timeout and inline error codes.
- **F3 Skeleton loading:** `top_k` flat gray blocks (thumb + two lines), opacity pulse only; ≥200 ms min display; inline "no results" / compact error with code — never a modal.
- **F4 Step-based progress:** per-stage pending → running (`done/total` real units: bytes, frames, audio seconds, keyframes, reps) → done; error shows stage + message. No fake progress. Detail collapses behind an eye toggle once indexing is done or a search runs; the one-line summary stays.
- **F5 Open at exact timestamp:** one click → resolve/import footage, target active comp (or create `Tempo — <basename>`), place layer (`startTime = T - start_s`, `inPoint = T`, `outPoint = T + dur`), playhead to shot start, select layer, single undo removes all.
- **F6 Look & feel (minimal in MVP):** AE-native dense gray flat; 1px borders, radius ≤ 2px, 4px rhythm, 12px/11px system font, mono + one accent, thin bars. Full polish later.

## Plan — one phase per commit (P0–P10 done; B1–B9 Brev migration)

- **P0** repo memory + contracts (this file, AGENTS.md, `docs/api.md`, decisions, `.gitignore`).
- **P1** service skeleton (config, schemas, app + `/health`).
- **P2** registry + jobs + sync/footage endpoints.
- **P3** indexing pipeline (shots → build_index, 9 stages).
- **P4** search + thumbs (golden-tested scoring).
- **P5** CEP panel (manifest, host.jsx, www).
- **P6** tests + smoke checklist + screenshot gate.
- **P7** Colab pivot spec: ADR-0002 (remote pipeline) + ADR-0003 (Drive auto-upload) + contract updates.
- **P8** Colab shim (FastAPI cell, ngrok, Drive checkpoints, token auth).
- **P9** local proxy (Drive uploader, Colab client, thumb sync, panel settings; delete `indexer/`).
- **P10** free-tier trial: import clip → untouched chain, timings + VRAM, golden parity.
- **B1** Brev spec: ADR-0008 (engine, tunnel, content cache) + ADR-0009 (v4 pipeline, z-score fusion) + contract v2.
- **B2** engine v4 pipeline with stage cache.
- **B3** v4 fusion search with FAISS candidates (golden + parity).
- **B4** engine HTTP API, content library, resumable uploads.
- **B5** Brev L4 compose deploy.
- **B6** sidecar content-addressed handoff over the brev tunnel.
- **B7** remove Modal backend, v3 indexer, storage seam.
- **B8** panel: collapsible indexing view, v4 stage labels.
- **B9** CI gates for the engine, release docs.

## Legacy note

Branch `vid-ind-api` is a cloud SaaS prototype (Hono/Qdrant/BullMQ/Modal) — reference only. `tempo_pipeline_v4.ipynb` (gitignored) is the behavioral reference for the pipeline, scoring, captions, and NER; `engine/` ports it cleanly and never imports it. v3 is retired.
