"""
Pydantic schemas for Receipt upload responses.
"""
import uuid

from pydantic import BaseModel, Field


class ReceiptUploadResponse(BaseModel):
    """Schema for receipt upload response after S3 upload completes."""

    transaction_id: uuid.UUID = Field(
        ...,
        description="ID of the transaction the receipt is attached to",
    )
    receipt_url: str = Field(
        ...,
        description="S3 URL of the uploaded receipt image",
    )
    message: str = Field(
        default="Receipt uploaded successfully",
        description="Human-readable status message",
    )
