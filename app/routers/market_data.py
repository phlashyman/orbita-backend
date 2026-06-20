"""
Market data router — SerpAPI proxy (global) + BODIVA local endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.market_data import (
    get_indices,
    get_currencies,
    get_movers,
    get_quote,
    search_quote,
)

router = APIRouter(prefix="/market-data", tags=["Market Data"])


# ---------------------------------------------------------------------------
# BODIVA local data schemas
# ---------------------------------------------------------------------------

class BodivaInstrument(BaseModel):
    ticker: str
    instrument_class: Optional[str] = None
    price: Optional[float] = None
    var_daily_pct: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    volume_qty: Optional[float] = None
    volume_aoa: Optional[float] = None
    n_trades_day: Optional[int] = None
    currency: str = "AOA"
    snapshot_date: Optional[str] = None
    source: Optional[str] = None
    # from bond_master
    title: Optional[str] = None
    issuer: Optional[str] = None
    coupon_rate: Optional[float] = None
    maturity_date: Optional[str] = None
    tax_regime: Optional[str] = None
    gross_yield: Optional[float] = None


class BodivaOrderBookRow(BaseModel):
    ticker: str
    side: str
    level: int
    price: Optional[float] = None
    quantity: Optional[float] = None
    yield_pct: Optional[float] = None
    snapshot_date: Optional[str] = None


class BodivaYieldPoint(BaseModel):
    maturity_label: str
    yield_pct: Optional[float] = None
    var_pp_vs_yesterday: Optional[float] = None
    currency: str = "AOA"


# ---------------------------------------------------------------------------
# BODIVA endpoints — query local market_snapshots / order_book_snapshots
# ---------------------------------------------------------------------------

@router.get("/bodiva/instruments", response_model=List[BodivaInstrument])
async def bodiva_instruments(db: AsyncSession = Depends(get_db)):
    """Latest BODIVA market snapshot per ticker (most recent date)."""
    try:
        result = await db.execute(text("""
            SELECT DISTINCT ON (ms.ticker)
                ms.ticker,
                ms.instrument_class,
                ms.price,
                ms.var_daily_pct,
                ms.best_bid,
                ms.best_ask,
                ms.volume_qty,
                ms.volume_aoa,
                ms.n_trades_day,
                ms.currency,
                ms.snapshot_date::text AS snapshot_date,
                ms.source,
                bm.title,
                bm.issuer,
                bm.coupon_rate,
                bm.maturity_date::text AS maturity_date,
                bm.tax_regime
            FROM market_snapshots ms
            LEFT JOIN bond_master bm ON bm.ticker = ms.ticker
            ORDER BY ms.ticker, ms.snapshot_date DESC, ms.imported_at DESC
        """))
        rows = result.mappings().all()
        return [BodivaInstrument(**dict(r)) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar instrumentos BODIVA: {e}")


@router.get("/bodiva/order-book", response_model=List[BodivaOrderBookRow])
async def bodiva_order_book(
    ticker: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Latest order book snapshot. Optionally filter by ticker."""
    try:
        latest_date = await db.execute(text(
            "SELECT MAX(snapshot_date) FROM order_book_snapshots"
            + (" WHERE ticker = :t" if ticker else "")
        ), ({"t": ticker.upper()} if ticker else {}))
        snap_date = latest_date.scalar()
        if not snap_date:
            return []

        q = text("""
            SELECT ticker, side, level, price, quantity, yield_pct,
                   snapshot_date::text AS snapshot_date
            FROM order_book_snapshots
            WHERE snapshot_date = :d
              AND (:ticker IS NULL OR ticker = :ticker)
            ORDER BY ticker, side, level
        """)
        result = await db.execute(q, {"d": snap_date, "ticker": ticker.upper() if ticker else None})
        rows = result.mappings().all()
        return [BodivaOrderBookRow(**dict(r)) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar livro de ordens: {e}")


@router.get("/bodiva/yield-curve", response_model=List[BodivaYieldPoint])
async def bodiva_yield_curve(
    currency: str = Query("AOA"),
    db: AsyncSession = Depends(get_db),
):
    """Yield curve for most recent snapshot date."""
    try:
        latest = await db.execute(text(
            "SELECT MAX(snapshot_date) FROM yield_curve_history WHERE currency = :c"
        ), {"c": currency.upper()})
        snap_date = latest.scalar()
        if not snap_date:
            return []

        result = await db.execute(text("""
            SELECT maturity_label, yield_pct, var_pp_vs_yesterday, currency
            FROM yield_curve_history
            WHERE snapshot_date = :d AND currency = :c
            ORDER BY CASE maturity_label
                WHEN '3M' THEN 1 WHEN '6M' THEN 2 WHEN '1Y' THEN 3
                WHEN '2Y' THEN 4 WHEN '3Y' THEN 5 WHEN '4Y' THEN 6
                WHEN '5Y' THEN 7 WHEN '7Y' THEN 8 WHEN '10Y' THEN 9
                ELSE 99 END
        """), {"d": snap_date, "c": currency.upper()})
        rows = result.mappings().all()
        return [BodivaYieldPoint(**dict(r)) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar curva de rendimentos: {e}")


@router.get("/bodiva/summary")
async def bodiva_summary(db: AsyncSession = Depends(get_db)):
    """Quick stats: latest snapshot date, number of instruments, total volume."""
    try:
        r = await db.execute(text("""
            SELECT
                MAX(snapshot_date)::text AS latest_date,
                COUNT(DISTINCT ticker) AS n_instruments,
                SUM(volume_aoa) AS total_volume_aoa
            FROM (
                SELECT DISTINCT ON (ticker) ticker, snapshot_date, volume_aoa
                FROM market_snapshots
                ORDER BY ticker, snapshot_date DESC
            ) latest
        """))
        row = r.mappings().first()
        if not row:
            return {"latest_date": None, "n_instruments": 0, "total_volume_aoa": 0}
        return dict(row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro: {e}")


@router.get("/indices")
async def indices():
    """Major global indices (US, Europe, Asia, LatAm)."""
    try:
        return await get_indices()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Market data unavailable: {e}")


@router.get("/currencies")
async def currencies():
    """Major currency pairs."""
    try:
        return await get_currencies()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Market data unavailable: {e}")


@router.get("/movers")
async def movers(
    trend: str = Query("most-active", pattern="^(most-active|gainers|losers)$")
):
    """Top movers: most-active | gainers | losers."""
    try:
        return await get_movers(trend)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Market data unavailable: {e}")


@router.get("/quote/{exchange}/{ticker}")
async def quote(exchange: str, ticker: str):
    """Single quote lookup, e.g. /quote/NASDAQ/AAPL or /quote/JSE/NPN."""
    try:
        result = await get_quote(ticker.upper(), exchange.upper())
        if result is None:
            raise HTTPException(status_code=404, detail="Ticker not found on this exchange.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Market data unavailable: {e}")


@router.get("/search")
async def search(q: str = Query(..., min_length=1, max_length=100)):
    """Search by company name or ticker."""
    try:
        result = await search_quote(q)
        if result is None:
            raise HTTPException(status_code=404, detail="No results found.")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Market data unavailable: {e}")
