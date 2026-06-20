"""
Pydantic schemas for ConciliationLog model.
Handles matching/unmatching manual transactions with bank statement lines.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.models.bank_statement import StatementStatus
from app.models.transaction import TransactionStatus


class MatchRequest(BaseModel):
    """Schema for requesting a match between a manual transaction and a bank statement line."""

    transaction_manual_id: uuid.UUID = Field(
        ...,
        description="ID of the manual transaction",
    )
    bank_statement_id: uuid.UUID = Field(
        ...,
        description="ID of the bank statement line",
    )


class MatchResult(BaseModel):
    """Schema representing a created conciliation log entry with related data."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique conciliation log identifier")
    family_id: uuid.UUID = Field(..., description="ID of the owning family")
    transaction_manual_id: uuid.UUID = Field(..., description="ID of the matched manual transaction")
    bank_statement_id: uuid.UUID = Field(..., description="ID of the matched bank statement line")
    conciliated_by: uuid.UUID | None = Field(..., description="ID of the user who performed the match")
    conciliated_at: datetime = Field(..., description="Timestamp when the match was made")

    # Nested related data for frontend display
    transaction_amount: str = Field(..., description="Amount from the manual transaction")
    transaction_date: datetime = Field(..., description="Date of the manual transaction")
    transaction_description: str | None = Field(..., description="Description of the manual transaction")
    statement_amount: str = Field(..., description="Amount from the bank statement")
    statement_date: datetime = Field(..., description="Date of the bank statement line")
    statement_description_raw: str = Field(..., description="Raw description from the bank statement")


class MatchScore(BaseModel):
    """Schema for a proposed match with confidence score."""

    score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Match confidence score (0-100)",
    )
    statement_id: uuid.UUID = Field(..., description="ID of the bank statement line")
    transaction_id: uuid.UUID = Field(..., description="ID of the manual transaction")
    match_type: str = Field(
        ...,
        pattern="^(AUTO|SUGGESTION|NONE)$",
        description="Match type: AUTO (high confidence), SUGGESTION (medium), NONE (no match)",
    )


class UnmatchRequest(BaseModel):
    """Schema for requesting to unmatch (break) an existing conciliation."""

    conciliation_log_id: uuid.UUID = Field(
        ...,
        description="ID of the conciliation log entry to remove",
    )
