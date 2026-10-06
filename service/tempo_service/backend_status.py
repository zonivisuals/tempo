"""Engine reachability: the probe, its cache, and the tunnel (ADR-0008).

One concern, behind a small interface, so `/health` does not read a module
global mid-update and the prober becomes callable in a test instead of only by
starting the app.

The cache exists because the panel polls `/health` every 2s and a stopped
instance would otherwise cost a connect timeout on every poll. The last known
stage list survives an unreachable engine, so a stopped instance shows a
transition rather than an empty stage list.
"""

import logging
import threading
import time

from .backends import get_provider
from .config import settings
from .tunnel import Tunnel

log = logging.getLogger("tempo.backend")

UNREACHABLE_STATUS: dict = {
    "reachable": False, "gpu": False, "signature": "", "stages": [], "checked_at": 0.0,
}

_lock = threading.Lock()
_status = dict(UNREACHABLE_STATUS)
_tunnel: Tunnel | None = None
_prober_started = False


def _probe_once(timeout: float | None = None) -> dict:
    """One synchronous probe. Never raises, never logs tokens."""
    try:
        provider = get_provider(settings, timeout or settings.backend_health_timeout_s)
        if provider is None:
            return dict(UNREACHABLE_STATUS, checked_at=0.0)
        return provider.health()
    except Exception as exc:  # misconfig must not take down lifespan or /health
        log.warning("engine probe crashed (%s)", exc)
        return dict(UNREACHABLE_STATUS, checked_at=0.0)


def refresh() -> dict:
    probe = _probe_once()
    with _lock:
        # Keep the last known stages while the engine is unreachable.
        stages = probe.get("stages") or _status["stages"]
        _status.update({**probe, "stages": stages, "checked_at": time.monotonic()})
        return dict(_status)


def status() -> dict:
    """The cached status, probing once if the cache was never populated."""
    with _lock:
        cached = dict(_status)
    return refresh() if cached["checked_at"] <= 0 else cached


def stage_names(upload_stage: str) -> list[str]:
    """`upload` plus the engine's stages, for a new job's step list."""
    with _lock:
        return [upload_stage, *_status["stages"]]


def tunnel_state() -> str:
    return _tunnel.state if _tunnel is not None else "off"


def start_tunnel() -> None:
    global _tunnel
    if settings.brev_instance and _tunnel is None:
        _tunnel = Tunnel(settings.brev_cli, settings.brev_instance, settings.tunnel_local_port,
                         settings.tunnel_remote_port, settings.tunnel_backoff_min_s,
                         settings.tunnel_backoff_max_s)
        _tunnel.start()


def stop_tunnel() -> None:
    if _tunnel is not None:
        _tunnel.stop()


def start_prober() -> None:
    """Refresh the cache every interval, logging only on a flip. Daemon; never dies."""
    global _prober_started
    if _prober_started:
        return
    _prober_started = True

    def loop() -> None:
        last = None
        while True:
            try:
                st = refresh()
                flip = (st["reachable"], st["gpu"], st["signature"])
                if flip != last:
                    log.info("engine: reachable=%s gpu=%s signature=%s tunnel=%s",
                             st["reachable"], st["gpu"], st["signature"] or "-", tunnel_state())
                    last = flip
            except Exception as exc:
                log.warning("engine prober error (%s)", exc)
            time.sleep(settings.backend_health_interval_s)

    threading.Thread(target=loop, daemon=True, name="tempo-backend-prober").start()