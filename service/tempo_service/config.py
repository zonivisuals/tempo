"""Tempo service configuration (AGENTS.md §3.7).

All tunables live here with documented defaults and TEMPO_ env overrides.
No absolute paths, ports, weights, or model names are hardcoded in logic —
logic imports them from here.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TEMPO_",
        extra="ignore",
        protected_namespaces=(),  # allow `model_cache_dir`, `model_*` field names
    )

    # Service
    port: int = 8765
    log_level: str = "INFO"

    # Durable state (relative by default; override via TEMPO_ARTIFACT_ROOT)
    artifact_root: Path = Path("./artifacts")
    model_cache_dir: Path = Path("./models")

    # Scoring weights (AGENTS.md §3.5 — pinned, golden-tested)
    dense_w: float = 0.45
    bm25_w: float = 0.40
    anchor_w: float = 0.15
    entity_boost: float = 0.15

    # Artifact semantics — bump whenever layout/meaning changes (forces re-index)
    format_version: int = 1

    # Panel polling / pacing
    sync_poll_s: float = 2.0
    job_poll_s: float = 0.5
    # Size/mtime changes must repeat this many consecutive syncs before they
    # count as `changed` (debounce against transient bad stats at AE reopen /
    # OneDrive hydration). New imports are unaffected (immediate when readable).
    sync_change_confirmations: int = 2

    # Removed footage is marked stale, pruned only when explicitly enabled
    prune_stale: bool = False

    # Pipeline models (single source of truth for model names)
    clip_model_name: str = "openai/clip-vit-large-patch14"
    whisper_model_name: str = "large-v3"  # faster-whisper model id
    blip2_model_name: str = "Salesforce/blip2-opt-2.7b"
    ner_model_name: str = "dslim/bert-base-NER"  # token-classification, simple aggregation
    ocr_languages: list[str] = ["en"]

    # Pipeline tuning
    visual_embed_batch: int = 32
    caption_max_new_tokens: int = 40

    # Remote backend (ADR-0004). Address + token are server config/env only
    # (TEMPO_BACKEND_URL / TEMPO_BACKEND_TOKEN), never user input, never git.
    # backend="local" runs the in-process indexer; "http" proxies to a backend
    # speaking the docs/api.md contract (Modal web endpoint in production).
    backend: str = "local"
    backend_url: str = ""
    backend_token: str = ""
    backend_timeout_s: float = 20.0
    backend_health_timeout_s: float = 3.0
    # Background prober cadence (lifespan thread; /health serves the cache).
    backend_health_interval_s: float = 15.0

    # Drive auto-upload (P9 / ADR-0003). Deterministic `tempo/<key>/<basename>`.
    drive_folder: str = "tempo"
    drive_chunk_mb: int = 8
    oauth_token_path: str = "./secrets/drive_token.json"

    # Storage (ADR-0006). provider="none" keeps the manual-copy behavior;
    # "s3" speaks any S3-compatible store (R2, B2) via presigned URLs.
    # Credentials via env only, never logged. retention="delete" purges the
    # raw upload after artifacts persist (locked product call); "keep" skips.
    storage_provider: str = "none"
    storage_endpoint: str = ""
    storage_bucket: str = "tempo"
    storage_key: str = ""
    storage_secret: str = ""
    storage_region: str = "auto"
    storage_presign_ttl: int = 3600
    storage_retention: str = "delete"

    # Plans (ADR-0007). Free tier locked: 1 footage, 7 footage-minutes.
    # Supabase licenses override this once billing lands.
    plan: str = "free"


settings = Settings()
