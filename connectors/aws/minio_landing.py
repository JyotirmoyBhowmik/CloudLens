"""MinIO S3 Landing Storage Adapter (connectors/aws layer).

Provides isolated S3/MinIO bucket landing operations without leaking boto3
into higher layers or contract specifications.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def upload_to_minio_s3(
    bucket: str,
    key: str,
    payload_bytes: bytes,
    content_type: str = "application/json",
) -> bool:
    """Uploads raw payload directly to MinIO S3 bucket (Prompt P14)."""
    try:
        import boto3

        s3_endpoint = os.getenv("S3_ENDPOINT", os.getenv("MINIO_ENDPOINT", "http://localhost:9000"))
        s3_access = os.getenv(
            "S3_ACCESS_KEY", os.getenv("OBJECT_STORE_ACCESS_KEY", "cloudlens_minio")
        )
        s3_secret = os.getenv(
            "S3_SECRET_KEY", os.getenv("OBJECT_STORE_SECRET_KEY", "cloudlens_minio_password")
        )
        s3_client = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access,
            aws_secret_access_key=s3_secret,
            region_name="us-east-1",
        )
        try:
            s3_client.create_bucket(Bucket=bucket)
        except Exception:
            pass
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=payload_bytes,
            ContentType=content_type,
        )
        logger.info(
            "Uploaded raw payload to MinIO: %s/%s (%d bytes)", bucket, key, len(payload_bytes)
        )
        return True
    except Exception as s3_err:
        logger.debug("MinIO S3 landing note: %s", s3_err)
        return False
