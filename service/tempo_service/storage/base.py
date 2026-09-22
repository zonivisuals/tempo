"""Storage provider seam (ADR-0006).

Owns bytes: presigned upload URLs, streaming PUT with real progress, and
retention deletes. The storage KEY contract (`tempo/<key>/<basename>`) lives
in drive.py; providers never invent names. Secrets pass through config/env
only and are never logged.
"""

import abc


class StorageError(Exception):
    """Upload/download/delete failure with an honest message."""


class StorageProvider(abc.ABC):
    """Byte store behind presigned URLs. All methods blocking with explicit
    timeouts; failures raise StorageError (never silent, never fake)."""

    @abc.abstractmethod
    def upload_url(self, key: str) -> str:
        """Presigned PUT URL for key (short TTL, single object)."""

    @abc.abstractmethod
    def upload_file(self, local_path: str, key: str, progress=None) -> int:
        """Stream local bytes to key. progress(done, total) per chunk.
        Returns bytes sent."""

    @abc.abstractmethod
    def delete_key(self, key: str) -> bool:
        """Delete key. True when gone (including already-absent)."""
