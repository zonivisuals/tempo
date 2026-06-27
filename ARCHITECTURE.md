# Tempo Architecture

Semantic video search plugin for Adobe Premiere Pro.  
Hybrid edge + cloud architecture using Google Colab for ML and a UXP plugin for the Premiere panel.

---

## 1. Overview

Tempo enables NLP-based search across video footage directly inside Premiere Pro. Users index their footage through an AI pipeline (scene detection, visual embeddings, speech transcription, face recognition) and then search using natural language queries — all from a dockable panel.

The system is split into two decoupled components:

| Component | Role | Technology |
|---|---|---|
| **UXP Plugin** | Premiere panel UI, local search fallback, Premiere DOM integration | JavaScript (UXP), HTML, CSS |
| **Colab ML API** | Heavy AI processing: CLIP, Whisper, InsightFace, FAISS | Python (FastAPI), ngrok |

---

## 2. Design Decisions

### 2.1 Hybrid Edge + Cloud Architecture

**Decision:** Lightweight operations run in the UXP plugin; all ML inference runs in the cloud on Colab.

**Rationale:**
- Uploading raw video footage to the cloud is slow and bandwidth-heavy (hours of 4K footage can be 100s of GB)
- ML models (CLIP, Whisper, InsightFace) require GPU acceleration — free cloud GPU (Colab T4) is preferable to requiring users to have a powerful local GPU
- The UXP runtime cannot extract video frames or run Python ML libraries, making local ML infeasible
- Day-to-day search queries are lightweight (text comparison) and can fall back to local TF-IDF when the cloud is unavailable

**Tradeoff:** Indexing new footage requires an active Colab session. Mitigated by caching the index locally for offline search.

### 2.2 Google Colab as ML Backend

**Decision:** The existing `tempo_pipeline.ipynb` is wrapped as a FastAPI server exposed via ngrok.

**Rationale:**
- Free T4 GPU eliminates cloud hosting costs
- The existing pipeline already implements all required stages (scene detection → CLIP → Whisper → InsightFace → FAISS)
- FastAPI provides clean REST endpoints for the plugin to consume

**Constraints:**
- Colab sessions idle-timeout after ~90 minutes and max out at 12 hours
- ngrok URL changes on every session restart
- The notebook requires manual trigger (user runs it in Colab)

**Mitigations:**
- FAISS index is exported to Google Drive for persistence across sessions
- The exported index can be downloaded by the plugin for local fallback search
- The plugin allows manual ngrok URL entry in settings

### 2.3 UXP Plugin as the Only Client Component

**Decision:** No companion app (Python CLI, Electron, etc.). The UXP plugin is the sole client.

**Rationale:**
- Zero-install for users — everything lives inside the Premiere panel
- Simplifies distribution (single `.ccx` package)
- UXP supports `require()` for modular JS, `fetch()` for network, and `localFileSystem` for file storage

**Constraint:** UXP cannot extract video frames, decode audio, or run Python. All footage processing must happen server-side (Colab).

### 2.4 Manual Colab Connection

**Decision:** Users copy the ngrok URL from their Colab session and paste it into the plugin's settings dialog.

**Rationale:**
- The ngrok URL is ephemeral and changes per session — no fixed endpoint exists
- Auto-discovery (scanning Google Drive, relay endpoints) adds complexity and failure points
- Manual entry is simple, transparent, and reliable

### 2.5 Remote Query Embedding

**Decision:** Search queries are sent to the Colab API for MiniLM embedding and FAISS search.

**Rationale:**
- MiniLM is a GPU-accelerated transformer that cannot run in UXP
- Colab's cascade search (visual → face → text) requires the FAISS indices which live in the cloud
- Produces the most accurate results

**Fallback:** When Colab is offline, the plugin uses local TF-IDF matching on cached transcript data. Less accurate but fully offline.

### 2.6 Plugin Manifest v5 with Explicit Permissions

**Decision:** All permissions are declared explicitly in `manifest.json` following least-privilege principle.

**Rationale:**
- UXP denies any undeclared permission by default
- Users are prompted for consent, building trust
- Avoids runtime failures from missing permissions

---

## 3. System Architecture

```
+---------------------------+     +------------------------------+
|   Adobe Premiere Pro      |     |   Google Colab Session       |
|                           |     |                              |
|   +-------------------+   |     |   +----------------------+   |
|   | Tempo Panel       |   |     |   | FastAPI Server        |   |
|   | (UXP Plugin)      |   |     |   |                      |   |
|   |                   |   |     |   |  POST /health        |   |
|   |  +-------------+  |   |     |   |  POST /search        |   |
|   |  | Search Bar   |  |   |     |   |  POST /index        |   |
|   |  +-------------+  |   |     |   |                      |   |
|   |  | Results List |  |   |     |   |  +--------------+   |   |
|   |  +-------------+  |   |     |   |  | CLIP         |   |   |
|   |  | Settings     |  |   |     |   |  | Whisper      |   |   |
|   |  +-------------+  |   |     |   |  | InsightFace  |   |   |
|   |                   |   |     |   |  | MiniLM       |   |   |
|   |  Modules:         |   |     |   |  | FAISS        |   |   |
|   |  api.js           |<--+-----+-->|  +--------------+   |   |
|   |  search.js        |   |  HTTPS |  |                   |   |
|   |  premiere.js      |   |     |   |  +--------------+   |   |
|   |  storage.js       |   |     |   |  | Google Drive |   |   |
|   |  ui.js            |   |     |   |  | (export idx) |   |   |
|   |  settings.js      |   |     |   |  +--------------+   |   |
|   +-------------------+   |     |   +----------------------+   |
+---------------------------+     +------------------------------+
                                           |
                                   +-------+
                                   |
                           +-------------------+
                           |  ngrok Tunnel     |
                           |  (ephemeral URL)  |
                           +-------------------+
```

---

## 4. Components

### 4.1 UXP Plugin (`Test-ev2i56/`)

A dockable panel in Premiere Pro that provides the search interface.

**Entrypoints:**
- **Panel** (`samplePlugin`): The main search interface — search bar, results list, status indicators
- **Command** (`show_alert`): Diagnostic command (retained from scaffold)

**Manifest:**
- `manifestVersion: 5` (required for Premiere)
- `host.app: "premierepro"`, `minVersion: "25.6.4"`
- `requiredPermissions.network.domains`: Allowlisted Colab/ngrok domains
- `requiredPermissions.localFileSystem: "request"`: File picker for index download
- `featureFlags.enableAlerts: true`: For diagnostic alerts

**Modules:**

| Module | File | Responsibility |
|---|---|---|
| `api.js` | `js/api.js` | HTTP client for Colab API (health, search, index) |
| `search.js` | `js/search.js` | Local TF-IDF fallback search on cached transcripts |
| `premiere.js` | `js/premiere.js` | Premiere DOM integration (project items, markers, navigation) |
| `storage.js` | `js/storage.js` | Sandbox file operations (read/write index, settings persistence) |
| `ui.js` | `js/ui.js` | DOM creation, theme awareness, component builders |
| `settings.js` | `js/settings.js` | Settings modal dialog (Colab URL, preferences) |

**UI Components (Spectrum UXP built-in):**
- `<sp-textfield>` — Search input
- `<sp-button>` — Search trigger, settings button
- `<sp-divider>` — Section separators
- `<sp-heading>`, `<sp-body>` — Typography
- `<dialog>` — Settings modal (via `uxpShowModal()`)

**Styling:**
- Flexbox layout (CSS Grid unavailable in UXP)
- Theme-aware classes (`theme-dark`, `theme-light`)
- No CSS custom properties (`--uxp-host-text-color` unsupported)

### 4.2 Colab ML API (`tempo_pipeline.ipynb`)

The existing Jupyter notebook wrapped as a FastAPI server.

**Endpoints:**

| Endpoint | Method | Input | Output |
|---|---|---|---|
| `/health` | GET | — | `{ "status": "ok", "indexed_clips": n }` |
| `/search` | POST | `{ "query": "text" }` | `{ "results": [{ "clip_id", "scene_id", "score", "transcript", "timecode" }] }` |
| `/index` | POST | Media files via Drive | `{ "status": "indexing", "export_path": "..." }` |

**Pipeline Stages (in order):**
1. Scene detection (scenedetect, ContentDetector, threshold=27.0)
2. CLIP visual embeddings (ViT, 512-dim)
3. Whisper transcription (small, translate mode)
4. MiniLM text embeddings (384-dim)
5. InsightFace face recognition (buffalo_l, 512-dim)
6. FAISS indexing (IndexFlatIP for visual, text, face)
7. Cascade search: visual (top-50) → face filter → text rerank

**Storage:**
- FAISS index + metadata exported to Google Drive as JSON
- Index includes: clip mapping, scene boundaries, transcripts, timestamps, face data

---

## 5. Data Flows

### 5.1 Indexing Flow

```
User                    Plugin                  Colab                     Google Drive
 |                       |                       |                           |
 |  1. Upload footage    |                       |                           |
 |  to Google Drive      |                       |                           |
 |---------------------->|                       |                           |
 |                       |                       |                           |
 |  2. Start Colab       |                       |                           |
 |  session, run         |                       |                           |
 |  pipeline notebook    |                       |                           |
 |                       |                       |                           |
 |  3. Enter ngrok URL   |                       |                           |
 |  in plugin settings   |                       |                           |
 |---------------------->|                       |                           |
 |                       |  4. POST /health      |                           |
 |                       |---------------------->|                           |
 |                       |  { "status": "ok" }   |                           |
 |                       |<----------------------|                           |
 |                       |                       |                           |
 |  [User triggers       |                       |                           |
 |   indexing in Colab]  |                       |  5. Read footage          |
 |                       |                       |-------------------------->|
 |                       |                       |  6. Return keyframes,     |
 |                       |                       |     audio extracts        |
 |                       |                       |<--------------------------|
 |                       |                       |                           |
 |                       |                       |  7. Run pipeline:         |
 |                       |                       |     scenedetect → CLIP    |
 |                       |                       |     → Whisper → MiniLM    |
 |                       |                       |     → InsightFace → FAISS |
 |                       |                       |                           |
 |                       |                       |  8. Export index          |
 |                       |                       |-------------------------->|
 |                       |                       |     (index.json)          |
 |                       |                       |                           |
 |                       |  9. POST /search      |                           |
 |                       |  (test query)         |                           |
 |                       |---------------------->|                           |
 |                       |  results array        |                           |
 |                       |<----------------------|                           |
```

### 5.2 Search Flow (Online — Colab connected)

```
User                      Plugin                    Colab
 |                         |                         |
 |  1. Type query          |                         |
 |  in search bar          |                         |
 |------------------------>|                         |
 |                         |                         |
 |                         |  2. POST /search        |
 |                         |  { "query": "..." }     |
 |                         |------------------------>|
 |                         |                         |
 |                         |  3. MiniLM embed query   |
 |                         |  4. FAISS cascade search |
 |                         |  5. Rerank results       |
 |                         |                         |
 |                         |  6. Results JSON         |
 |                         |<------------------------|
 |                         |                         |
 |  7. Display results     |                         |
 |  in panel list          |                         |
 |<------------------------|                         |
 |                         |                         |
 |  8. Click result        |                         |
 |------------------------>|                         |
 |                         |  9. Call Premiere API:   |
 |                         |     navigate to scene   |
 |                         |     add marker          |
```

### 5.3 Search Flow (Offline — Colab disconnected)

```
User                      Plugin
 |                         |
 |  1. Type query          |
 |------------------------>|
 |                         |
 |                         |  2. Check Colab health → timeout/fail
 |                         |
 |                         |  3. Load cached index from plugin-data:/
 |                         |
 |                         |  4. Run TF-IDF on cached transcripts
 |                         |
 |  5. Display results     |
 |<------------------------|
```

---

## 6. Constraints & Risks

| Constraint | Impact | Mitigation |
|---|---|---|
| Colab session timeout (12hr max, ~90min idle) | API unavailable for search | Local TF-IDF fallback; re-index requires new session |
| ngrok URL changes per session | Plugin can't auto-connect | Manual URL entry in settings |
| UXP cannot extract video frames | All processing must go through Colab | Drive-based media sharing |
| UXP has no CSS Grid | Layout must use Flexbox | All UI built with Flexbox |
| UXP `hide()`/`destroy()` unreliable | Can't rely on cleanup hooks | All setup in `show()` |
| `entrypoints.setup()` can only be called once | All entrypoints in single call | Single setup() in index.js |
| No `TextDecoder` in UXP | Can't stream HTTP responses | `response.json()` for all API calls |
| Network domains must be allowlisted | API calls fail if domain not in manifest | Wildcard or specific ngrok domain pattern |

---

## 7. Future Considerations

| Topic | Approach |
|---|---|
| **Persistent cloud endpoint** | Migrate from Colab to Modal / Replicate / Vertex AI for always-on API |
| **Real-time frame extraction** | Premiere SDK or C++ addon for local frame capture from timeline |
| **Face search refinement** | Named face database with persistent embeddings across projects |
| **Bulk project scanning** | Auto-index all footage in active project with one click |
| **Collaborative search** | Shared FAISS index across team members via cloud storage |
| **SWC UI** | Migrate from built-in Spectrum widgets to SWC for richer components (requires bundler) |
