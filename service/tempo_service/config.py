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

    # Removed footage is marked stale, pruned only when explicitly enabled
    prune_stale: bool = False

    # Pipeline models (single source of truth for model names)
    clip_model_name: str = "openai/clip-vit-large-patch14"
    whisper_model_name: str = "large-v3"  # faster-whisper model id
    blip2_model_name: str = "Salesforce/blip2-opt-2.7b"
    # AGENTS.md §3.2 shorthand "dslim/bert-base-NER" resolves to this HF id
    ner_model_name: str = "dslim/bert-base-NERD"
    ocr_languages: list[str] = ["en"]

    # Pipeline tuning
    visual_embed_batch: int = 32
    caption_max_new_tokens: int = 40


settings = Settings()
