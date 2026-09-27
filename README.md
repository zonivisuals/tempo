# Tempo

Semantic search for footage inside After Effects. Type what you're looking for ("vending machine at night", "road trip to Akita"), get the matching shots with thumbnails and timecodes, and click one to drop that exact range on your timeline.

## How it works

```
After Effects panel ──► local sidecar (127.0.0.1:8765) ──► GPU engine (NVIDIA Brev L4)
   search, results        registry, uploads, thumbs          indexing + search
```

- **Panel** (`panel/`): the CEP extension docked in After Effects. It lists project footage, shows indexing progress, runs searches, and inserts clips.
- **Sidecar** (`service/`): a small local Python service. It notices new footage, uploads it, tracks progress, and caches thumbnails. It holds no AI models.
- **Engine** (`engine/`): runs every AI model on a GPU instance. It indexes footage and answers searches.

## The AI workflow

### Indexing (once per video)

Every video goes through seven stages on the GPU:

| Stage | What happens | Model |
|---|---|---|
| **Shots** | Cuts the video into shots (long takes split at 8 s) and saves 3 frames per shot | PySceneDetect |
| **Visual** | Turns each shot's frames into an image embedding | SigLIP 2 |
| **Speech** | Transcribes the audio with word timings, and translates it to English if needed | faster-whisper large-v3 |
| **OCR** | Reads on-screen text (titles, subtitles, signs) | EasyOCR |
| **Captions** | Groups similar shots and writes a description for one shot per group; every shot borrows the closest description | Florence-2 |
| **Text** | Finds names and places, tags emotions, embeds the dialogue and captions | BERT NER, emotion classifier, bge-base |
| **Index** | Saves everything plus small thumbnails | — |

Each shot ends up with three searchable "keys": what it **looks like** (visual), what is **said** around it (dialogue), and what it **shows** in words (caption).

### Search

A query is scored against every shot with six signals, then added up:

| Signal | Weight | Meaning |
|---|---|---|
| Visual | 0.35 | Query text vs. shot image (SigLIP 2) |
| Dialogue | 0.25 | Query vs. what is said around the shot (bge) |
| Caption | 0.15 | Query vs. the shot's description (bge) |
| Keywords | 0.15 | Exact word matches (BM25) |
| Entity | 0.10 | Names and places in the query found in the shot (typos tolerated: "jhon" → "John") |
| Anchor | 0.05 | Shots that look like the ones where a named entity appears |

Each signal is normalised first, so image matches and text matches compete fairly. Only one result is returned per scene, and every result carries its score breakdown. FAISS keeps search fast on large libraries.

### Nothing is indexed twice

- **Same file, same place:** skipped.
- **Same video anywhere else** (moved, renamed, copied, another project): recognised by its contents and ready instantly, with no upload and no GPU work.
- **Interrupted indexing:** resumes from the last finished stage.
- **Interrupted upload:** resumes from the last byte received.

## Setup

You need Windows with After Effects (2019–2025), Python 3.11+, WSL (Ubuntu), and an NVIDIA Brev account.

### 1. Deploy the engine on Brev

1. In the [Brev console](https://brev.nvidia.com), create an instance: GPU **L4**, name **`tempo-l4-instance`**, disk 200 GB or more.
2. In WSL, install the Brev CLI and log in:
   ```bash
   bash -c "$(curl -fsSL https://raw.githubusercontent.com/brevdev/brev-cli/main/bin/install-latest.sh)"
   brev login
   brev refresh
   ```
3. Deploy (builds the engine, downloads the models, checks the GPU):
   ```bash
   export TEMPO_REPO_URL=https://github.com/zonivisuals/tempo.git
   bash engine/deploy/brev-deploy.sh
   ```
4. Copy the engine token it generated:
   ```bash
   brev exec tempo-l4-instance "grep TOKEN /home/ubuntu/workspace/tempo-src/engine/deploy/.env"
   ```

### 2. Run the sidecar (PowerShell)

```powershell
pip install ./service
$env:PYTHONPATH = "service"
$env:TEMPO_BREV_INSTANCE = "tempo-l4-instance"
$env:TEMPO_BREV_CLI = "wsl brev"
$env:TEMPO_BACKEND_TOKEN = "<token from step 1.4>"
python -m uvicorn tempo_service.app:app --host 127.0.0.1 --port 8765
```

The sidecar opens and keeps alive the tunnel to the engine. Check http://127.0.0.1:8765/health: `backend` should show `reachable: true` and `tunnel: "up"`.

If the tunnel won't come up, open it yourself in a separate window and point the sidecar at it:

```powershell
wsl -e bash -lc 'ssh -F ~/.brev/ssh_config -N -L 8900:localhost:8900 tempo-l4-instance'
# then start the sidecar with this instead of TEMPO_BREV_INSTANCE / TEMPO_BREV_CLI:
$env:TEMPO_BACKEND_URL = "http://127.0.0.1:8900"
```

### 3. Install the panel

```powershell
Copy-Item -Recurse -Force .\panel "$env:APPDATA\Adobe\CEP\extensions\Tempo"
reg add "HKCU\Software\Adobe\CSXS.11" /v PlayerDebugMode /t REG_SZ /d 1 /f
```

Fully quit After Effects, reopen it, then go to **Window › Extensions › Tempo**.

### 4. Use it

1. Import a video into your project. The panel picks it up automatically, or click **Sync now**.
2. Watch it upload and index. The eye icon shows or hides the stage details.
3. Type a search and press Enter.
4. Click a result: the shot lands on your active comp at the playhead, trimmed. **Ctrl+Z** removes it in one step.

## Development

```powershell
pip install "./service[dev]" "./engine[dev]"
$env:PYTHONPATH = "service;engine"
python -m pytest service/tests engine/tests -q
python -m ruff check service engine
```

To run the engine locally on CPU (smaller models, slower, no GPU needed), use `pip install "./engine[ml]"`, then `python -m tempo_engine.prefetch` and `python -m tempo_engine.app`. Point the sidecar at it with `TEMPO_BACKEND_URL=http://127.0.0.1:8900`.

More detail: `docs/production.md` (setup and troubleshooting), `docs/api.md` and `docs/engine-api.md` (APIs), `AGENTS.md` (architecture and rules).
