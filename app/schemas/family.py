"""
Pydantic schemas for Family model.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class FamilyCreate(BaseModel):
    """Schema for creating a new family (tenant)."""

    name: str = Field(..., min_length=1, max_length=100, description="Family name")


class FamilyRead(BaseModel):
    """Schema for reading a family — output only, no sensitive data."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique family identifier")
    name: str = Field(..., description="Family name")
    created_at: datetime = Field(..., description="Timestamp when the family was created")
