"""
risk_manager.py
===============
Portfolio risk management engine — stress tests, early warnings, liquidity,
and concentration analysis. FRM-aligned methodology.

Leverages existing functions from:
  - portfolio_analytics.py: calc_var_*, calc_concentration_*, calc_drawdown, calc_liquidity_score
  - financial_core.py: calc_duration, price_impact_yield_shock
  - tax_engine.py: get_active_iac_rate

All core computations are PURE. Async orchestration at the bottom.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Optional, Any, Tuple

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio
from app.models.portfolio_holding import PortfolioHolding
from app.models.bodiva_market import MarketSnapshot, OrderBookSnapshot, BondMaster
from app.models.scenario_analysis import ScenarioAnalysis, ScenarioType
from app.models.scenario_definition import ScenarioDefinition, ScenarioCategory
from app.models.investment_signal import InvestmentSignal, SignalType, SignalSeverity
from app.models.country_risk_metric import CountryRiskMetric
from app.models.portfolio_analytics import PortfolioAnalytics

from .portfolio_analytics import (
    calc_concentration_hhi,
    calc_concentration_gini,
    calc_effective_n,
    calc_liquidity_score,
    calc_slippage_estimate,
    calc_drawdown,
    calc_var_parametric,
    calc_var_historic,
    calc_cvar,
    calc_sharpe_ratio,
    calc_sortino_ratio,
    calc_calmar_ratio,
)
from .financial_core import (
    D, parse_date, years_between,
    calc_duration, price_impact_yield_shock, solve_ytm, fisher_real,
)
from .tax_engine import get_active_iac_rate, resolve_for_bond

# ═══════════════════════════════════════════════════════════════════════════
# 1. Prebuilt Angola Scenarios
# ═══════════════════════════════════════════════════════════════════════════

PREBUILT_SCENARIOS = [
    {
        "name": "Estabilidade",
        "category": "MACRO",
        "severity": 0,
        "description": "Cenario base: BNA mantem taxa a 17%, inflacao controlada a 12%, USD/AOA estavel.",
        "params": {
            "bna_rate": 0.17, "inflation": 0.12, "usd_aoa": 650.0,
            "eur_aoa": 710.0, "oil_price": 75.0, "gdp_growth": 0.03, "cds_spread": 500,
        },
    },
    {
        "name": "Choque Moderado",
        "category": "MACRO",
        "severity": 2,
        "description": "BNA sobe taxa 2pp para 19%, inflacao acelera 3pp para 15%, kwanza deprecia 10%.",
        "params": {
            "bna_rate": 0.19, "inflation": 0.15, "usd_aoa": 715.0,
            "eur_aoa": 781.0, "oil_price": 63.75, "gdp_growth": 0.02, "cds_spread": 650,
        },
    },
    {
        "name": "Choque Severo",
        "category": "MACRO",
        "severity": 3,
        "description": "Crise: BNA sobe 5pp para 22%, inflacao atinge 20%, kwanza deprecia 25%, petroleo cai 30%.",
        "params": {
            "bna_rate": 0.22, "inflation": 0.20, "usd_aoa": 812.5,
            "eur_aoa": 887.5, "oil_price": 52.5, "gdp_growth": -0.01, "cds_spread": 900,
        },
    },
    {
        "name": "Crise Cambial",
        "category": "CURRENCY",
        "severity": 4,
        "description": "Crash cambial: BNA sobe 10pp para 27%, inflacao explode a 27%, kwanza perde 50%, petroleo colapsa.",
        "params": {
            "bna_rate": 0.27, "inflation": 0.27, "usd_aoa": 975.0,
            "eur_aoa": 1065.0, "oil_price": 37.5, "gdp_growth": -0.03, "cds_spread": 1500,
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# 2. Stress Test — apply a macro scenario to a bond portfolio
# ═══════════════════════════════════════════════════════════════════════════

def _apply_rate_shock_to_bond(
    bond: Dict[str, Any],
    delta_yield: float,
) -> Optional[Dict[str, Any]]:
    """
    Apply a parallel yield shift (+delta_yield in decimal, e.g. 0.02 = +200bp)
    to a single bond position and compute the price impact.

    Uses duration + convexity 2nd-order Taylor approximation.
    """
    coupon = bond.get("coupon_rate")
    par = bond.get("par_value")
    freq_n_val = bond.get("frequency_n") or 2
    years = years_between(
        parse_date(bond.get("issue_date")),
        parse_date(bond.get("maturity_date")),
    )

    if not (coupon and par and years and years > 0):
        return None

    # Build cash flows
    n_cf = int(years * freq_n_val)
    if n_cf <= 0:
        return None

    cf: list[tuple[Decimal, Decimal]] = []
    for i in range(1, n_cf + 1):
        t = D(i) / D(freq_n_val)
        cf_gross = D(par) * D(coupon) / D(freq_n_val)
        if i == n_cf:
            cf.append((t, cf_gross + D(par)))
        else:
            cf.append((t, cf_gross))

    # Compute duration at current yield
    current_yield = D(str(coupon))
    dur = calc_duration(cf, current_yield)
    mod_dur = dur["modified"]
    conv = dur["convexity"]

    current_price = D(str(bond.get("current_price", par)))
    impact = price_impact_yield_shock(current_price, mod_dur, conv, D(str(delta_yield)))

    qty = bond.get("quantity", 1) or 1
    pnl = float(impact["pnl"]) * qty

    return {
        "ticker": bond.get("ticker", "?"),
        "current_price": float(current_price),
        "modified_duration": float(mod_dur),
        "convexity": float(conv),
        "delta_yield": delta_yield,
        "price_change_pct": float(impact["pct_change"]),
        "new_price": float(impact["new_price"]),
        "pnl_per_unit": float(impact["pnl"]),
        "pnl_total": round(pnl, 2),
    }


def stress_test_holding(
    holding: Dict[str, Any],
    scenario_params: Dict[str, float],
) -> Dict[str, Any]:
    """
    Estimate the impact of a macro scenario on a single holding.

    For bonds: apply a yield shock proportional to BNA rate change.
    For equities: apply a valuation shock proportional to GDP + inflation change.
    """
    instr_class = holding.get("instrument_class", "BOND_GOV")
    current_value = holding.get("current_value", 0) or 0
    ticker = holding.get("ticker", "?")

    result = {
        "ticker": ticker,
        "instrument_class": instr_class,
        "current_value": current_value,
        "impact_value": 0.0,
        "impact_pct": 0.0,
        "new_value": current_value,
        "notes": "",
    }

    if "BOND" in str(instr_class).upper():
        # Bond impact via duration
        base_bna = 0.17
        shock_bna = scenario_params.get("bna_rate", base_bna)
        delta_yield = shock_bna - base_bna

        bond_impact = _apply_rate_shock_to_bond(holding, delta_yield)
        if bond_impact:
            result["impact_pct"] = bond_impact["price_change_pct"]
            result["impact_value"] = bond_impact["pnl_total"]
            result["new_value"] = current_value + result["impact_value"]

        # Add inflation impact on real return (Fisher adjustment)
        base_infl = 0.12
        shock_infl = scenario_params.get("inflation", base_infl)
        if shock_infl > base_infl:
            infl_effect = (shock_infl - base_infl) * current_value * 0.3  # approximation
            result["impact_value"] += -infl_effect
            result["impact_pct"] += -(shock_infl - base_infl) * 0.3

        result["notes"] = f"Choque BNA: {base_bna:.0%} -> {shock_bna:.0%} (+{delta_yield*100:.0f}bp)"

    elif "EQUITY" in str(instr_class).upper():
        # Equity impact via GDP + inflation shock
        # Angola equities are heavily correlated with macro conditions
        base_gdp = 0.03
        shock_gdp = scenario_params.get("gdp_growth", base_gdp)
        gdp_effect = (shock_gdp - base_gdp) * 3  # 1% GDP change ~ 3% equity impact

        base_infl = 0.12
        shock_infl = scenario_params.get("inflation", base_infl)
        infl_effect = -(shock_infl - base_infl) * 2  # higher inflation = lower equity multiples

        total_effect = gdp_effect + infl_effect
        result["impact_pct"] = total_effect
        result["impact_value"] = current_value * total_effect
        result["new_value"] = current_value + result["impact_value"]
        result["notes"] = f"GDP: {base_gdp:.0%}->{shock_gdp:.0%}, Infl: {base_infl:.0%}->{shock_infl:.0%}"

    else:
        # Default: proportional shock to value
        severity = scenario_params.get("_severity", 1.0)
        result["impact_pct"] = -severity * 0.05
        result["impact_value"] = -severity * 0.05 * current_value
        result["new_value"] = current_value + result["impact_value"]
        result["notes"] = "Estimativa generica (classificacao nao reconhecida)"

    result["impact_value"] = round(result["impact_value"], 2)
    result["impact_pct"] = round(result["impact_pct"], 6)
    result["new_value"] = round(result["new_value"], 2)
    return result


async def stress_test(
    db: AsyncSession,
    portfolio_id: str,
    scenario: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Full stress test: apply a macro scenario to an entire portfolio.

    1. Fetch all holdings
    2. Apply scenario to each position
    3. Aggregate results
    4. Optionally persist to ScenarioAnalysis
    """
    # Fetch portfolio
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = port_result.scalar_one_or_none()
    if not portfolio:
        return {"error": "Portfolio not found"}

    # Fetch holdings enriched from BondMaster
    holdings_result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = holdings_result.scalars().all()

    portfolio_value = float(portfolio.current_value or 0)
    scenario_params = scenario.get("params", {})

    results = []
    total_impact = 0.0

    for h in holdings:
        h_dict = {
            "id": str(h.id),
            "ticker": getattr(h, "ticker", None),
            "quantity": float(h.quantity) if h.quantity else 0,
            "current_value": float(h.current_value) if h.current_value else 0,
            "current_price": float(h.current_price) if h.current_price else 0,
            "instrument_class": "BOND_GOV",
        }

        # Enrich from BondMaster if available
        if h.instrument_id:
            instr_result = await db.execute(
                select(BondMaster).where(BondMaster.ticker == getattr(h, "ticker", None))
            )
            master = instr_result.scalar_one_or_none()
            if master:
                h_dict["coupon_rate"] = master.coupon_rate
                h_dict["issue_date"] = master.issue_date
                h_dict["maturity_date"] = master.maturity_date
                h_dict["par_value"] = master.par_value
                h_dict["frequency_n"] = master.frequency_n or 2
                h_dict["instrument_class"] = master.instrument_class or "BOND_GOV"

        impact = stress_test_holding(h_dict, scenario_params)
        results.append(impact)
        total_impact += impact["impact_value"]

    impact_pct = total_impact / portfolio_value if portfolio_value > 0 else 0.0
    severity = scenario.get("severity", 2)

    return {
        "portfolio_id": portfolio_id,
        "portfolio_name": portfolio.name,
        "portfolio_value": portfolio_value,
        "scenario": scenario.get("name", "Custom"),
        "scenario_severity": severity,
        "holdings_analyzed": len(results),
        "total_impact": round(total_impact, 2),
        "total_impact_pct": round(impact_pct, 4),
        "new_portfolio_value": round(portfolio_value + total_impact, 2),
        "per_holding": results,
        "worst_affected": sorted(results, key=lambda r: r["impact_pct"])[0]
            if results else None,
        "best_affected": sorted(results, key=lambda r: r["impact_pct"])[-1]
            if results else None,
    }


async def run_scenario_analysis(
    db: AsyncSession,
    portfolio_id: str,
    n_simulations: int = 1000,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    Run all predefined Angola scenarios against the portfolio and rank them.

    For Monte Carlo: simplified parametric simulation with 1K paths.
    Returns summary for each scenario + overall risk score.
    """
    results = {"portfolio_id": portfolio_id, "scenarios": [], "overall_risk_score": 0}

    for scenario in PREBUILT_SCENARIOS:
        scenario_with_sev = dict(scenario)
        scenario_with_sev["params"]["_severity"] = scenario["severity"] / 2.0
        result = await stress_test(db, portfolio_id, scenario_with_sev)
        results["scenarios"].append({
            "name": scenario["name"],
            "severity": scenario["severity"],
            "impact_pct": result["total_impact_pct"],
            "impact_value": result["total_impact"],
            "new_value": result["new_portfolio_value"],
        })

        # Persist if requested
        if persist:
            analysis = ScenarioAnalysis(
                portfolio_id=portfolio_id,
                scenario_type=ScenarioType.PARAMETRIC,
                scenario_name=scenario["name"],
                params=scenario["params"],
                impact_value=result["total_impact"],
                impact_pct=result["total_impact_pct"],
                n_simulations=0,
                snapshot_date=datetime.utcnow(),
            )
            db.add(analysis)

    if persist:
        await db.commit()

    # Overall risk score: weighted average by severity
    scores = results["scenarios"]
    if scores:
        weighted = sum(
            abs(s["impact_pct"]) * (s["severity"] + 1)
            for s in scores
        )
        total_weight = sum(s["severity"] + 1 for s in scores)
        results["overall_risk_score"] = round(weighted / total_weight * 100, 1) if total_weight > 0 else 0

    return results


# ═══════════════════════════════════════════════════════════════════════════
# 3. Early Warnings
# ═══════════════════════════════════════════════════════════════════════════

EARLY_WARNING_RULES = [
    {
        "id": "duration_high",
        "check": lambda m: m.get("modified_duration", 0) > 7,
        "level": SignalSeverity.ALERT.value,
        "title": "Duration elevada",
        "message": "A duration modificada do portfolio excede 7 anos. "
                   "Subidas de taxa de 1pp podem causar perdas superiores a 7%.",
    },
    {
        "id": "hhi_high",
        "check": lambda m: m.get("hhi", 0) > 0.25,
        "level": SignalSeverity.WATCH.value,
        "title": "Concentracao excessiva",
        "message": "O indice HHI indica concentracao significativa. "
                   "Considera diversificar entre mais instrumentos e classes.",
    },
    {
        "id": "liquidity_low",
        "check": lambda m: m.get("liquidity_score", 5) < 2.0,
        "level": SignalSeverity.INFO.value,
        "title": "Liquidez reduzida",
        "message": "A liquidez do portfolio e baixa, o que pode dificultar "
                   "a saida de posicoes em momentos de volatilidade.",
    },
    {
        "id": "drawdown_extreme",
        "check": lambda m: m.get("max_drawdown_pct", 0) > 0.15,
        "level": SignalSeverity.ALERT.value,
        "title": "Drawdown significativo",
        "message": "O portfolio registou um drawdown maximo acima de 15%. "
                   "Considera rever a alocacao de risco.",
    },
    {
        "id": "real_yield_negative",
        "check": lambda m: m.get("weighted_real_yield", 0) < 0,
        "level": SignalSeverity.CRITICAL.value,
        "title": "Yield real negativo",
        "message": "O portfolio esta a perder poder de compra — "
                   "o yield nominal menos IAC nao cobre a inflacao.",
    },
    {
        "id": "cvar_tail_risk",
        "check": lambda m: m.get("cvar_95_1m_pct", 0) > 0.10,
        "level": SignalSeverity.ALERT.value,
        "title": "Risco de cauda elevado",
        "message": "O CVaR (Expected Shortfall) a 95% excede 10% em 1 mes. "
                   "O portfolio tem exposicao significativa a eventos extremos.",
    },
    {
        "id": "convexity_negative",
        "check": lambda m: m.get("convexity", 0) < 0,
        "level": SignalSeverity.WATCH.value,
        "title": "Convexidade negativa",
        "message": "Convexidade negativa — a duracao aumenta quando as taxas sobem, "
                   "amplificando perdas em cenarios de subida de juros.",
    },
]


def generate_early_warnings(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Check all early warning rules against current portfolio metrics.

    Returns list of triggered warnings with severity and message.
    Pure function — no DB required.
    """
    warnings = []
    for rule in EARLY_WARNING_RULES:
        try:
            if rule["check"](metrics):
                warnings.append({
                    "warning_id": rule["id"],
                    "severity": rule["level"],
                    "title": rule["title"],
                    "message": rule["message"],
                    "detected_at": datetime.utcnow().isoformat(),
                })
        except (KeyError, TypeError):
            continue
    return warnings


# ═══════════════════════════════════════════════════════════════════════════
# 4. Liquidity Analysis
# ═══════════════════════════════════════════════════════════════════════════

async def liquidity_analysis(
    db: AsyncSession,
    portfolio_id: str,
) -> Dict[str, Any]:
    """Full liquidity analysis: spread, depth, slippage per instrument."""
    holdings_result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = holdings_result.scalars().all()

    per_instrument = []
    total_score = 0.0
    count = 0

    for h in holdings:
        ticker = getattr(h, "ticker", None)
        qty = float(h.quantity) if h.quantity else 0
        if not ticker or qty <= 0:
            continue

        # Fetch order book data
        ob_result = await db.execute(
            select(OrderBookSnapshot)
            .where(OrderBookSnapshot.ticker == ticker)
            .order_by(desc(OrderBookSnapshot.snapshot_date))
            .limit(20)
        )
        order_book = ob_result.scalars().all()

        best_bid = max((r.price for r in order_book if r.side == "BID" and r.price), default=None)
        best_ask = min((r.price for r in order_book if r.side == "ASK" and r.price), default=None)
        bid_vol = sum(r.quantity for r in order_book if r.side == "BID" and r.quantity)

        ls = calc_liquidity_score(best_bid, best_ask, bid_vol)

        # Slippage estimate
        bid_prices = [float(r.price) for r in order_book if r.side == "BID" and r.price]
        bid_vols = [float(r.quantity) for r in order_book if r.side == "BID" and r.quantity]
        sl = calc_slippage_estimate(qty, bid_vols, bid_prices)

        per_instrument.append({
            "ticker": ticker,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_pct": ls["spread_pct"],
            "bid_depth": bid_vol,
            "liquidity_score": ls["score"],
            "slippage_pct": sl["slippage_pct"],
            "levels_to_fill": sl["levels_consumed"],
        })
        total_score += ls["score"]
        count += 1

    avg_score = total_score / count if count > 0 else 0.0

    # Qualitative rating
    if avg_score > 100:
        rating = "ALTA"
    elif avg_score > 30:
        rating = "MEDIA"
    elif avg_score > 5:
        rating = "BAIXA"
    else:
        rating = "MUITO_BAIXA"

    return {
        "portfolio_id": portfolio_id,
        "average_liquidity_score": round(avg_score, 2),
        "liquidity_rating": rating,
        "instruments_analyzed": count,
        "per_instrument": per_instrument,
        "worst": sorted(per_instrument, key=lambda i: i["liquidity_score"])[0]
            if per_instrument else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. Concentration Report
# ═══════════════════════════════════════════════════════════════════════════

async def concentration_report(
    db: AsyncSession,
    portfolio_id: str,
) -> Dict[str, Any]:
    """
    Concentration analysis: HHI, Gini, Effective N, and breakdowns
    by issuer, instrument class, currency, and maturity bucket.
    """
    holdings_result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = holdings_result.scalars().all()

    values = [float(h.current_value or 0) for h in holdings]
    total_value = sum(values)
    weights = [v / total_value if total_value > 0 else 0 for v in values]

    # Overall metrics
    hhi = round(calc_concentration_hhi(weights), 4)
    gini = round(calc_concentration_gini(weights), 4)
    eff_n = round(calc_effective_n(hhi), 2)

    # Breakdown by instrument class
    by_class: dict[str, float] = {}
    for h in holdings:
        cls = getattr(h, "instrument_class", None) or "UNKNOWN"
        val = float(h.current_value or 0)
        by_class[cls] = by_class.get(cls, 0) + val

    # Breakdown by issuer (enrich from BondMaster)
    by_issuer: dict[str, float] = {}
    by_maturity_bucket: dict[str, float] = {}
    for h in holdings:
        ticker = getattr(h, "ticker", None)
        val = float(h.current_value or 0)
        if ticker:
            master_result = await db.execute(
                select(BondMaster).where(BondMaster.ticker == ticker)
            )
            master = master_result.scalar_one_or_none()
            if master:
                issuer = master.issuer or "Desconhecido"
                by_issuer[issuer] = by_issuer.get(issuer, 0) + val

                if master.maturity_date:
                    years_left = years_between(date.today(), master.maturity_date)
                    if years_left <= 1:
                        bucket = "<1 ano"
                    elif years_left <= 3:
                        bucket = "1-3 anos"
                    elif years_left <= 5:
                        bucket = "3-5 anos"
                    elif years_left <= 10:
                        bucket = "5-10 anos"
                    else:
                        bucket = ">10 anos"
                    by_maturity_bucket[bucket] = by_maturity_bucket.get(bucket, 0) + val

        if not ticker:
            by_issuer["Outro"] = by_issuer.get("Outro", 0) + val

    # Convert to percentages
    def to_pct(d: dict) -> dict:
        return {k: round(v / total_value * 100, 1) if total_value > 0 else 0 for k, v in d.items()}

    # Diversification assessment
    if eff_n >= 5:
        rating = "BEM_DIVERSIFICADO"
    elif eff_n >= 3:
        rating = "MODERADO"
    elif eff_n >= 1.5:
        rating = "CONCENTRADO"
    else:
        rating = "MUITO_CONCENTRADO"

    return {
        "portfolio_id": portfolio_id,
        "total_value": total_value,
        "n_holdings": len(holdings),
        "hhi": hhi,
        "gini": gini,
        "effective_n": eff_n,
        "diversification_rating": rating,
        "by_class": to_pct(by_class),
        "by_class_raw": by_class,
        "by_issuer": to_pct(by_issuer),
        "by_issuer_raw": by_issuer,
        "by_maturity_bucket": to_pct(by_maturity_bucket),
        "by_maturity_bucket_raw": by_maturity_bucket,
    }
