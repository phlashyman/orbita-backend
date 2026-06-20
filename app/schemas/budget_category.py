"""
Pydantic schemas for BudgetCategory model.
Categories are scoped by family and month for time-boxed budgeting.
"""
import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict


class BudgetCategoryCreate(BaseModel):
    """Schema for creating a new budget category."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Category name (e.g. Groceries, Transport)",
    )
    projected_amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Planned spending amount for this category",
    )
    month_year: datetime.date = Field(
        ...,
        description="Budget month (first day of the month, e.g. 2026-05-01)",
    )


class BudgetCategoryRead(BaseModel):
    """Schema for reading a budget category — includes all fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique category identifier")
    family_id: uuid.UUID = Field(..., description="ID of the owning family")
    name: str = Field(..., description="Category name")
    projected_amount: Decimal = Field(..., description="Planned spending amount")
    month_year: datetime.date = Field(..., description="Budget month")
    created_at: datetime.datetime = Field(..., description="Timestamp when the category was created")


class BudgetCategoryUpdate(BaseModel):
    """Schema for partial updates to a budget category."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Category name",
    )
    projected_amount: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=2,
        description="Planned spending amount",
    )


class CategorySpent(BaseModel):
    """Inner schema representing spent amount per category."""

    category_id: uuid.UUID = Field(..., description="Category identifier")
    category_name: str = Field(..., description="Category name")
    projected_amount: Decimal = Field(..., description="Planned amount")
    spent_amount: Decimal = Field(..., description="Actual spent amount")
    remaining: Decimal = Field(..., description="Remaining budget (projected - spent)")


class BudgetSummary(BaseModel):
    """Aggregated budget overview for a family in a given month."""

    month_year: datetime.date = Field(..., description="Budget month")
    total_projected: Decimal = Field(..., description="Sum of all projected amounts")
    total_spent: Decimal = Field(..., description="Sum of all actual spending")
    total_remaining: Decimal = Field(..., description="Total remaining across all categories")
    categories: list[CategorySpent] = Field(
        default_factory=list,
        description="Per-category spending breakdown",
    )
