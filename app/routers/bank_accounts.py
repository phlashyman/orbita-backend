"""
Bank accounts router for Orbita.

Provides CRUD endpoints for managing bank accounts and wallets.
All endpoints are scoped to the current user's family (multi-tenant).
"""
from datetime import datetime, timezone
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.bank_account import BankAccount
from app.models.user import User
from app.schemas import BankAccountCreate, BankAccountRead, BankAccountUpdate

router = APIRouter(prefix="/bank-accounts", tags=["Bank Accounts"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_account_or_404(
    db: AsyncSession,
    account_id: UUID,
    family_id: UUID,
) -> BankAccount:
    """Fetch a bank account by ID ensuring it belongs to the given family."""
    result = await db.execute(
        select(BankAccount).where(
            BankAccount.id == account_id,
            BankAccount.family_id == family_id,
            BankAccount.deleted_at.is_(None),
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank account not found",
        )
    return account


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[BankAccountRead])
async def list_bank_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all active bank accounts for the current user's family."""
    result = await db.execute(
        select(BankAccount).where(
            BankAccount.family_id == current_user.family_id,
            BankAccount.deleted_at.is_(None),
        )
    )
    accounts = result.scalars().all()
    return accounts


@router.post(
    "/",
    response_model=BankAccountRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_bank_account(
    body: BankAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new bank account for the current user's family."""
    account = BankAccount(
        family_id=current_user.family_id,
        bank_name=body.bank_name,
        account_type=body.account_type.value,
        currency=body.currency,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@router.get("/{account_id}", response_model=BankAccountRead)
async def get_bank_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single bank account by ID (family-scoped)."""
    account = await _get_account_or_404(
        db, account_id, current_user.family_id
    )
    return account


@router.put("/{account_id}", response_model=BankAccountRead)
async def update_bank_account(
    account_id: UUID,
    body: BankAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a bank account. Only provided fields are updated."""
    account = await _get_account_or_404(
        db, account_id, current_user.family_id
    )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # Handle enum values
        if hasattr(value, "value"):
            setattr(account, field, value.value)
        else:
            setattr(account, field, value)

    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bank_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete a bank account."""
    account = await _get_account_or_404(
        db, account_id, current_user.family_id
    )
    account.soft_delete()
    return None
