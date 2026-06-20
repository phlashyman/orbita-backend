"""
Pydantic schemas for TransactionManual model.
Manual transactions entered by family members.
"""
import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict

from app.models.transaction import TransactionStatus


class TransactionCreate(BaseModel):
    """Schema for creating a new manual transaction."""

    account_id: uuid.UUID = Field(
        ...,
        description="ID of the bank account associated with this transaction",
    )
    category_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the budget category (optional)",
    )
    amount: Decimal = Field(
        ...,
        decimal_places=2,
        description="Transaction amount",
    )
    date: datetime.date = Field(
        ...,
        description="Transaction date",
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        description="Optional description or note",
    )


class TransactionRead(BaseModel):
    """Schema for reading a transaction — includes all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique transaction identifier")
    family_id: uuid.UUID = Field(..., description="ID of the owning family")
    user_id: uuid.UUID | None = Field(..., description="ID of the user who created the transaction")
    account_id: uuid.UUID = Field(..., description="ID of the associated bank account")
    category_id: uuid.UUID | None = Field(..., description="ID of the budget category")
    amount: Decimal = Field(..., description="Transaction amount")
    date: datetime.date = Field(..., description="Transaction date")
    description: str | None = Field(..., description="Transaction description")
    receipt_url: str | None = Field(..., description="S3 URL to receipt image")
    status: TransactionStatus = Field(..., description="Transaction status: PENDING or CONCILED")
    created_at: datetime.datetime = Field(..., description="Timestamp when the transaction was created")


class TransactionUpdate(BaseModel):
    """Schema for partial updates to a transaction — all fields optional."""

    account_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the bank account",
    )
    category_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the budget category",
    )
    amount: Decimal | None = Field(
        default=None,
        decimal_places=2,
        description="Transaction amount",
    )
    date: datetime.date | None = Field(
        default=None,
        description="Transaction date",
    )
    description: str | None = Field(
        default=None,
        max_length=255,
        description="Transaction description",
    )


class TransactionListFilter(BaseModel):
    """Schema for filtering and querying transactions."""

    account_id: uuid.UUID | None = Field(
        default=None,
        description="Filter by bank account ID",
    )
    category_id: uuid.UUID | None = Field(
        default=None,
        description="Filter by budget category ID",
    )
    status: TransactionStatus | None = Field(
        default=None,
        description="Filter by transaction status",
    )
    date_from: datetime.date | None = Field(
        default=None,
        description="Filter transactions from this date (inclusive)",
    )
    date_to: datetime.date | None = Field(
        default=None,
        description="Filter transactions up to this date (inclusive)",
    )
