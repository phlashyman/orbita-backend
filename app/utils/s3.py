"""
S3 / MinIO client wrapper for receipt image storage.
Handles upload, retrieval, and URL generation.
"""
import boto3
from botocore.client import Config
from app.config import settings

_s3_client = None


def get_s3_client():
    """Singleton S3 client (MinIO-compatible)."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            **settings.s3_config,
            config=Config(signature_version="s3v4"),
        )
    return _s3_client


def generate_receipt_path(family_id: str, transaction_id: str, year: int) -> str:
    """Generate S3 key: families/{family_id}/receipts/{year}/{transaction_id}.webp"""
    return f"families/{family_id}/receipts/{year}/{transaction_id}.webp"


def get_receipt_url(key: str) -> str:
    """Generate a presigned URL for temporary access to a receipt."""
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=3600,
    )
