"""
Receipt image processing service.

Handles MIME validation, image resizing, WebP transcoding,
and S3 upload for transaction receipt images.

Algorithm (exact):
1. Validate MIME type via magic bytes
2. Open with Pillow
3. Resize maintaining aspect ratio (max width 1200 px)
4. Transcode to WebP format
5. Apply compression quality 75%
6. Generate S3 key: families/{family_id}/receipts/{year}/{transaction_id}.webp
7. Upload to S3 bucket via boto3
8. Return the S3 key
"""

import io
import struct
from datetime import date
from decimal import Decimal
from typing import Final

from PIL import Image

from app.config import settings
from app.utils.s3 import get_s3_client, generate_receipt_path

# ---------------------------------------------------------------------------
# Accepted MIME types and their magic-byte signatures
# ---------------------------------------------------------------------------

_ACCEPTED_MIME_TYPES: Final[set[str]] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

# Magic bytes checked at file header
_MAGIC_SIGNATURES: Final[list[tuple[str, bytes]]] = [
    ("image/jpeg", b"\xff\xd8"),              # JPEG SOI marker
    ("image/png",  b"\x89PNG\r\n\x1a\n"),     # PNG signature
    ("image/webp", b"RIFF"),                  # WebP container start
]

# Resize constraint
_MAX_WIDTH: Final[int] = 1200

# WebP encoding quality
_WEBP_QUALITY: Final[int] = 75

# Maximum upload size (10 MB)
_MAX_FILE_SIZE: Final[int] = 10 * 1024 * 1024


class ImageValidationError(ValueError):
    """Raised when uploaded file fails MIME / size validation."""


class ImageProcessingError(RuntimeError):
    """Raised when Pillow processing or S3 upload fails."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_image_mime(file_bytes: bytes) -> str:
    """
    Detect MIME type of an image by inspecting its magic bytes.

    Checks the file header against known signatures for JPEG, PNG, and WebP.
    Returns the MIME type string (e.g. ``'image/jpeg'``).

    Raises:
        ImageValidationError: If the magic bytes do not match an accepted format
                              or the file is too short to read a signature.
    """
    if len(file_bytes) < 12:
        raise ImageValidationError("File too short to determine MIME type.")

    if len(file_bytes) > _MAX_FILE_SIZE:
        raise ImageValidationError(
            f"File exceeds maximum allowed size of {_MAX_FILE_SIZE} bytes."
        )

    # JPEG
    if file_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"

    # PNG
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    # WebP — RIFF....WEBP
    if (
        file_bytes[:4] == b"RIFF"
        and file_bytes[8:12] == b"WEBP"
    ):
        return "image/webp"

    raise ImageValidationError(
        "Unsupported image format. Accepted: image/jpeg, image/png, image/webp."
    )


def _resize_image(img: Image.Image) -> Image.Image:
    """
    Resize *img* so that its width does not exceed ``_MAX_WIDTH`` pixels
    while preserving the original aspect ratio.

    If the image is already smaller than the limit it is returned unchanged.
    """
    if img.width <= _MAX_WIDTH:
        return img

    ratio = _MAX_WIDTH / img.width
    new_height = int(img.height * ratio)
    return img.resize((_MAX_WIDTH, new_height), Image.LANCZOS)


def _transcode_to_webp(img: Image.Image) -> bytes:
    """
    Convert a Pillow image to WebP bytes at ``_WEBP_QUALITY`` %.

    RGBA images are preserved; all others are converted to RGB first.
    """
    if img.mode in ("RGBA", "P"):
        # P (palette) -> RGBA to avoid information loss
        if img.mode == "P":
            img = img.convert("RGBA")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=_WEBP_QUALITY, method=6)
    return buffer.getvalue()


def process_receipt_image(
    file_bytes: bytes,
    family_id: str,
    transaction_id: str,
    year: int,
) -> str:
    """
    End-to-end receipt-image pipeline.

    Steps:
        1. Validate MIME type (magic bytes).
        2. Open with Pillow.
        3. Resize (max width 1200 px, aspect-ratio preserved).
        4. Transcode to WebP.
        5. Compress at quality 75 %.
        6. Build S3 key: ``families/{family_id}/receipts/{year}/{transaction_id}.webp``.
        7. Upload to S3.
        8. Return the S3 key.

    Args:
        file_bytes: Raw bytes of the uploaded image file.
        family_id: UUID string of the family that owns the transaction.
        transaction_id: UUID string of the parent transaction.
        year: Calendar year used in the S3 path.

    Returns:
        The S3 object key (path) where the processed receipt was stored.

    Raises:
        ImageValidationError: On MIME / size validation failure.
        ImageProcessingError: On Pillow or S3 upload failure.
    """
    # 1. MIME validation
    mime_type = validate_image_mime(file_bytes)

    # 2. Open with Pillow
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()  # sanity check — re-open below for processing
    except Exception as exc:
        raise ImageProcessingError(f"Cannot open image with Pillow: {exc}") from exc

    # Re-open after verify() consumed the stream
    try:
        img = Image.open(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ImageProcessingError(f"Cannot re-open image after verify: {exc}") from exc

    # 3. Resize
    try:
        img = _resize_image(img)
    except Exception as exc:
        raise ImageProcessingError(f"Resize failed: {exc}") from exc

    # 4. Transcode to WebP + 5. quality 75
    try:
        webp_bytes = _transcode_to_webp(img)
    except Exception as exc:
        raise ImageProcessingError(f"WebP transcoding failed: {exc}") from exc

    # 6. Generate S3 key
    s3_key = generate_receipt_path(family_id, transaction_id, year)

    # 7. Upload to S3
    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=webp_bytes,
            ContentType="image/webp",
        )
    except Exception as exc:
        raise ImageProcessingError(f"S3 upload failed: {exc}") from exc

    # 8. Return S3 key
    return s3_key
