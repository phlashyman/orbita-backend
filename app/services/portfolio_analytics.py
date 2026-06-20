"""
portfolio_analytics.py
======================
Portfolio-level investment analytics — the heart of Orbita's intelligence layer.

Computes:
  - Risk metrics:       VaR, CVaR (Expected Shortfall)
  - Risk-adjusted return: Sharpe, Sortino, Calmar, Information Ratio
  - Duration & convexity: Macaulay, Modified, Convexity (bond portfolios)
  - Concentration:      HHI, Gini coefficient, Effective N
  - Liquidity:          Spread-based score, estimated slippage
  - Drawdown analysis:  Max drawdown %, duration

All core math is PURE (testable without DB). Orchestration is async via SQLAlchemy.
Uses financial_core.py for YTM, duration, Fisher, and tax_engine.py for IAC.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple, Any

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio
from app.models.portfolio_holding import PortfolioHolding
from app.models.portfolio_analytics import PortfolioAnalytics
from app.models.bodiva_market import MarketSnapshot, OrderBookSnapshot, BondMaster
from app.models.country_risk_metric import CountryRiskMetric
from app.models.instrument import Instrument

from .financial_core import (
    D, parse_date, freq_n, years_between,
    fisher_real, solve_ytm, calc_duration, price_impact_yield_shock,
    generate_cash_flows,
)
from .tax_engine import resolve_for_bond, get_active_iac_rate

# ═══════════════════════════════════════════════════════════════════════════
# Pure calculation functions — testable without DB
# ═══════════════════════════════════════════════════════════════════════════

# ── Value-at-Risk ─────────────────────────────────────────────────────────

def calc_var_parametric(position_values: List[float], confidence: float = 0.95) -> Dict[str, float]:
    """
    Parametric VaR assuming normal distribution of returns.
    VaR = z_score * sigma * portfolio_value

    Returns {var_value, var_pct, z_score}.
    For an illiquid market like BODIVA, parametric VaR is an approximation.
    """
    if not position_values or len(position_values) < 2:
        return {"var_value": 0.0, "var_pct": 0.0, "z_score": 0.0}

    portfolio_value = sum(position_values)
    if portfolio_value <= 0:
        return {"var_value": 0.0, "var_pct": 0.0, "z_score": 0.0}

    # Compute daily returns (naive: pairwise differences)
    returns = []
    for i in range(1, len(position_values)):
        if position_values[i - 1] > 0:
            r = (position_values[i] - position_values[i - 1]) / position_values[i - 1]
            returns.append(r)

    if not returns:
        return {"var_value": 0.0, "var_pct": 0.0, "z_score": 0.0}

    mu = sum(returns) / len(returns)
    sigma = math.sqrt(sum((r - mu) ** 2 for r in returns) / (len(returns) - 1)) if len(returns) > 1 else 0.0

    # z-score for confidence level
    z_scores = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
    z = z_scores.get(confidence, 1.645)

    # 1-month VaR: scale daily σ by √21 (trading days)
    var_pct = z * sigma * math.sqrt(21)
    var_value = portfolio_value * var_pct

    return {"var_value": abs(float(var_value)), "var_pct": abs(float(var_pct)), "z_score": z}


def calc_var_historic(position_values: List[float], confidence: float = 0.95) -> Dict[str, float]:
    """
    Historic VaR: actual percentile of observed negative returns.
    Works even with non-normal distributions (important for frontier markets).
    """
    if not position_values or len(position_values) < 2:
        return {"var_value": 0.0, "var_pct": 0.0}

    portfolio_value = sum(position_values)
    if portfolio_value <= 0:
        return {"var_value": 0.0, "var_pct": 0.0}

    returns = []
    for i in range(1, len(position_values)):
        if position_values[i - 1] > 0:
            r = (position_values[i] - position_values[i - 1]) / position_values[i - 1]
            returns.append(r)

    if not returns:
        return {"var_value": 0.0, "var_pct": 0.0}

    sorted_returns = sorted(returns)
    idx = max(0, int(len(sorted_returns) * (1 - confidence)))
    var_ret = abs(sorted_returns[idx])
    var_value = portfolio_value * var_ret * math.sqrt(21)

    return {"var_value": float(var_value), "var_pct": float(var_ret) * math.sqrt(21)}


def calc_cvar(position_values: List[float], confidence: float = 0.95) -> Dict[str, float]:
    """
    Conditional VaR (Expected Shortfall): average loss beyond VaR.
    More informative than VaR for fat-tailed frontier market distributions.
    """
    if not position_values or len(position_values) < 2:
        return {"cvar_value": 0.0, "cvar_pct": 0.0}

    portfolio_value = sum(position_values)
    if portfolio_value <= 0:
        return {"cvar_value": 0.0, "cvar_pct": 0.0}

    returns = []
    for i in range(1, len(position_values)):
        if position_values[i - 1] > 0:
            r = (position_values[i] - position_values[i - 1]) / position_values[i - 1]
            returns.append(r)

    if not returns:
        return {"cvar_value": 0.0, "cvar_pct": 0.0}

    sorted_returns = sorted(returns)
    cutoff = max(1, int(len(sorted_returns) * (1 - confidence)))  # at least 1 in tail
    tail = sorted_returns[:cutoff]
    if not tail:
        return {"cvar_value": 0.0, "cvar_pct": 0.0}

    avg_tail = abs(sum(tail) / len(tail))
    cvar_pct = avg_tail * math.sqrt(21)
    cvar_value = portfolio_value * cvar_pct

    return {"cvar_value": float(cvar_value), "cvar_pct": float(cvar_pct)}


# ── Risk-Adjusted Returns ─────────────────────────────────────────────────

def calc_sharpe_ratio(
    portfolio_return: float,
    risk_free_rate: float,
    portfolio_volatility: float,
) -> Optional[float]:
    """
    Sharpe = (R_p - R_f) / sigma_p

    For Angola: R_f ≈ BNA rate − IAC (real return risk-free approximation).
    Negative Sharpe is possible if portfolio underperforms risk-free.
    """
    if not portfolio_volatility or portfolio_volatility <= 0:
        return None
    return (portfolio_return - risk_free_rate) / portfolio_volatility


def calc_sortino_ratio(
    returns: List[float],
    risk_free_rate: float,
) -> Optional[float]:
    """
    Sortino = (R_p - R_f) / sigma_downside
    Penalizes only negative volatility — more relevant for risk-averse investors.
    """
    if not returns or len(returns) < 2:
        return None

    mu = sum(returns) / len(returns)
    downside = [(r - risk_free_rate) for r in returns if r < risk_free_rate]
    if not downside:
        return 0.0

    # Population downside deviation
    variance = sum((d - risk_free_rate) ** 2 for d in downside) / len(downside)
    sigma_d = math.sqrt(variance)
    if sigma_d <= 0:
        return None

    return (mu - risk_free_rate) / sigma_d


def calc_calmar_ratio(
    portfolio_return: float,
    max_drawdown_pct: float,
) -> Optional[float]:
    """
    Calmar = (R_p - R_f) / max_drawdown
    Useful in high-inflation environments where drawdown protection matters.
    """
    if not max_drawdown_pct or max_drawdown_pct <= 0:
        return None
    return portfolio_return / abs(max_drawdown_pct)


def calc_information_ratio(
    portfolio_returns: List[float],
    benchmark_returns: List[float],
) -> Optional[float]:
    """
    IR = (R_p - R_b) / tracking_error
    Measures value added vs. a benchmark (e.g. OT index).
    """
    if not portfolio_returns or not benchmark_returns:
        return None
    if len(portfolio_returns) != len(benchmark_returns):
        return None

    diffs = [p - b for p, b in zip(portfolio_returns, benchmark_returns)]
    if len(diffs) < 2:
        return None

    mu_diff = sum(diffs) / len(diffs)
    te = math.sqrt(sum((d - mu_diff) ** 2 for d in diffs) / (len(diffs) - 1))
    if te <= 0:
        return None

    return mu_diff / te


# ── Concentration ─────────────────────────────────────────────────────────

def calc_concentration_hhi(weights: List[float]) -> float:
    """
    Hirschman-Herfindahl Index: sum of squared weights.
    HHI < 0.10 → well-diversified
    HHI > 0.25 → concentrated
    """
    if not weights:
        return 0.0
    total = sum(weights)
    if total <= 0:
        return 0.0
    normalised = [w / total for w in weights]
    return sum(w ** 2 for w in normalised)


def calc_concentration_gini(weights: List[float]) -> float:
    """
    Gini coefficient over position weights.
    0 = perfect equality, 1 = total inequality.
    """
    if not weights or len(weights) < 2:
        return 0.0

    sorted_w = sorted(w for w in weights if w > 0)
    if not sorted_w:
        return 0.0

    n = len(sorted_w)
    total = sum(sorted_w)
    if total <= 0:
        return 0.0

    # Sum of absolute differences
    sum_diff = 0.0
    for i, wi in enumerate(sorted_w):
        for j, wj in enumerate(sorted_w):
            sum_diff += abs(wi - wj)

    gini = sum_diff / (2 * n * n * (total / n))
    return gini


def calc_effective_n(hhi: float) -> float:
    """Effective N = 1/HHI — number of equally-weighted positions."""
    if hhi <= 0:
        return 0.0
    return 1.0 / hhi


# ── Liquidity ─────────────────────────────────────────────────────────────

def calc_liquidity_score(
    bid: Optional[float],
    ask: Optional[float],
    volume_qty: Optional[float],
) -> Dict[str, float]:
    """
    Liquidity score based on bid-ask spread and available depth.
    Score = (1 / spread_pct) * sqrt(volume) → higher = more liquid.
    """
    if not bid or not ask or bid <= 0 or ask <= 0:
        return {"score": 0.0, "spread_pct": None, "depth": None}

    spread_pct = (ask - bid) / ((bid + ask) / 2)
    vol = volume_qty or 0

    # Score heuristic: inverse spread × log depth
    if spread_pct > 0:
        score = (1.0 / spread_pct) * math.log(vol + 1)
    else:
        score = math.log(vol + 1) * 100  # zero spread → very liquid

    return {"score": float(score), "spread_pct": float(spread_pct), "depth": float(vol)}


def calc_slippage_estimate(
    quantity: float,
    bid_volumes: List[float],
    bid_prices: List[float],
) -> Dict[str, float]:
    """
    Estimate slippage: how much the price moves if you sell `quantity` units.
    Walks the order book levels until the full quantity is absorbed.
    """
    if not quantity or quantity <= 0 or not bid_volumes:
        return {"slippage_pct": 0.0, "slippage_value": 0.0, "levels_consumed": 0}

    remaining = quantity
    weighted_price = 0.0
    consumed_levels = 0

    for i, (vol, price) in enumerate(zip(bid_volumes, bid_prices)):
        if vol <= 0 or not price:
            continue
        taken = min(remaining, vol)
        weighted_price += taken * price
        remaining -= taken
        consumed_levels += 1
        if remaining <= 0:
            break

    if consumed_levels == 0:
        return {"slippage_pct": 0.0, "slippage_value": 0.0, "levels_consumed": 0}

    avg_exec_price = weighted_price / (quantity - remaining)
    best_price = bid_prices[0] if bid_prices and bid_prices[0] else avg_exec_price

    if best_price and best_price > 0:
        slippage_pct = (best_price - avg_exec_price) / best_price
    else:
        slippage_pct = 0.0

    return {
        "slippage_pct": float(slippage_pct),
        "slippage_value": float(slippage_pct * (quantity * best_price)),
        "levels_consumed": consumed_levels,
    }


# ── Drawdown ──────────────────────────────────────────────────────────────

def calc_drawdown(values: List[float]) -> Dict[str, float]:
    """
    Peak-to-trough drawdown from an equity curve.
    Returns {max_drawdown_pct, max_drawdown_days, current_drawdown_pct}.
    """
    if not values or len(values) < 2:
        return {"max_drawdown_pct": 0.0, "max_drawdown_days": 0, "current_drawdown_pct": 0.0}

    peak = values[0]
    max_dd_pct = 0.0
    max_dd_days = 0
    current_dd_start = 0
    current_dd_pct = 0.0

    for i, v in enumerate(values):
        if v > peak:
            peak = v
            current_dd_start = i
        dd_pct = (peak - v) / peak if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_days = i - current_dd_start
        if i == len(values) - 1:
            current_dd_pct = dd_pct

    return {
        "max_drawdown_pct": float(max_dd_pct),
        "max_drawdown_days": int(max_dd_days),
        "current_drawdown_pct": float(current_dd_pct),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Async orchestration — DB-dependent
# ═══════════════════════════════════════════════════════════════════════════

async def fetch_holdings(
    db: AsyncSession,
    portfolio_id: str,
) -> List[Dict[str, Any]]:
    """Fetch raw holdings with enrichment from Instrument and BondMaster."""
    result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = result.scalars().all()

    enriched: list[dict] = []
    for h in holdings:
        d = {
            "id": str(h.id),
            "ticker": None,
            "quantity": float(h.quantity) if h.quantity else 0,
            "current_value": float(h.current_value) if h.current_value else 0,
            "avg_buy_price": float(h.avg_buy_price) if h.avg_buy_price else 0,
            "current_price": float(h.current_price) if h.current_price else 0,
            "unrealized_pnl": float(h.unrealized_pnl) if h.unrealized_pnl else 0,
            "instrument_class": "BOND_GOV",
        }

        # Enrich with Instrument
        if h.instrument_id:
            instr_result = await db.execute(
                select(Instrument).where(Instrument.id == h.instrument_id)
            )
            instr = instr_result.scalar_one_or_none()
            if instr and instr.ticker:
                d["ticker"] = instr.ticker

        # Enrich with BondMaster for bond-specific fields
        if d["ticker"]:
            master_result = await db.execute(
                select(BondMaster).where(BondMaster.ticker == d["ticker"])
            )
            master = master_result.scalar_one_or_none()
            if master:
                d["coupon_rate"] = master.coupon_rate
                d["issue_date"] = master.issue_date
                d["maturity_date"] = master.maturity_date
                d["par_value"] = master.par_value
                d["instrument_class"] = master.instrument_class or "BOND_GOV"
                d["frequency_n"] = master.frequency_n or 2

        enriched.append(d)

    return enriched


async def calculate_all_metrics(
    db: AsyncSession,
    portfolio_id: str,
    *,
    bna_rate: float = 0.17,
    inflation_rate: float = 0.1242,
    persist: bool = False,
    risk_free_override: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Orchestrator: fetch data, compute all analytics, optionally persist.

    Parameters:
        portfolio_id: portfolio UUID
        bna_rate: current BNA policy rate (decimal, default 17%)
        inflation_rate: current inflation (decimal, default 12.42%)
        persist: if True, write snapshot to PortfolioAnalytics table
        risk_free_override: override Rf (useful for testing)

    Returns comprehensive analytics dict.
    """
    # ── Fetch ──
    holdings = await fetch_holdings(db, portfolio_id)

    # Portfolio basic data
    portfolio_result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = portfolio_result.scalar_one_or_none()
    if not portfolio:
        return {"error": "Portfolio not found"}

    portfolio_value = float(portfolio.current_value or 0)
    total_invested = float(portfolio.total_invested or 0)
    realized_pnl = float(portfolio.total_return_pct or 0) * total_invested / 100 if total_invested else 0

    unrealized_pnl = sum(
        float(h.unrealized_pnl or 0) for h in
        (await db.execute(select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        ))).scalars().all()
    )

    # ── Risk-free rate (Angola-specific) ──
    if risk_free_override is not None:
        rf = risk_free_override
    else:
        # Rf ≈ BNA rate adjusted for IAC on risk-free OT
        iac = await get_active_iac_rate(db, payment_date=date.today())
        rf = bna_rate * (1 - float(iac))  # nominal Rf net of tax

    # ── Try country risk metrics for better Rf ──
    try:
        cr_result = await db.execute(
            select(CountryRiskMetric)
            .where(CountryRiskMetric.country_code == "AO")
            .order_by(desc(CountryRiskMetric.metric_date))
            .limit(1)
        )
        crm = cr_result.scalar_one_or_none()
        if crm and crm.risk_free_rate:
            rf = float(crm.risk_free_rate)
        if crm and crm.inflation_rate:
            inflation_rate = float(crm.inflation_rate)
    except Exception:
        pass  # Table might not exist yet

    # ── Weights → HHI, Gini, Effective N ──
    weights = [h.get("current_value", 0) for h in holdings]
    hhi = calc_concentration_hhi(weights)
    gini = calc_concentration_gini(weights)
    eff_n = calc_effective_n(hhi)

    # ── Duration (aggregate across bonds) ──
    dur_mac = 0.0
    dur_mod = 0.0
    conv_total = 0.0
    weighted_yield = 0.0
    weighted_real_yield = 0.0
    total_bond_value = sum(
        h.get("current_value", 0) for h in holdings
        if h.get("instrument_class") in ("BOND_GOV", "BOND_CORP") and h.get("coupon_rate")
    )

    for h in holdings:
        if h.get("instrument_class") not in ("BOND_GOV", "BOND_CORP"):
            continue
        val = h.get("current_value", 0) or 0
        coupon = h.get("coupon_rate")
        maturity = h.get("maturity_date")
        issue = h.get("issue_date")
        par = h.get("par_value") or 0
        freq_n_val = h.get("frequency_n") or 2

        if not (val and coupon and maturity and par):
            continue

        # Compute YTM from current price
        years = years_between(issue, maturity) if issue else 0
        if years <= 0:
            continue

        # Build cash flows for this bond
        n_cf = int(years * freq_n_val)
        if n_cf <= 0:
            continue

        cf: list[tuple[Decimal, Decimal]] = []
        for i in range(1, n_cf + 1):
            t = D(i) / D(freq_n_val)
            cf_gross = D(par) * D(coupon) / D(freq_n_val)
            if i == n_cf:
                cf.append((t, cf_gross + D(par)))
            else:
                cf.append((t, cf_gross))

        # Resolve IAC for this bond
        rates = await resolve_for_bond(db, h, payment_date=date.today())
        iac_rate = float(rates["coupon_tax_rate"])

        # Price: use current_value / (quantity) as current price per unit
        qty = h.get("quantity", 1) or 1
        current_price_per_unit = val / max(qty, 1)
        theoretical_price = D(par)

        # YTM from market price
        try:
            ytm = float(solve_ytm(cf, D(str(current_price_per_unit * par) if current_price_per_unit < 1000 else D(str(val)))))
        except Exception:
            ytm = float(D(coupon))

        # Duration
        try:
            dur = calc_duration(cf, D(str(ytm)))
        except Exception:
            continue

        # Real yield (Fisher)
        real_yld = float(fisher_real(D(str(ytm)), D(str(inflation_rate))))
        real_yld_after_tax = real_yld * (1 - iac_rate)

        w = val / max(total_bond_value, 1)
        dur_mac += float(dur["macaulay"]) * w
        dur_mod += float(dur["modified"]) * w
        conv_total += float(dur["convexity"]) * w
        weighted_yield += ytm * w
        weighted_real_yield += real_yld_after_tax * w

    # ── Portfolio return ──
    portfolio_return = (portfolio_value / total_invested - 1) if total_invested > 0 else 0.0

    # ── VaR / CVaR ──
    # For VaR we need historical snapshots — use holdings values as proxy
    values = [h.get("current_value", 0) for h in holdings]
    var_p = calc_var_parametric(values)
    var_h = calc_var_historic(values)
    cvar = calc_cvar(values)

    # ── Liquidity ──
    liq_scores = []
    for h in holdings:
        ticker = h.get("ticker")
        if not ticker:
            continue
        ob_result = await db.execute(
            select(OrderBookSnapshot)
            .where(OrderBookSnapshot.ticker == ticker)
            .order_by(desc(OrderBookSnapshot.snapshot_date))
            .limit(10)
        )
        order_book = ob_result.scalars().all()
        best_bid = max((r.price for r in order_book if r.side == "BID" and r.price), default=None)
        best_ask = min((r.price for r in order_book if r.side == "ASK" and r.price), default=None)
        bid_vol = sum(r.quantity for r in order_book if r.side == "BID" and r.quantity)
        ls = calc_liquidity_score(best_bid, best_ask, bid_vol)
        liq_scores.append(ls["score"])

    avg_liquidity = sum(liq_scores) / len(liq_scores) if liq_scores else 0.0

    # ── Slippage estimate ──
    total_volume = sum(h.get("quantity", 0) or 0 for h in holdings)
    bid_prices_list = []
    bid_vols_list = []
    for h in holdings:
        ticker = h.get("ticker")
        if not ticker:
            continue
        ob_result = await db.execute(
            select(OrderBookSnapshot)
            .where(OrderBookSnapshot.ticker == ticker, OrderBookSnapshot.side == "BID")
            .order_by(OrderBookSnapshot.level)
            .limit(5)
        )
        for r in ob_result.scalars().all():
            bid_prices_list.append(float(r.price or 0))
            bid_vols_list.append(float(r.quantity or 0))

    slippage = calc_slippage_estimate(total_volume, bid_vols_list, bid_prices_list)

    # ── Drawdown (proxy: use holdings current_value) ──
    dd = calc_drawdown(values)

    # ── Sharpe / Sortino / Calmar ──
    returns_list = [
        (h.get("current_value", 0) - h.get("avg_buy_price", 0) * h.get("quantity", 0))
        / max(abs(h.get("avg_buy_price", 0) * h.get("quantity", 0)), 1)
        for h in holdings if h.get("avg_buy_price", 0) > 0
    ]

    # Volatility from order book yield_pct variations as proxy
    vol_result = await db.execute(
        select(OrderBookSnapshot.yield_pct)
        .order_by(desc(OrderBookSnapshot.snapshot_date))
        .limit(100)
    )
    yields_data = [r[0] for r in vol_result.all() if r[0] is not None]
    sigma = 0.0
    if len(yields_data) >= 5:
        mu_y = sum(yields_data) / len(yields_data)
        sigma = math.sqrt(sum((y - mu_y) ** 2 for y in yields_data) / (len(yields_data) - 1)) / 100

    sharpe = calc_sharpe_ratio(weighted_yield, rf, sigma) if sigma > 0 else None
    sortino_val = calc_sortino_ratio(returns_list, rf) if len(returns_list) >= 2 else None
    calmar = calc_calmar_ratio(weighted_yield, dd["max_drawdown_pct"]) if dd["max_drawdown_pct"] > 0 else None

    # ── Assemble result ──
    result: dict = {
        "portfolio_id": portfolio_id,
        "portfolio_name": portfolio.name,
        "portfolio_value": portfolio_value,
        "total_invested": total_invested,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "n_holdings": len(holdings),

        # Risk
        "risk_metrics": {
            "var_95_1m": var_p["var_value"],
            "var_95_1m_pct": var_p["var_pct"],
            "var_historic_pct": var_h["var_pct"],
            "cvar_95_1m": cvar["cvar_value"],
            "cvar_95_1m_pct": cvar["cvar_pct"],
        },

        # Risk-adjusted return
        "performance_metrics": {
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino_val,
            "calmar_ratio": calmar,
            "information_ratio": None,  # Needs benchmark data
        },

        # Duration & convexity
        "duration_metrics": {
            "macaulay_duration": round(dur_mac, 2),
            "modified_duration": round(dur_mod, 2),
            "convexity": round(conv_total, 2),
            "weighted_yield": round(weighted_yield, 4),
            "weighted_real_yield": round(weighted_real_yield, 4),
        },

        # Concentration
        "concentration_metrics": {
            "hhi": round(hhi, 4),
            "gini": round(gini, 4),
            "effective_n": round(eff_n, 2),
        },

        # Liquidity
        "liquidity_metrics": {
            "score": round(avg_liquidity, 2),
            "estimated_slippage_pct": slippage["slippage_pct"],
        },

        # Drawdown
        "drawdown_metrics": dd,

        # Context
        "context": {
            "risk_free_rate": round(rf, 4),
            "inflation_rate": round(inflation_rate, 4),
            "bna_rate": round(bna_rate, 4),
            "snapshot_date": datetime.utcnow().isoformat(),
        },

        # Early warnings
        "early_warnings": [],
    }

    # ── Early warning rules ──
    warnings = []
    if dur_mod > 7:
        warnings.append({
            "level": "ALERT",
            "message": "Portfolio muito sensivel a subidas de taxa — duration modificada > 7 anos.",
            "metric": "modified_duration",
            "value": round(dur_mod, 2),
        })
    if hhi > 0.25:
        warnings.append({
            "level": "WATCH",
            "message": "Concentracao elevada — considera diversificar entre mais instrumentos.",
            "metric": "hhi",
            "value": round(hhi, 2),
        })
    if avg_liquidity < 2.0 and avg_liquidity > 0:
        warnings.append({
            "level": "INFO",
            "message": "Liquidez baixa — pode ser dificil sair rapidamente de algumas posicoes.",
            "metric": "liquidity_score",
            "value": round(avg_liquidity, 2),
        })
    if dd["max_drawdown_pct"] > 0.15:
        warnings.append({
            "level": "ALERT",
            "message": f"Drawdown maximo de {dd['max_drawdown_pct']:.1%} — rever alocacao.",
            "metric": "max_drawdown_pct",
            "value": round(dd["max_drawdown_pct"], 2),
        })
    if weighted_real_yield < 0:
        warnings.append({
            "level": "CRITICAL",
            "message": "Yield real negativo — o portfolio perde poder de compra anualmente.",
            "metric": "weighted_real_yield",
            "value": round(weighted_real_yield, 4),
        })

    result["early_warnings"] = warnings

    # ── Persist (optional) ──
    if persist:
        snapshot = PortfolioAnalytics(
            portfolio_id=portfolio_id,
            var_95_1m=var_p["var_value"],
            var_95_1m_pct=var_p["var_pct"],
            cvar_95_1m=cvar["cvar_value"],
            sharpe_ratio=sharpe,
            sortino_ratio=sortino_val,
            calmar_ratio=calmar,
            macaulay_duration=round(dur_mac, 2),
            modified_duration=round(dur_mod, 2),
            convexity=round(conv_total, 2),
            hhi=round(hhi, 4),
            gini=round(gini, 4),
            effective_n=round(eff_n, 2),
            liquidity_score=round(avg_liquidity, 2),
            estimated_slippage_pct=slippage["slippage_pct"],
            max_drawdown_pct=dd["max_drawdown_pct"],
            max_drawdown_duration_days=dd["max_drawdown_days"],
            snapshot_date=datetime.utcnow(),
            portfolio_value=portfolio_value,
            total_invested=total_invested,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            raw_data=result,
        )
        db.add(snapshot)
        await db.commit()

    return result
