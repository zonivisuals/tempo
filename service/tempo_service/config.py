"""Tempo sidecar configuration (AGENTS.md §3.7).

All tunables live here with documented defaults and TEMPO_ env overrides.
No absolute paths, ports, weights, or model names are hardcoded in logic —
logic imports them from here. The sidecar holds no models and no scoring:
both live on the engine (ADR-0008/0009).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEMPO_", extra="ignore")

    # Service
    port: int = 8765
    log_level: str = "INFO"

    # Durable state (relative by default; override via TEMPO_ARTIFACT_ROOT)
    artifact_root: Path = Path("./artifacts")

    # Registry semantics — bump whenever layout/meaning changes. 2 = v4 engine
    # (content_id replaces drive_path); a bump re-enqueues, and the job reuses
    # the engine's index when the content is unchanged.
    format_version: int = 2

    # Panel polling / pacing
    sync_poll_s: float = 2.0
    job_poll_s: float = 0.5
    # Size/mtime changes must repeat this many consecutive syncs before they
    # count as `changed` (debounce against transient bad stats at AE reopen /
    # OneDrive hydration). New imports are unaffected (immediate when readable).
    sync_change_confirmations: int = 2

    # Removed footage is marked stale, pruned only when explicitly enabled
    prune_stale: bool = False

    # Engine (ADR-0008). Address + token are server config/env only
    # (TEMPO_BACKEND_URL / TEMPO_BACKEND_TOKEN), never user input, never git.
    # Empty URL + a Brev instance = the supervised tunnel's local port.
    backend_url: str = ""
    backend_token: str = ""
    backend_timeout_s: float = 20.0
    backend_health_timeout_s: float = 3.0
    # Background prober cadence (lifespan thread; /health serves the cache).
    backend_health_interval_s: float = 15.0
    # Engine job polling: transient misses ridden out before a job fails, and
    # the wait between polls while the engine is asleep/warming.
    backend_poll_miss_retries: int = 5
    backend_asleep_wait_s: float = 2.0
    # Thumbs.tar sync-down can be large; it gets its own budget.
    backend_bulk_timeout_s: float = 120.0

    # Brev tunnel (ADR-0008): `<brev_cli> port-forward <instance> --port L:R`.
    # Empty instance = no tunnel (direct TEMPO_BACKEND_URL, e.g. a local CPU engine).
    # On Windows the CLI lives in WSL: TEMPO_BREV_CLI="wsl brev".
    brev_instance: str = ""
    brev_cli: str = "brev"
    tunnel_local_port: int = 8900
    tunnel_remote_port: int = 8900
    tunnel_backoff_min_s: float = 1.0
    tunnel_backoff_max_s: float = 30.0

    # Direct upload to the engine (resumable, offset-checked). Must stay under
    # the engine's TEMPO_ENGINE_MAX_CHUNK_MB.
    upload_chunk_mb: int = 8
    upload_timeout_s: float = 120.0

    # Plans (ADR-0007, amended by ADR-0010). Free tier locked: 3 footage, 120 footage-minutes.
    # Supabase licenses override this once billing lands.
    plan: str = "free"

    @property
    def engine_url(self) -> str:
        """Configured URL, else the tunnel's local end when a Brev instance is set."""
        if self.backend_url:
            return self.backend_url
        if self.brev_instance:
            return f"http://127.0.0.1:{self.tunnel_local_port}"
        return ""


settings = Settings()
