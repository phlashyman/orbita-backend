"""
Pydantic schemas for BankStatement model.
Handles imported bank statement lines and their lifecycle.
"""
import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict

from app.models.bank_statement import StatementStatus


class BankStatementLine(BaseModel):
    """Schema for a single line extracted from a bank statement import."""

    bank_transaction_id: str = Field(
        ...,
        max_length=255,
        description="Unique transaction ID from the bank (hash or reference)",
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
    description_raw: str = Field(
        ...,
        max_length=255,
        description="Raw description as it appears on the statement",
    )


class BankStatementImport(BaseModel):
    """Schema for importing a batch of bank statement lines."""

    account_id: uuid.UUID = Field(
        ...,
        description="ID of the bank account these statements belong to",
    )
    lines: list[BankStatementLine] = Field(
        ...,
        min_length=1,
        description="List of statement lines to import",
    )


class BankStatementRead(BaseModel):
    """Schema for reading a bank statement line — includes all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique statement line identifier")
    family_id: uuid.UUID = Field(..., description="ID of the owning family")
    account_id: uuid.UUID = Field(..., description="ID of the associated bank account")
    bank_transaction_id: str = Field(..., description="Bank's unique transaction reference")
    amount: Decimal = Field(..., description="Transaction amount")
    date: datetime.date = Field(..., description="Transaction date")
    description_raw: str = Field(..., description="Raw description from the bank")
    status: StatementStatus = Field(..., description="Statement status")
    assigned_user_id: uuid.UUID | None = Field(
        ...,
        description="ID of the user this statement is assigned to",
    )
    created_at: datetime.datetime = Field(..., description="Timestamp when the statement line was imported")


class StatementStatusUpdate(BaseModel):
    """Schema for updating the status of a bank statement line."""

    status: StatementStatus = Field(
        ...,
        description="New status for the statement line",
    )
    assigned_user_id: uuid.UUID | None = Field(
        default=None,
        description="Optionally assign the statement to a user",
    )
