"""Drive auto-upload helpers (ADR-0003, P9-minimal).

Deterministic remote name: `tempo/<footage_key>/<basename>` where
`footage_key = sha1(local_path)[:10]` (registry.footage_key_for — stable
across re-imports). Same key + size already on Drive → skip bytes.

P9-minimal ships the path contract + local bookkeeping only; resumable
uploads via google-api-python-client land next (pinned then, with rationale).
No hardcoded paths — drive_folder comes from config.
"""

from pathlib import PurePosixPath

from . import registry as registry_module
from .config import settings


def drive_path_for(footage_key: str, local_path: str) -> str:
    """Deterministic Drive destination for a footage key."""
    base = local_path.replace("\\", "/").rsplit("/", 1)[-1] or footage_key
    return str(PurePosixPath(settings.drive_folder) / footage_key / base)


def drive_path_for_local(local_path: str) -> str:
    """Convenience: key lookup + deterministic path in one call."""
    return drive_path_for(registry_module.footage_key_for(local_path), local_path)
