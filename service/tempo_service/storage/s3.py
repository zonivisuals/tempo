"""S3-compatible presigned URLs + streaming PUT (SigV4, stdlib only).

Implements AWS Signature Version 4 for presigned requests exactly per
https://docs.aws.amazon.com/AmazonS3/latest/API/sig-v4-authenticating-requests.html
(path-style `/bucket/key`, `host` as the only signed header,
`UNSIGNED-PAYLOAD`). Works against AWS S3, Cloudflare R2, and Backblaze B2
(S3-compat endpoints) — only the endpoint/region/credentials differ.

Byte-parity against botocore is asserted in tests (frozen clock), so this
file may not change signing behavior without updating those vectors.
"""

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit


def _amz_now(amz_date: str | None) -> tuple[str, str]:
    if amz_date is not None:
        return amz_date, amz_date[:8]
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return stamp, stamp[:8]


def _quote_key(key: str) -> str:
    # S3 path encoding: keep / unencoded, uppercase hex, ~ stays literal.
    return quote(key, safe="/~")


def _signing_key(secret: str, date: str, region: str) -> bytes:
    k_date = hmac.new(("AWS4" + secret).encode("utf-8"), date.encode("utf-8"),
                      hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


def presign(method: str, endpoint: str, access_key: str, secret_key: str,
            bucket: str, key: str, expires_s: int = 3600,
            region: str = "auto", amz_date: str | None = None) -> str:
    """Presigned URL for one S3 operation (GET/PUT/DELETE) on bucket/key."""
    method = method.upper()
    if method not in ("GET", "PUT", "DELETE"):
        raise ValueError(f"unsupported method for presign: {method}")
    stamp, datestamp = _amz_now(amz_date)
    host = urlsplit(endpoint).netloc
    canonical_uri = f"/{bucket}/{_quote_key(key)}"
    credential = f"{access_key}/{datestamp}/{region}/s3/aws4_request"
    params = [
        ("X-Amz-Algorithm", "AWS4-HMAC-SHA256"),
        ("X-Amz-Credential", credential),
        ("X-Amz-Date", stamp),
        ("X-Amz-Expires", str(int(expires_s))),
        ("X-Amz-SignedHeaders", "host"),
    ]
    canonical_qs = "&".join(
        f"{quote(k, safe='~')}={quote(v, safe='~')}" for k, v in sorted(params)
    )
    canonical_headers = f"host:{host}\n"
    canonical_request = "\n".join(
        [method, canonical_uri, canonical_qs, canonical_headers,
         "host", "UNSIGNED-PAYLOAD"]
    )
    scope = f"{datestamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", stamp, scope,
         hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()]
    )
    signature = hmac.new(
        _signing_key(secret_key, datestamp, region),
        string_to_sign.encode("utf-8"), hashlib.sha256,
    ).hexdigest()
    return f"{endpoint.rstrip('/')}{canonical_uri}?{canonical_qs}&X-Amz-Signature={signature}"


def put_file(url: str, local_path: str, progress=None, chunk_size: int = 1 << 20,
             timeout_s: float = 600.0) -> int:
    """Stream a local file to a presigned PUT URL with real byte progress.

    progress(done, total) is called per chunk. Returns bytes sent. Raises
    OSError/URLError with the status surfaced — never silent.
    """
    import os
    import urllib.error
    import urllib.request

    total = os.path.getsize(local_path)

    class _Reader:
        def __init__(self, path):
            self._f = open(path, "rb")
            self._done = 0

        def read(self, n=-1):
            chunk = self._f.read(n)
            self._done += len(chunk)
            if progress:
                progress(self._done, total)
            return chunk

        def close(self):
            try:
                self._f.close()
            except OSError:
                pass

    reader = _Reader(local_path)
    req = urllib.request.Request(
        url, data=reader, method="PUT",
        headers={"Content-Type": "application/octet-stream",
                 "Content-Length": str(total)},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            if res.status not in (200, 201, 204):
                raise OSError(f"upload failed: HTTP {res.status}")
    except urllib.error.HTTPError as exc:
        raise OSError(f"upload failed: HTTP {exc.code}") from exc
    finally:
        reader.close()
    if progress:
        progress(total, total)
    return total


def delete_key(url: str, timeout_s: float = 60.0) -> bool:
    """DELETE an object via its presigned URL. True on 2xx, False on 404."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as res:
            return 200 <= res.status < 300
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise OSError(f"delete failed: HTTP {exc.code}") from exc
