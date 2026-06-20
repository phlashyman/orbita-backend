"""
Portfolio router for Orbita.

Provides CRUD endpoints for:
- Portfolios (carteiras de investimento)
- Portfolio Holdings (posições)
- Instruments (instrumentos BODIVA)
- Brokers (corretoras)
- Trades (operações/compras-vendas)

All endpoints are scoped to the current user's family (multi-tenant).
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_active_user, require_admin
from app.models.broker import Broker
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.portfolio_holding import PortfolioHolding
from app.models.trade import Trade
from app.models.user import User
from app.schemas import (
    BrokerCreate,
    BrokerRead,
    BrokerUpdate,
    ConsolidatedPortfolioSummary,
    HoldingWithDetails,
    InstrumentCreate,
    InstrumentRead,
    InstrumentUpdate,
    PortfolioCreate,
    PortfolioHoldingCreate,
    PortfolioHoldingRead,
    PortfolioHoldingUpdate,
    PortfolioRead,
    PortfolioSummary,
    PortfolioUpdate,
    TradeCreate,
    TradeRead,
)

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


# =============================================================================
# Helpers
# =============================================================================

async def _get_portfolio_or_404(
    db: AsyncSession,
    portfolio_id: UUID,
    family_id: UUID,
) -> Portfolio:
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.family_id == family_id,
            Portfolio.deleted_at.is_(None),
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )
    return portfolio


async def _get_holding_or_404(
    db: AsyncSession,
    holding_id: UUID,
    family_id: UUID,
) -> PortfolioHolding:
    """Fetch a holding ensuring its portfolio belongs to the family."""
    result = await db.execute(
        select(PortfolioHolding)
        .join(Portfolio, PortfolioHolding.portfolio_id == Portfolio.id)
        .where(
            PortfolioHolding.id == holding_id,
            Portfolio.family_id == family_id,
            Portfolio.deleted_at.is_(None),
        )
    )
    holding = result.scalar_one_or_none()
    if holding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holding not found",
        )
    return holding


async def _get_instrument_or_404(
    db: AsyncSession,
    instrument_id: UUID,
) -> Instrument:
    result = await db.execute(
        select(Instrument).where(
            Instrument.id == instrument_id,
            Instrument.deleted_at.is_(None),
        )
    )
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrument not found",
        )
    return instrument


# =============================================================================
# Broker Endpoints (Admin-managed reference data — ADMIN ONLY for mutations)
# =============================================================================

@router.get("/brokers", response_model=List[BrokerRead])
async def list_brokers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """List all active brokers (reference data)."""
    result = await db.execute(
        select(Broker).where(Broker.deleted_at.is_(None)).order_by(Broker.name)
    )
    return result.scalars().all()


@router.post("/brokers", response_model=BrokerRead, status_code=status.HTTP_201_CREATED)
async def create_broker(
    body: BrokerCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Create a new broker (admin only)."""
    broker = Broker(**body.model_dump())
    db.add(broker)
    await db.flush()
    await db.refresh(broker)
    return broker


# =============================================================================
# Instrument Endpoints (Admin-managed reference data — ADMIN ONLY for mutations)
# =============================================================================

@router.get("/instruments", response_model=List[InstrumentRead])
async def list_instruments(
    active_only: bool = Query(True, description="Filter only active instruments"),
    instrument_type: str | None = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """List BODIVA instruments (reference data)."""
    query = select(Instrument).where(Instrument.deleted_at.is_(None))
    if active_only:
        query = query.where(Instrument.is_active == True)
    if instrument_type:
        query = query.where(Instrument.instrument_type == instrument_type)
    query = query.order_by(Instrument.maturity_date)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/instruments/{instrument_id}", response_model=InstrumentRead)
async def get_instrument(
    instrument_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_active_user),
):
    """Get a single instrument by ID."""
    return await _get_instrument_or_404(db, instrument_id)


@router.post(
    "/instruments", response_model=InstrumentRead, status_code=status.HTTP_201_CREATED
)
async def create_instrument(
    body: InstrumentCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Create a new BODIVA instrument (admin only)."""
    instrument = Instrument(**body.model_dump())
    db.add(instrument)
    await db.flush()
    await db.refresh(instrument)
    return instrument


@router.put("/instruments/{instrument_id}", response_model=InstrumentRead)
async def update_instrument(
    instrument_id: UUID,
    body: InstrumentUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Update instrument market data (admin only)."""
    instrument = await _get_instrument_or_404(db, instrument_id)
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(instrument, field, value)
    return instrument


# =============================================================================
# Portfolio Endpoints (Family-scoped)
# =============================================================================

@router.get("/portfolios", response_model=List[PortfolioRead])
async def list_portfolios(
    portfolio_type: str | None = Query(None, description="Filter by type: REAL or SIMULATED"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List portfolios for the current user's family."""
    query = select(Portfolio).where(
        Portfolio.family_id == current_user.family_id,
        Portfolio.deleted_at.is_(None),
    )
    if portfolio_type:
        query = query.where(Portfolio.portfolio_type == portfolio_type)
    query = query.order_by(Portfolio.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/portfolios", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED
)
async def create_portfolio(
    body: PortfolioCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new portfolio for the current user's family."""
    portfolio = Portfolio(
        family_id=current_user.family_id,
        user_id=current_user.id,
        **body.model_dump(),
    )
    db.add(portfolio)
    await db.flush()
    await db.refresh(portfolio)
    return portfolio


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioRead)
async def get_portfolio(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a single portfolio by ID (family-scoped)."""
    return await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)


@router.put("/portfolios/{portfolio_id}", response_model=PortfolioRead)
async def update_portfolio(
    portfolio_id: UUID,
    body: PortfolioUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a portfolio."""
    portfolio = await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(portfolio, field, value)
    return portfolio


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete a portfolio and its holdings."""
    portfolio = await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)
    portfolio.soft_delete()
    return None


# =============================================================================
# Portfolio Summary / Consolidated View
# =============================================================================

@router.get("/portfolios/{portfolio_id}/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get detailed summary for a single portfolio including holdings metrics."""
    portfolio = await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)

    # Count holdings
    holdings_result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = holdings_result.scalars().all()
    holdings_count = len(holdings)

    # Calculate weighted yield
    total_value = Decimal("0")
    weighted_yield = Decimal("0")
    next_coupon_total = Decimal("0")
    next_coupon_date = None

    for h in holdings:
        if h.current_value:
            total_value += Decimal(str(h.current_value))
            if h.unrealized_pnl_pct:
                weighted_yield += Decimal(str(h.current_value)) * Decimal(
                    str(h.unrealized_pnl_pct)
                )
            if h.next_coupon_amount:
                next_coupon_total += Decimal(str(h.next_coupon_amount))
            if h.next_coupon_date:
                if next_coupon_date is None or h.next_coupon_date < next_coupon_date:
                    next_coupon_date = h.next_coupon_date

    if total_value > 0:
        weighted_yield = weighted_yield / total_value

    return PortfolioSummary(
        portfolio_id=portfolio.id,
        portfolio_name=portfolio.name,
        total_invested=portfolio.total_invested,
        current_value=portfolio.current_value,
        total_return=Decimal(str(portfolio.current_value)) - Decimal(str(portfolio.total_invested)),
        total_return_pct=portfolio.total_return_pct,
        holdings_count=holdings_count,
        yield_weighted=round(weighted_yield, 2) if total_value > 0 else None,
        next_coupon_total=next_coupon_total if next_coupon_total > 0 else None,
        next_coupon_date=next_coupon_date,
    )


@router.get("/summary/consolidated", response_model=ConsolidatedPortfolioSummary)
async def get_consolidated_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get consolidated view across all family portfolios."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.family_id == current_user.family_id,
            Portfolio.deleted_at.is_(None),
        )
    )
    portfolios = result.scalars().all()

    total_invested = Decimal("0")
    current_value = Decimal("0")
    total_holdings = 0

    breakdown: list[PortfolioSummary] = []

    for portfolio in portfolios:
        # Get holdings count for this portfolio
        h_result = await db.execute(
            select(PortfolioHolding).where(
                PortfolioHolding.portfolio_id == portfolio.id,
                PortfolioHolding.deleted_at.is_(None),
            )
        )
        holdings = h_result.scalars().all()
        h_count = len(holdings)
        total_holdings += h_count

        total_invested += Decimal(str(portfolio.total_invested))
        current_value += Decimal(str(portfolio.current_value))

        breakdown.append(
            PortfolioSummary(
                portfolio_id=portfolio.id,
                portfolio_name=portfolio.name,
                total_invested=portfolio.total_invested,
                current_value=portfolio.current_value,
                total_return=Decimal(str(portfolio.current_value)) - Decimal(
                    str(portfolio.total_invested)
                ),
                total_return_pct=portfolio.total_return_pct,
                holdings_count=h_count,
                yield_weighted=None,
                next_coupon_total=None,
                next_coupon_date=None,
            )
        )

    total_return = current_value - total_invested
    total_return_pct = Decimal("0")
    if total_invested > 0:
        total_return_pct = (total_return / total_invested) * Decimal("100")

    return ConsolidatedPortfolioSummary(
        family_id=current_user.family_id,
        total_portfolios=len(portfolios),
        total_invested=total_invested,
        current_value=current_value,
        total_return=total_return,
        total_return_pct=round(total_return_pct, 2),
        total_holdings=total_holdings,
        weighted_yield=None,
        portfolio_breakdown=breakdown,
    )


# =============================================================================
# Portfolio Holding Endpoints (Family-scoped via portfolio)
# =============================================================================

@router.get("/portfolios/{portfolio_id}/holdings", response_model=List[PortfolioHoldingRead])
async def list_holdings(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List holdings for a portfolio (family-scoped)."""
    await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)

    result = await db.execute(
        select(PortfolioHolding, Instrument, Broker)
        .join(Instrument, PortfolioHolding.instrument_id == Instrument.id, isouter=True)
        .join(Broker, PortfolioHolding.broker_id == Broker.id, isouter=True)
        .where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )

    holdings_read: list[PortfolioHoldingRead] = []
    for row in result.all():
        holding, instrument, broker = row
        holdings_read.append(
            PortfolioHoldingRead(
                id=holding.id,
                portfolio_id=holding.portfolio_id,
                instrument_id=holding.instrument_id,
                instrument_ticker=instrument.ticker if instrument else None,
                instrument_name=instrument.name if instrument else None,
                instrument_type=instrument.instrument_type if instrument else None,
                broker_id=holding.broker_id,
                broker_name=broker.name if broker else None,
                quantity=holding.quantity,
                avg_buy_price=holding.avg_buy_price,
                current_price=holding.current_price,
                current_value=holding.current_value,
                unrealized_pnl=holding.unrealized_pnl,
                unrealized_pnl_pct=holding.unrealized_pnl_pct,
                next_coupon_date=holding.next_coupon_date,
                next_coupon_amount=holding.next_coupon_amount,
            )
        )

    return holdings_read


@router.post(
    "/portfolios/{portfolio_id}/holdings",
    response_model=PortfolioHoldingRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_holding(
    portfolio_id: UUID,
    body: PortfolioHoldingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Add a holding to a portfolio."""
    # Verify portfolio ownership
    await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)

    # Verify instrument exists
    instrument = await _get_instrument_or_404(db, body.instrument_id)

    current_price = instrument.current_price or body.avg_buy_price
    quantity_dec = Decimal(str(body.quantity))
    current_price_dec = Decimal(str(current_price))
    avg_buy_dec = Decimal(str(body.avg_buy_price))

    current_value = quantity_dec * current_price_dec
    invested = quantity_dec * avg_buy_dec
    unrealized_pnl = current_value - invested
    unrealized_pct = Decimal("0")
    if invested > 0:
        unrealized_pct = (unrealized_pnl / invested) * Decimal("100")

    holding = PortfolioHolding(
        portfolio_id=portfolio_id,
        instrument_id=body.instrument_id,
        broker_id=body.broker_id,
        quantity=body.quantity,
        avg_buy_price=body.avg_buy_price,
        current_price=current_price,
        current_value=current_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=round(unrealized_pct, 2),
        next_coupon_date=None,
        next_coupon_amount=None,
    )
    db.add(holding)
    await db.flush()

    # Also create a BUY trade record
    trade = Trade(
        portfolio_id=portfolio_id,
        holding_id=holding.id,
        instrument_id=body.instrument_id,
        broker_id=body.broker_id,
        trade_type="BUY",
        trade_date=date.today(),
        quantity=body.quantity,
        price=body.avg_buy_price,
        total_amount=invested,
        fees=Decimal("0"),
        notes="Initial position",
    )
    db.add(trade)

    return PortfolioHoldingRead(
        id=holding.id,
        portfolio_id=holding.portfolio_id,
        instrument_id=holding.instrument_id,
        instrument_ticker=instrument.ticker,
        instrument_name=instrument.name,
        instrument_type=instrument.instrument_type,
        broker_id=holding.broker_id,
        quantity=holding.quantity,
        avg_buy_price=holding.avg_buy_price,
        current_price=holding.current_price,
        current_value=holding.current_value,
        unrealized_pnl=holding.unrealized_pnl,
        unrealized_pnl_pct=holding.unrealized_pnl_pct,
    )


@router.get("/holdings/{holding_id}", response_model=HoldingWithDetails)
async def get_holding_with_details(
    holding_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Get a holding with its full trade history and instrument details."""
    holding = await _get_holding_or_404(db, holding_id, current_user.family_id)

    # Get instrument details
    instrument_result = await db.execute(
        select(Instrument).where(Instrument.id == holding.instrument_id)
    )
    instrument = instrument_result.scalar_one_or_none()

    # Get broker details
    broker_result = await db.execute(
        select(Broker).where(Broker.id == holding.broker_id)
    )
    broker = broker_result.scalar_one_or_none()

    # Get trades for this holding
    trades_result = await db.execute(
        select(Trade, Broker)
        .join(Broker, Trade.broker_id == Broker.id, isouter=True)
        .where(
            Trade.holding_id == holding_id,
            Trade.deleted_at.is_(None),
        )
        .order_by(Trade.trade_date.desc())
    )

    trades_read: list[TradeRead] = []
    for row in trades_result.all():
        trade, trade_broker = row
        trades_read.append(
            TradeRead(
                id=trade.id,
                portfolio_id=trade.portfolio_id,
                holding_id=trade.holding_id,
                instrument_id=trade.instrument_id,
                broker_id=trade.broker_id,
                broker_name=trade_broker.name if trade_broker else None,
                trade_type=trade.trade_type,
                trade_date=trade.trade_date,
                quantity=trade.quantity,
                price=trade.price,
                total_amount=trade.total_amount,
                fees=trade.fees,
                notes=trade.notes,
            )
        )

    return HoldingWithDetails(
        holding=PortfolioHoldingRead(
            id=holding.id,
            portfolio_id=holding.portfolio_id,
            instrument_id=holding.instrument_id,
            instrument_ticker=instrument.ticker if instrument else None,
            instrument_name=instrument.name if instrument else None,
            instrument_type=instrument.instrument_type if instrument else None,
            broker_id=holding.broker_id,
            broker_name=broker.name if broker else None,
            quantity=holding.quantity,
            avg_buy_price=holding.avg_buy_price,
            current_price=holding.current_price,
            current_value=holding.current_value,
            unrealized_pnl=holding.unrealized_pnl,
            unrealized_pnl_pct=holding.unrealized_pnl_pct,
            next_coupon_date=holding.next_coupon_date,
            next_coupon_amount=holding.next_coupon_amount,
        ),
        trades=trades_read,
        instrument=InstrumentRead.model_validate(instrument) if instrument else None,
    )


@router.put("/holdings/{holding_id}", response_model=PortfolioHoldingRead)
async def update_holding(
    holding_id: UUID,
    body: PortfolioHoldingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Update a holding (e.g., adjust quantity or broker)."""
    holding = await _get_holding_or_404(db, holding_id, current_user.family_id)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(holding, field, value)

    return PortfolioHoldingRead(
        id=holding.id,
        portfolio_id=holding.portfolio_id,
        instrument_id=holding.instrument_id,
        broker_id=holding.broker_id,
        quantity=holding.quantity,
        avg_buy_price=holding.avg_buy_price,
        current_price=holding.current_price,
        current_value=holding.current_value,
        unrealized_pnl=holding.unrealized_pnl,
        unrealized_pnl_pct=holding.unrealized_pnl_pct,
        next_coupon_date=holding.next_coupon_date,
        next_coupon_amount=holding.next_coupon_amount,
    )


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holding(
    holding_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete a holding."""
    holding = await _get_holding_or_404(db, holding_id, current_user.family_id)
    holding.soft_delete()
    return None


# =============================================================================
# Trade Endpoints (Family-scoped via portfolio)
# =============================================================================

@router.get("/portfolios/{portfolio_id}/trades", response_model=List[TradeRead])
async def list_trades(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all trades for a portfolio (family-scoped)."""
    await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)

    result = await db.execute(
        select(Trade, Broker)
        .join(Broker, Trade.broker_id == Broker.id, isouter=True)
        .where(
            Trade.portfolio_id == portfolio_id,
            Trade.deleted_at.is_(None),
        )
        .order_by(Trade.trade_date.desc())
    )

    trades_read: list[TradeRead] = []
    for row in result.all():
        trade, broker = row
        trades_read.append(
            TradeRead(
                id=trade.id,
                portfolio_id=trade.portfolio_id,
                holding_id=trade.holding_id,
                instrument_id=trade.instrument_id,
                broker_id=trade.broker_id,
                broker_name=broker.name if broker else None,
                trade_type=trade.trade_type,
                trade_date=trade.trade_date,
                quantity=trade.quantity,
                price=trade.price,
                total_amount=trade.total_amount,
                fees=trade.fees,
                notes=trade.notes,
            )
        )

    return trades_read


@router.post(
    "/portfolios/{portfolio_id}/trades",
    response_model=TradeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_trade(
    portfolio_id: UUID,
    body: TradeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Record a new trade (buy/sell/coupon) for a portfolio."""
    await _get_portfolio_or_404(db, portfolio_id, current_user.family_id)

    trade = Trade(
        portfolio_id=portfolio_id,
        holding_id=body.holding_id,
        instrument_id=body.instrument_id,
        broker_id=body.broker_id,
        trade_type=body.trade_type,
        trade_date=body.trade_date,
        quantity=body.quantity,
        price=body.price,
        total_amount=body.total_amount,
        fees=body.fees,
        notes=body.notes,
    )
    db.add(trade)
    await db.flush()

    # Get broker name for response
    broker_name = None
    if trade.broker_id:
        broker_result = await db.execute(
            select(Broker).where(Broker.id == trade.broker_id)
        )
        broker = broker_result.scalar_one_or_none()
        broker_name = broker.name if broker else None

    return TradeRead(
        id=trade.id,
        portfolio_id=trade.portfolio_id,
        holding_id=trade.holding_id,
        instrument_id=trade.instrument_id,
        broker_id=trade.broker_id,
        broker_name=broker_name,
        trade_type=trade.trade_type,
        trade_date=trade.trade_date,
        quantity=trade.quantity,
        price=trade.price,
        total_amount=trade.total_amount,
        fees=trade.fees,
        notes=trade.notes,
    )