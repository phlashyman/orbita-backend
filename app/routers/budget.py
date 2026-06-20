"""
Budget router for Orbita.

Provides CRUD endpoints for budget categories and a summary endpoint
that aggregates projected vs actual spending per category for a given month.
All endpoints are scoped to the current user's family (multi-tenant).
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.budget_category import BudgetCategory
from app.models.transaction import TransactionManual
from app.models.user import User
from app.schemas import (
    BudgetCategoryCreate,
    BudgetCategoryRead,
    BudgetCategoryUpdate,
    BudgetSummary,
    CategorySpent,
)

router = APIRouter(prefix="/budget", tags=["Budget"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_category_or_404(
    db: AsyncSession,
    category_id: UUID,
    family_id: UUID,
) -> BudgetCategory:
    """Fetch a budget category by ID ensuring it belongs to the given family."""
    result = await db.execute(
        select(BudgetCategory).where(
            BudgetCategory.id == category_id,
            BudgetCategory.family_id == family_id,
            BudgetCategory.deleted_at.is_(None),
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget category not found",
        )
    return category


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=List[BudgetCategoryRead])
async def list_budget_categories(
    month_year: date | None = Query(
        None,
        description="Filter by month (first day of month, e.g. 2026-05-01)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List budget categories for the current user's family.

    Optionally filter by ``month_year`` to get categories for a specific month.
    """
    query = select(BudgetCategory).where(
        BudgetCategory.family_id == current_user.family_id,
        BudgetCategory.deleted_at.is_(None),
    )
    if month_year is not None:
        query = query.where(BudgetCategory.month_year == month_year)

    result = await db.execute(query)
    categories = result.scalars().all()
    return categories


@router.post(
    "/categories",
    response_model=BudgetCategoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_budget_category(
    body: BudgetCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new budget category for the current user's family."""
    category = BudgetCategory(
        family_id=current_user.family_id,
        name=body.name,
        projected_amount=body.projected_amount,
        month_year=body.month_year,
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


@router.get("/categories/{category_id}", response_model=BudgetCategoryRead)
async def get_budget_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single budget category by ID (family-scoped)."""
    category = await _get_category_or_404(
        db, category_id, current_user.family_id
    )
    return category


@router.put("/categories/{category_id}", response_model=BudgetCategoryRead)
async def update_budget_category(
    category_id: UUID,
    body: BudgetCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a budget category. Only provided fields are updated."""
    category = await _get_category_or_404(
        db, category_id, current_user.family_id
    )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete a budget category."""
    category = await _get_category_or_404(
        db, category_id, current_user.family_id
    )
    category.soft_delete()
    return None


# ---------------------------------------------------------------------------
# Budget Summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=BudgetSummary)
async def get_budget_summary(
    month_year: date = Query(
        ...,
        description="Budget month (first day of month, e.g. 2026-05-01)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get budget summary: total projected vs actual spending by category.

    Joins budget categories with manual transactions on ``category_id``
    and sums transaction amounts per category for the given month.
    """
    # Fetch all categories for the family + month
    category_result = await db.execute(
        select(BudgetCategory).where(
            BudgetCategory.family_id == current_user.family_id,
            BudgetCategory.month_year == month_year,
            BudgetCategory.deleted_at.is_(None),
        )
    )
    categories = category_result.scalars().all()

    if not categories:
        return BudgetSummary(
            month_year=month_year,
            total_projected=Decimal("0.00"),
            total_spent=Decimal("0.00"),
            total_remaining=Decimal("0.00"),
            categories=[],
        )

    # Sum transactions per category for the given month
    category_ids = [c.id for c in categories]
    tx_result = await db.execute(
        select(
            TransactionManual.category_id,
            func.coalesce(func.sum(TransactionManual.amount), Decimal("0.00")).label(
                "spent_amount"
            ),
        )
        .where(
            TransactionManual.family_id == current_user.family_id,
            TransactionManual.category_id.in_(category_ids),
            TransactionManual.deleted_at.is_(None),
        )
        .group_by(TransactionManual.category_id)
    )
    spent_by_category = {
        row.category_id: Decimal(str(row.spent_amount)) for row in tx_result.all()
    }

    # Build category breakdown
    category_spent_list: list[CategorySpent] = []
    total_projected = Decimal("0.00")
    total_spent = Decimal("0.00")

    for cat in categories:
        projected = Decimal(str(cat.projected_amount))
        spent = spent_by_category.get(cat.id, Decimal("0.00"))
        remaining = projected - spent

        total_projected += projected
        total_spent += spent

        category_spent_list.append(
            CategorySpent(
                category_id=cat.id,
                category_name=cat.name,
                projected_amount=projected,
                spent_amount=spent,
                remaining=remaining,
            )
        )

    return BudgetSummary(
        month_year=month_year,
        total_projected=total_projected,
        total_spent=total_spent,
        total_remaining=total_projected - total_spent,
        categories=category_spent_list,
    )
