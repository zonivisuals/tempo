# AGENTS.md

## Project Overview

**Tempo** — Adobe Premiere Pro plugin for semantic video search. Passes footage through an AI pipeline (scene detection, CLIP embeddings, Whisper transcription, face recognition, FAISS search) and provides NLP-based search inside Premiere.

## Repository Structure

```
tempo/
├── tempo_pipeline.ipynb    ← AI pipeline (Python, Colab). Processes video → embeddings + FAISS index
├── Test-ev2i56/            ← UXP plugin scaffold (Premiere panel + command)
│   ├── manifest.json       ← Plugin config: id "Test-ev2i56", host "premierepro" v25.6.4
│   ├── index.js            ← Panel/command entrypoints (entrypoints.setup)
│   ├── package.json
│   └── README.md
└── PLUGIN.md               ← Full UXP development reference (read this before writing plugin code)
```

## Development Workflow

### Plugin Development (UXP)

1. Enable Developer Mode in Premiere: Settings → Plugins → "Enable developer mode" → Restart
2. Open UXP Developer Tool (UDT v2.2+)
3. Click "Add Plugin" → select `Test-ev2i56/manifest.json`
4. Click "Load & Watch" — plugin loads in Premiere, auto-reloads on code changes
5. Manifest changes require manual unload + reload in UDT

**Key constraint:** `entrypoints.setup()` can only be called once per plugin.

### Pipeline Development (Python)

The pipeline runs in Colab or locally. Key dependencies:
```
openai-whisper, scenedetect, transformers, torch, sentence-transformers, faiss-cpu, insightface, onnxruntime, spacy, moviepy
```

Pipeline stages: scene detection → CLIP visual embeddings → Whisper transcription → MiniLM text embeddings → face recognition (insightface) → FAISS indexing → cascade search (visual → face filter → text rerank).

## UXP Plugin Rules (read PLUGIN.md for full reference)

- **Manifest version:** 5 (required for Premiere)
- **Not a browser:** CSS Grid unavailable, `TextDecoder` unavailable, many web APIs missing
- **Permissions:** All network/filesystem/shell access must be declared in `manifest.json`. Undeclared = denied.
- **Theme awareness:** Use `document.theme.getCurrent()` + `document.theme.onUpdated` to adapt to Light/Dark/Darkest
- **Modal dialogs:** Use `<dialog>` + `uxpShowModal()`. Handle `"reasonCanceled"` (Esc/title bar close)
- **`hide()`/`destroy()` hooks:** Unreliable in Premiere — use `show()` for setup instead
- **Spectrum widgets:** Built-in (`<sp-button>`, `<sp-textfield>`, etc.). SWC requires npm install + bundler + `enableSWCSupport` flag
- **Inline event handlers:** Require `allowCodeGenerationFromStrings: true` permission
- **`alert()`/`confirm()`/`prompt()`:** Require `enableAlerts: true` feature flag

## Current Plugin State

The plugin (`Test-ev2i56/`) is a basic scaffold with:
- One panel entrypoint (`samplePlugin`) with theme-aware styling
- One command entrypoint (`show_alert`) using `alert()`
- No filesystem, network, or IPC permissions yet
- Plugin ID: `Test-ev2i56`, name: `tempo`
