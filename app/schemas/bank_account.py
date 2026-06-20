"""
Pydantic schemas for BankAccount model.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.models.bank_account import AccountType


class BankAccountCreate(BaseModel):
    """Schema for creating a new bank account or wallet."""

    bank_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Bank or institution name (e.g. BAI, BFA, Caixa Carteira)",
    )
    account_type: AccountType = Field(
        default=AccountType.CURRENT,
        description="Type of account: CURRENT, SAVINGS, or CASH",
    )
    currency: str = Field(
        default="AOA",
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code (default: AOA)",
    )


class BankAccountRead(BaseModel):
    """Schema for reading a bank account — includes all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique account identifier")
    family_id: uuid.UUID = Field(..., description="ID of the owning family")
    bank_name: str = Field(..., description="Bank or institution name")
    account_type: AccountType = Field(..., description="Account type")
    currency: str = Field(..., description="Currency code")
    created_at: datetime = Field(..., description="Timestamp when the account was created")


class BankAccountUpdate(BaseModel):
    """Schema for partial updates to a bank account — all fields optional."""

    bank_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Bank or institution name",
    )
    account_type: AccountType | None = Field(
        default=None, description="Type of account"
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code",
    )
