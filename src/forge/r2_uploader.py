"""R2 signed URL generator + uploader.

P4.4: Handle R2 (S3-compatible) signed URL for binary download.

In production, R2 upload happens in GH Action (has access to R2_ACCESS_KEY).
This module generates signed URL for download (read-only) — read-side only.

For full R2 SDK integration in Worker runtime (P4.5+):
- Use aws4fetch or S3 SDK
- Generate presigned URL with 7-day expiry
- Cache in KV for performance
"""
from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from typing import Any

from src.lib.log import get_logger

log = get_logger("forge.r2")


def generate_signed_url(
    bucket: str,
    key: str,
    account_id: str,
    access_key_id: str,
    secret_access_key: str,
    expires_in_seconds: int = 604800,  # 7 days
) -> str:
    """Generate R2 (S3-compatible) signed URL for download.

    Format: https://<account>.r2.cloudflarestorage.com/<bucket>/<key>?X-Amz-...

    Args:
        bucket: R2 bucket name (e.g. "toolforge-tools")
        key: Object key (e.g. "capcut-reup/0.1.0/setup.exe")
        account_id: Cloudflare account ID
        access_key_id: R2 access key ID
        secret_access_key: R2 secret access key
        expires_in_seconds: URL validity (default 7 days)

    Returns:
        Signed URL string
    """
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    object_url = f"{endpoint}/{bucket}/{key}"

    # S3 v4 signing
    now = int(time.time())
    amz_date = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    amz_short_date = amz_date[:8]  # YYYYMMDD

    # Scope: <date>/<region>/<service>/aws4_request
    scope = f"{amz_short_date}/auto/s3/aws4_request"
    credential = f"{access_key_id}/{scope}"

    # Canonical request
    canonical_uri = "/" + urllib.parse.quote(key, safe="/~")
    canonical_querystring = (
        f"X-Amz-Algorithm=AWS4-HMAC-SHA256"
        f"&X-Amz-Credential={urllib.parse.quote(credential, safe='/+=')}"
        f"&X-Amz-Date={amz_date}"
        f"&X-Amz-Expires={expires_in_seconds}"
        f"&X-Amz-SignedHeaders=host"
    )
    canonical_headers = f"host:{account_id}.r2.cloudflarestorage.com\n"
    signed_headers = "host"
    payload_hash = "UNSIGNED-PAYLOAD"

    canonical_request = (
        f"GET\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    # String to sign
    algorithm = "AWS4-HMAC-SHA256"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    # Signing key
    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

    k_date = sign(f"AWS4{secret_access_key}".encode('utf-8'), amz_short_date)
    k_region = sign(k_date, "auto")
    k_service = sign(k_region, "s3")
    k_signing = sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    signed_url = f"{object_url}?{canonical_querystring}&X-Amz-Signature={signature}"
    return signed_url


def is_valid_r2_config(account_id: str, access_key_id: str, secret_access_key: str) -> bool:
    """Check if R2 credentials are configured."""
    return bool(account_id and access_key_id and secret_access_key)


def build_r2_path(tool_id: str, version: str, filename: str = "setup.exe") -> str:
    """Build canonical R2 object path for a tool binary.

    Pattern: <tool_id>/<version>/<filename>
    Example: capcut-reup/0.1.0/setup.exe
    """
    return f"{tool_id}/{version}/{filename}"
