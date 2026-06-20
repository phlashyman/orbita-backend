"""
Pydantic schemas for Broker File Upload module.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# Broker Position Extracted
# ============================================================================

class BrokerPositionExtracted(BaseModel):
    """
    A single position extracted from a broker file.

    Represents one line in a portfolio statement — typically one instrument
    with its quantity, price, and total value.
    """

    ticker: Optional[str] = Field(
        None,
        description="Instrument ticker or ISIN code",
    )
    name: Optional[str] = Field(
        None,
        description="Instrument name or description",
    )
    quantity: Optional[float] = Field(
        None,
        description="Number of units held",
    )
    price: Optional[float] = Field(
        None,
        description="Unit price (avg buy or current market)",
    )
    value: Optional[float] = Field(
        None,
        description="Total position value (quantity * price)",
    )
    instrument_type: Optional[str] = Field(
        None,
        description="Type of instrument (TREASURY_BOND, CORPORATE_BOND, etc.)",
    )
    market: Optional[str] = Field(
        None,
        description="Market / segment where the instrument is traded (e.g. BODIVA OBRIGAÇÕES)",
    )
    currency: Optional[str] = Field(
        None,
        description="Currency of the position values (e.g. AOA, USD)",
    )
    par_value: Optional[float] = Field(
        None,
        description="Nominal / par value per unit",
    )
    acquisition_value: Optional[float] = Field(
        None,
        description="Total acquisition value of the position",
    )
    unrealized_pnl: Optional[float] = Field(
        None,
        description="Unrealized profit/loss (current value - acquisition value)",
    )
    unrealized_pnl_pct: Optional[float] = Field(
        None,
        description="Unrealized profit/loss as a percentage of acquisition value",
    )
    daily_variation_pct: Optional[float] = Field(
        None,
        description="Daily variation percentage",
    )
    weight_pct: Optional[float] = Field(
        None,
        description="Position weight as a percentage of the total portfolio",
    )
    raw_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Raw row data for debugging / manual mapping",
    )


# ============================================================================
# Broker File Upload Create
# ============================================================================

class BrokerFileUploadCreate(BaseModel):
    """
    Schema for creating a broker file upload record.

    Used internally by the upload endpoint; the file itself is sent
    as multipart/form-data separately.
    """

    broker_id: Optional[UUID] = Field(
        None,
        description="Optional broker association",
    )
    portfolio_id: Optional[UUID] = Field(
        None,
        description="Optional target portfolio for import",
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="User-provided notes",
    )


# ============================================================================
# Broker File Upload Update
# ============================================================================

class BrokerFileUploadUpdate(BaseModel):
    """
    Schema for updating a broker file upload.

    Only notes can be updated after creation.
    """

    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="User-provided notes",
    )


# ============================================================================
# Broker File Upload Read (full detail)
# ============================================================================

class BrokerFileUploadRead(BaseModel):
    """
    Full response schema for a broker file upload.

    Includes parsed_data (extracted positions) when available.
    """

    id: UUID
    family_id: UUID
    user_id: Optional[UUID]
    broker_id: Optional[UUID]
    portfolio_id: Optional[UUID]

    original_filename: str
    stored_filename: str
    s3_key: str
    file_size: Optional[int]
    file_type: str

    status: str
    parsed_data: Optional[List[BrokerPositionExtracted]] = None
    error_message: Optional[str] = None

    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# Broker File Upload List Item (lightweight)
# ============================================================================

class BrokerFileUploadListItem(BaseModel):
    """
    Lightweight list response for broker file uploads.

    Excludes parsed_data to keep responses small.
    """

    id: UUID
    family_id: UUID
    user_id: Optional[UUID]
    broker_id: Optional[UUID]
    portfolio_id: Optional[UUID]

    original_filename: str
    file_type: str
    file_size: Optional[int]
    status: str
    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# Broker File Process Result
# ============================================================================

class BrokerFileProcessResult(BaseModel):
    """
    Result of processing a broker file.

    Returned by the POST /{id}/process endpoint.
    """

    upload_id: UUID
    status: str
    file_type: str
    positions_found: int
    positions: List[BrokerPositionExtracted]
    error_message: Optional[str] = None
    detected_broker_id: Optional[UUID] = None
    detected_broker_name: Optional[str] = None


# ============================================================================
# Broker File Import Request
# ============================================================================

class BrokerFileImportRequest(BaseModel):
    """
    Request body for importing positions from a processed file.

    The user selects which positions to import and provides the target
    portfolio and instrument mappings.
    """

    portfolio_id: Optional[UUID] = Field(
        None,
        description="Target portfolio to import holdings into (optional — omit to import as unallocated)",
    )
    broker_id: Optional[UUID] = Field(
        None,
        description="Broker to associate with the holdings",
    )
    positions: List[BrokerPositionExtracted] = Field(
        ...,
        description="Positions to import (subset of parsed_data)",
    )


# ============================================================================
# Broker File Import Result
# ============================================================================

class BrokerFileImportResult(BaseModel):
    """
    Result of importing positions as holdings.

    Returned by the POST /{id}/import endpoint.
    """

    upload_id: UUID
    portfolio_id: Optional[UUID] = None
    holdings_created: int
    trades_created: int
    errors: List[str] = Field(default_factory=list)


# ============================================================================
# Broker File Upload Form (multipart upload)
# ============================================================================

class BrokerFileUploadForm(BaseModel):
    """
    Form data accompanying a multipart file upload.

    This schema documents the expected form fields; the actual
    parsing is done via FastAPI's Form() / File() dependencies.
    """

    broker_id: Optional[UUID] = None
    portfolio_id: Optional[UUID] = None
    notes: Optional[str] = Field(None, max_length=500)
