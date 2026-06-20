"""
plan_engine.py
==============
Investment plan engine — instrument analysis, buy window, swap opportunities.
Ported from Claude AI version (Sessions S9-S10, 42 tests passing).

Core functions (PURE, no DB):
  - instrument_real_yield() — YTM pipeline: gross → net (IAC) → real (Fisher)
  - buy_window()            — COMPRAR vs AGUARDAR decision
  - classify_plan_instruments() — reconcile plan instruments vs real holdings
  - swap_benefit()          — net benefit of swapping bond H for bond C
  - is_swap_recommended()   — liquidity + gain thresholds

Async orchestrators:
  - evaluate_plan()         — plan table with prices, yields, buy windows
  - find_swaps()            — scan candidate universe for swap opportunities
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Set

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bodiva_market import BondMaster, MarketSnapshot, OrderBookSnapshot
from app.models.portfolio_holding import PortfolioHolding
from app.models.portfolio import Portfolio
from app.models.investment_signal import InvestmentSignal, SignalType, SignalSeverity

from .financial_core import (
    D, parse_date, years_between,
    generate_cash_flows, solve_ytm, yield_after_tax, fisher_real,
)

# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════
FIXED_INCOME = ("BOND_GOV", "BOND_CORP", "TBILL")
MAX_PRICE_AGE_DAYS = 30
MIN_SWAP_MATURITY_YEARS = 0.5

# ═══════════════════════════════════════════════════════════════════════════
# PURE FUNCTIONS — testable without DB
# ═══════════════════════════════════════════════════════════════════════════

def instrument_real_yield(
    *,
    par_value: float,
    coupon_rate: float,
    years_to_maturity: float,
    frequency_n: int,
    market_price_pct: float,
    inflation: float,
    iac_rate: float,
) -> Dict[str, Optional[float]]:
    """
    YTM pipeline: gross → net (after IAC) → real (Fisher).
    Returns {"ytm", "net_yield", "real_yield"} in decimal (e.g. 0.18 = 18%).
    """
    none = {"ytm": None, "net_yield": None, "real_yield": None}
    if not market_price_pct or not par_value or not coupon_rate or years_to_maturity <= 0:
        return none

    cfs = generate_cash_flows(
        D(par_value), D(coupon_rate), D(years_to_maturity),
        int(frequency_n or 2), coupon_tax_rate=D(0),  # GROSS — tax applied later
    )
    if not cfs:
        return none

    pairs = [(D(c["t_years"]), D(c["total_flow"])) for c in cfs]
    price = D(par_value) * D(market_price_pct) / D(100)
    if price <= 0:
        return none

    ytm = solve_ytm(pairs, price)
    net = yield_after_tax(ytm, D(iac_rate))
    real = fisher_real(net, D(inflation))
    return {"ytm": float(ytm), "net_yield": float(net), "real_yield": float(real)}


def buy_window(
    *,
    real_yield: Optional[float],
    objective_real_yield: Optional[float],
    cap_entry: Optional[float],
    spread_pct: Optional[float] = None,
    max_spread_pct: float = 2.0,
    min_cap_entry: float = 1.0,
    price_is_stale: bool = False,
) -> Dict[str, Any]:
    """
    Decide COMPRAR vs AGUARDAR for an instrument.

    All conditions must be true for COMPRAR:
      1. real_yield >= objective_real_yield
      2. cap_entry >= min_cap_entry (liquidity to enter)
      3. spread_pct <= max_spread_pct (or no spread data)
      4. price is NOT stale (< MAX_PRICE_AGE_DAYS)
    """
    yield_ok = (
        real_yield is not None and objective_real_yield is not None
        and real_yield >= objective_real_yield
    )
    liq_ok = (cap_entry is not None and cap_entry >= min_cap_entry)
    spread_ok = (spread_pct is None) or (spread_pct <= max_spread_pct)

    reasons: list[str] = []
    reasons.append("yield real >= objetivo" if yield_ok else "yield real abaixo do objetivo")
    reasons.append("liquidez suficiente para entrar" if liq_ok else "liquidez insuficiente no order book")
    if spread_pct is not None and not spread_ok:
        reasons.append("spread demasiado largo")
    if price_is_stale:
        reasons.append("preco desatualizado")

    status = "COMPRAR" if (yield_ok and liq_ok and spread_ok and not price_is_stale) else "AGUARDAR"
    return {"status": status, "yield_ok": yield_ok, "liq_ok": liq_ok,
            "spread_ok": spread_ok, "reasons": reasons}


def classify_plan_instruments(
    plan_rows: List[Dict[str, Any]],
    real_tickers: Set[str],
) -> List[Dict[str, Any]]:
    """Mark each plan instrument as 'realizado' or 'pendente' based on real holdings."""
    return [
        {
            **r,
            "estado": "realizado" if r.get("ticker") in real_tickers else "pendente",
            "na_carteira_real": r.get("ticker") in real_tickers,
        }
        for r in plan_rows
    ]


def swap_benefit(
    *,
    h_clean_value: float,
    h_accrued_net: float,
    h_acquisition_clean: float,
    h_real_yield: float,
    h_capgain_rate: float,
    c_real_yield: float,
    commission_pct: float,
    horizon_years: float,
) -> Dict[str, Any]:
    """
    Net benefit of swapping bond H (held) for bond C (candidate).

    Steps:
      P = dirty_value − sell_comm − capgain_tax   (net proceeds)
      V_keep  = dirty × (1 + yield_H)^T             (keep H)
      V_swap  = (P / (1 + commission)) × (1 + yield_C)^T   (buy C)
      Gain    = V_swap − V_keep
    """
    Dh = D(h_clean_value)
    dirty = Dh + D(h_accrued_net)
    sell_comm = dirty * D(commission_pct)
    gain = Dh - D(h_acquisition_clean)
    capgain_tax = (gain * D(h_capgain_rate)) if gain > 0 else D(0)
    P = dirty - sell_comm - capgain_tax

    T = D(horizon_years)
    invested_c = P / (D(1) + D(commission_pct))
    v_keep = dirty * (D(1) + D(h_real_yield)) ** T
    v_swap = invested_c * (D(1) + D(c_real_yield)) ** T
    ganho = v_swap - v_keep

    return {
        "dirty_value": float(dirty),
        "sell_commission": float(sell_comm),
        "capital_gain": float(gain),
        "capgain_tax": float(capgain_tax),
        "net_proceeds": float(P),
        "invested_in_c": float(invested_c),
        "v_keep": float(v_keep),
        "v_swap": float(v_swap),
        "swap_gain": float(ganho),
        "switching_cost": float(dirty - P),
    }


def is_swap_recommended(
    swap: Dict[str, Any],
    *,
    cap_exit_h: Optional[float],
    cap_entry_c: Optional[float],
    min_gain_pct: float = 1.0,
    min_cap: float = 1.0,
) -> Dict[str, Any]:
    """Apply liquidity + gain thresholds to swap result."""
    base = swap["dirty_value"] or 1.0
    gain_pct = (swap["swap_gain"] / base * 100.0) if base else 0.0
    gain_ok = gain_pct >= min_gain_pct
    exit_ok = (cap_exit_h is not None and cap_exit_h >= min_cap)
    entry_ok = (cap_entry_c is not None and cap_entry_c >= min_cap)
    return {
        "recommended": bool(gain_ok and exit_ok and entry_ok),
        "gain_pct": gain_pct,
        "gain_ok": gain_ok,
        "exit_ok": exit_ok,
        "entry_ok": entry_ok,
    }


# ═══════════════════════════════════════════════════════════════════════════
# ASYNC ORCHESTRATORS — DB-dependent
# ═══════════════════════════════════════════════════════════════════════════

def _is_stale(price_date, today=None) -> bool:
    """True if price is older than MAX_PRICE_AGE_DAYS."""
    if not price_date:
        return False
    d = parse_date(price_date)
    if not d:
        return False
    today = today or date.today()
    return (today - d).days > MAX_PRICE_AGE_DAYS


async def _order_book_price_pct(
    db: AsyncSession,
    ticker: str,
    side: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Price from order book, aware of side (ask=buy, bid=sell)."""
    # Get the latest date
    latest_result = await db.execute(
        select(OrderBookSnapshot.snapshot_date)
        .where(OrderBookSnapshot.ticker == ticker, OrderBookSnapshot.price.isnot(None))
        .order_by(desc(OrderBookSnapshot.snapshot_date))
        .limit(1)
    )
    latest_date = latest_result.scalar_one_or_none()
    if not latest_date:
        return None

    rows_result = await db.execute(
        select(OrderBookSnapshot)
        .where(
            OrderBookSnapshot.ticker == ticker,
            OrderBookSnapshot.snapshot_date == latest_date,
            OrderBookSnapshot.price.isnot(None),
        )
    )
    rows = rows_result.scalars().all()

    best_bid = best_ask = last_quote = None
    for r in rows:
        s = (r.side or "").upper()
        p = r.price
        if r.last_quote is not None:
            last_quote = float(r.last_quote)
        if p is None:
            continue
        if s == "BID":
            best_bid = p if best_bid is None else max(best_bid, p)
        elif s == "ASK":
            best_ask = p if best_ask is None else min(best_ask, p)

    s = (side or "").lower()
    if s == "ask":
        price = best_ask if best_ask is not None else (last_quote or best_bid)
    elif s == "bid":
        price = best_bid if best_bid is not None else (last_quote or best_ask)
    elif best_bid is not None and best_ask is not None:
        price = (best_bid + best_ask) / 2.0
    elif last_quote:
        price = last_quote
    elif best_ask is not None:
        price = best_ask
    elif best_bid is not None:
        price = best_bid
    else:
        price = None

    if price is None:
        return None
    return {"price": float(price), "date": latest_date}


async def _resolve_price_pct(
    db: AsyncSession,
    ticker: str,
    side: Optional[str] = None,
    allow_order_book: bool = True,
) -> Dict[str, Any]:
    """Resolve price with fallback: market_snapshots → order book."""
    ms_result = await db.execute(
        select(MarketSnapshot)
        .where(MarketSnapshot.ticker == ticker, MarketSnapshot.price.isnot(None))
        .order_by(desc(MarketSnapshot.snapshot_date), desc(MarketSnapshot.snapshot_time))
        .limit(1)
    )
    ms = ms_result.scalar_one_or_none()
    if ms and ms.price:
        return {"price": float(ms.price), "date": ms.snapshot_date, "source": "snapshot"}

    if allow_order_book:
        ob = await _order_book_price_pct(db, ticker, side=side)
        if ob:
            return {"price": ob["price"], "date": ob["date"], "source": "order_book"}

    return {"price": None, "date": None, "source": None}


async def evaluate_plan(
    db: AsyncSession,
    portfolio_id: str,
    inflation: float,
    objective_real_yield: float,
) -> List[Dict[str, Any]]:
    """
    Plan table: for each instrument in the portfolio, compute:
      - current market price (side=ask for entry)
      - real yield
      - buy window decision
      - reconciliation against real holdings
    """
    # Fetch portfolio holdings
    ph_result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = ph_result.scalars().all()

    # Fetch real holdings tickers (across all real portfolios)
    real_result = await db.execute(
        select(Portfolio.ticker).where(Portfolio.portfolio_type == "REAL")
    )
    real_tickers = {r[0] for r in real_result.all() if r[0]}

    rows: list[dict] = []
    for h in holdings:
        # Get ticker from instrument_id
        ticker = None
        if h.instrument_id:
            instr = await db.execute(
                select(BondMaster).where(BondMaster.ticker == getattr(h, "ticker", None))
            )
            master = instr.scalar_one_or_none()
            if master:
                ticker = master.ticker

        if not ticker:
            continue

        pinfo = await _resolve_price_pct(db, ticker, side="ask")
        price = pinfo["price"]
        stale = _is_stale(pinfo["date"])

        # Compute real yield
        master = await db.execute(
            select(BondMaster).where(BondMaster.ticker == ticker)
        )
        bond = master.scalar_one_or_none()

        ry = None
        ytm_val = None
        if bond and bond.par_value and bond.coupon_rate and bond.maturity_date:
            years = years_between(parse_date(bond.issue_date), parse_date(bond.maturity_date))
            if years and years > 0 and price:
                from .tax_engine import resolve_for_bond
                try:
                    rates = await resolve_for_bond(
                        db, {"ticker": ticker, "instrument_class": bond.instrument_class or "BOND_GOV",
                             "bodiva_admitted": bond.bodiva_admitted},
                    )
                    iac_rate = float(rates["coupon_tax_rate"])
                except Exception:
                    iac_rate = 0.10

                ry = instrument_real_yield(
                    par_value=float(bond.par_value),
                    coupon_rate=float(bond.coupon_rate),
                    years_to_maturity=years,
                    frequency_n=bond.frequency_n or 2,
                    market_price_pct=price,
                    inflation=inflation,
                    iac_rate=iac_rate,
                )
                ytm_val = ry["ytm"]

        real_yield = ry["real_yield"] if ry else None
        win = buy_window(
            real_yield=real_yield,
            objective_real_yield=objective_real_yield,
            cap_entry=1.0,  # simplified for MVP
            price_is_stale=stale,
        )

        rows.append({
            "ticker": ticker,
            "name": getattr(bond, "title", ticker) if bond else ticker,
            "market_price_pct": price,
            "real_yield": real_yield,
            "ytm": ytm_val,
            "estado": "realizado" if ticker in real_tickers else "pendente",
            "na_carteira_real": ticker in real_tickers,
            "janela": win["status"],
            "janela_motivos": win["reasons"],
            "price_date": str(pinfo["date"]) if pinfo["date"] else None,
            "price_source": pinfo["source"],
            "preco_desatualizado": stale,
        })

    return rows


async def find_swaps(
    db: AsyncSession,
    portfolio_id: str,
    inflation: float,
    horizon_years: float,
    commission_pct: float = 0.00395,
    min_gain_pct: float = 1.0,
    top_per_holding: int = 1,
) -> List[Dict[str, Any]]:
    """
    Find swap opportunities: for each held bond, search BODIVA universe
    for better candidates. Returns ranked list with breakdown + recommendation.
    """
    # Fetch holdings
    ph_result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = ph_result.scalars().all()

    # Universe: all bonds in BondMaster
    universe_result = await db.execute(
        select(BondMaster).where(
            BondMaster.instrument_class.in_(FIXED_INCOME)
        )
    )
    universe = universe_result.scalars().all()

    out: list[dict] = []
    for h in holdings:
        ticker = getattr(h, "ticker", None)
        if not ticker:
            continue

        hb_result = await db.execute(
            select(BondMaster).where(BondMaster.ticker == ticker)
        )
        hb = hb_result.scalar_one_or_none()
        if not hb or hb.instrument_class not in FIXED_INCOME:
            continue

        h_yrs = years_between(parse_date(hb.issue_date), parse_date(hb.maturity_date))
        if h_yrs is None or h_yrs < MIN_SWAP_MATURITY_YEARS:
            continue

        h_price_info = await _resolve_price_pct(db, ticker, side="bid")
        h_price = h_price_info.get("price")
        if not h_price:
            continue

        from .tax_engine import resolve_for_bond
        try:
            h_rates = await resolve_for_bond(
                db, {"ticker": ticker, "instrument_class": hb.instrument_class or "BOND_GOV",
                     "bodiva_admitted": hb.bodiva_admitted},
            )
            h_iac = float(h_rates["coupon_tax_rate"])
        except Exception:
            h_iac = 0.10

        h_ry = instrument_real_yield(
            par_value=float(hb.par_value or 100000),
            coupon_rate=float(hb.coupon_rate or 0),
            years_to_maturity=h_yrs,
            frequency_n=hb.frequency_n or 2,
            market_price_pct=h_price,
            inflation=inflation,
            iac_rate=h_iac,
        )
        if not h_ry.get("real_yield"):
            continue

        qty = float(h.quantity or 0)
        par = float(hb.par_value or 100000)
        h_clean = (qty * par * h_price / 100.0) if h_price else float(h.current_value or 0)
        h_acq = float(h.avg_buy_price or 0) * qty if h.avg_buy_price else h_clean

        cands: list[dict] = []
        for cb in universe:
            ct = cb.ticker
            if not ct or ct == ticker:
                continue

            c_yrs = years_between(parse_date(cb.issue_date), parse_date(cb.maturity_date))
            if c_yrs is None or c_yrs < MIN_SWAP_MATURITY_YEARS:
                continue

            cinfo = await _resolve_price_pct(db, ct, side="ask")
            c_price = cinfo.get("price")
            if not c_price or _is_stale(cinfo.get("date")):
                continue

            try:
                c_rates = await resolve_for_bond(
                    db, {"ticker": ct, "instrument_class": cb.instrument_class or "BOND_GOV",
                         "bodiva_admitted": cb.bodiva_admitted},
                )
                c_iac = float(c_rates["coupon_tax_rate"])
            except Exception:
                c_iac = 0.10

            c_ry = instrument_real_yield(
                par_value=float(cb.par_value or 100000),
                coupon_rate=float(cb.coupon_rate or 0),
                years_to_maturity=c_yrs,
                frequency_n=cb.frequency_n or 2,
                market_price_pct=c_price,
                inflation=inflation,
                iac_rate=c_iac,
            )
            if not c_ry.get("real_yield"):
                continue

            sb = swap_benefit(
                h_clean_value=h_clean,
                h_accrued_net=0.0,
                h_acquisition_clean=h_acq,
                h_real_yield=h_ry["real_yield"],
                h_capgain_rate=0.10,
                c_real_yield=c_ry["real_yield"],
                commission_pct=commission_pct,
                horizon_years=horizon_years,
            )
            rec = is_swap_recommended(sb, cap_exit_h=1.0, cap_entry_c=1.0, min_gain_pct=min_gain_pct)
            cands.append({
                "sell": ticker, "sell_name": hb.title or ticker,
                "buy": ct, "buy_name": cb.title or ct,
                "h_real_yield": h_ry["real_yield"],
                "c_real_yield": c_ry["real_yield"],
                "buy_price_date": str(cinfo.get("date")) if cinfo.get("date") else None,
                **sb, **rec,
            })

        cands.sort(key=lambda x: (x["recommended"], x["entry_ok"], x["swap_gain"]), reverse=True)
        out.extend(cands[:top_per_holding] if top_per_holding else cands)

    out.sort(key=lambda x: (x["recommended"], x["entry_ok"], x["swap_gain"]), reverse=True)
    return out
