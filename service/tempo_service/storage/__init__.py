"""Storage providers (ADR-0006). Factory reads server config only."""

import logging

from .base import StorageError, StorageProvider

log = logging.getLogger("tempo.storage")


class S3Backend(StorageProvider):
    """Any S3-compatible store: AWS S3, Cloudflare R2, Backblaze B2.

    Only the endpoint/region/credentials differ. Uploads go direct from
    the sidecar to the store via presigned PUT (bytes never proxy through
    our servers); deletes are presigned DELETEs.
    """

    def __init__(self, endpoint, bucket, access_key, secret_key,
                 region="auto", ttl_s=3600, timeout_s=600.0):
        from . import s3 as s3_module

        self._s3 = s3_module
        self._endpoint = endpoint.rstrip("/")
        self._bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._ttl_s = ttl_s
        self._timeout_s = timeout_s

    def upload_url(self, key: str) -> str:
        return self._s3.presign(
            "PUT", self._endpoint, self._access_key, self._secret_key,
            self._bucket, key, expires_s=self._ttl_s, region=self._region,
        )

    def upload_file(self, local_path: str, key: str, progress=None) -> int:
        try:
            return self._s3.put_file(
                self.upload_url(key), local_path, progress=progress,
                timeout_s=self._timeout_s,
            )
        except OSError as exc:
            raise StorageError(f"upload failed for {key}: {exc}") from exc

    def delete_key(self, key: str) -> bool:
        try:
            url = self._s3.presign(
                "DELETE", self._endpoint, self._access_key, self._secret_key,
                self._bucket, key, expires_s=300, region=self._region,
            )
            return self._s3.delete_key(url, timeout_s=60.0)
        except OSError as exc:
            raise StorageError(f"delete failed for {key}: {exc}") from exc


def get_storage(provider, endpoint, bucket, access_key, secret_key,
                region="auto", ttl_s=3600, timeout_s=600.0):
    """Return the configured provider, or None (manual-copy behavior).

    `provider="s3"` requires endpoint + bucket + credentials; anything
    missing falls back to None with a warning (never a silent stall).
    Unknown names raise ValueError (fail fast on typos).
    """
    if provider in ("", "none"):
        return None
    if provider == "s3":
        if not (endpoint and bucket and access_key and secret_key):
            log.warning("storage=s3 but endpoint/bucket/credentials incomplete; uploads stay manual")
            return None
        return S3Backend(endpoint, bucket, access_key, secret_key, region, ttl_s, timeout_s)
    raise ValueError(f"unknown storage provider: {provider!r} (want none|s3)")


__all__ = ["StorageError", "StorageProvider", "S3Backend", "get_storage"]
