"""
Watchlist router — CRUD para activos internacionais guardados por utilizador.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.models.watchlist import WatchlistItem

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class WatchlistItemCreate(BaseModel):
    ticker: str = Field(..., max_length=20)
    exchange: str = Field(..., max_length=30)
    name: str | None = Field(None, max_length=200)
    sector: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=500)


class WatchlistItemRead(BaseModel):
    id: str
    ticker: str
    exchange: str
    name: str | None
    sector: str | None
    notes: str | None
    created_at: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[WatchlistItemRead])
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all watchlist items for the authenticated user."""
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == current_user.id, WatchlistItem.deleted_at.is_(None))
        .order_by(WatchlistItem.created_at.desc())
    )
    items = result.scalars().all()
    return [
        WatchlistItemRead(
            id=str(item.id),
            ticker=item.ticker,
            exchange=item.exchange,
            name=item.name,
            sector=item.sector,
            notes=item.notes,
            created_at=item.created_at.isoformat(),
        )
        for item in items
    ]


@router.post("/", response_model=WatchlistItemRead, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    body: WatchlistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Add a ticker to the user's watchlist. Duplicate (same ticker+exchange) is rejected."""
    existing = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.ticker == body.ticker.upper(),
            WatchlistItem.exchange == body.exchange.upper(),
            WatchlistItem.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Activo já existe na watchlist.")

    item = WatchlistItem(
        user_id=current_user.id,
        ticker=body.ticker.upper(),
        exchange=body.exchange.upper(),
        name=body.name,
        sector=body.sector,
        notes=body.notes,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)

    return WatchlistItemRead(
        id=str(item.id),
        ticker=item.ticker,
        exchange=item.exchange,
        name=item.name,
        sector=item.sector,
        notes=item.notes,
        created_at=item.created_at.isoformat(),
    )


@router.patch("/{item_id}", response_model=WatchlistItemRead)
async def update_watchlist_item(
    item_id: str,
    body: WatchlistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update notes or sector for a watchlist item."""
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    item.notes = body.notes
    item.sector = body.sector
    item.name = body.name or item.name
    await db.flush()

    return WatchlistItemRead(
        id=str(item.id),
        ticker=item.ticker,
        exchange=item.exchange,
        name=item.name,
        sector=item.sector,
        notes=item.notes,
        created_at=item.created_at.isoformat(),
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft-delete a watchlist item."""
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    item.soft_delete()
    await db.commit()
