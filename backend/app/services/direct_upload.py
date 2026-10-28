"""Presigned POST for browser-direct uploads to object storage."""

from typing import Any, Dict

import boto3
from botocore.client import Config

from app.config import settings

DIRECT_UPLOAD_EXPIRES_S = 900


def presign_upload_post(bucket: str, key: str, max_size: int) -> Dict[str, Any]:
    """Return a presigned POST (url + fields) the browser can use directly.

    The S3 v4 signature covers the host, so the client is built against the
    PUBLIC base URL (the one the browser reaches), not the internal endpoint.
    Signing is local: no network call is made.
    """
    public_base = (settings.MINIO_PUBLIC_BASE_URL or "").rstrip("/")
    if not public_base:
        raise RuntimeError("MINIO_PUBLIC_BASE_URL is not configured")
    client = boto3.client(
        "s3",
        endpoint_url=public_base,
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )
    return client.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields={"key": key, "Content-Type": "application/octet-stream"},
        Conditions=[
            {"key": key},
            {"Content-Type": "application/octet-stream"},
            ["content-length-range", 1, max_size],
        ],
        ExpiresIn=DIRECT_UPLOAD_EXPIRES_S,
    )
