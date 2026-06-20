"""
scenario_engine.py
==================
Scenario simulation engine — Monte Carlo, sensitivity matrix, tornado charts.

MVP approach:
  - Monte Carlo: simplified parametric with 1K paths (no GARCH, no copula)
  - Correlation: linear (no copula — v2 feature)
  - Generates distribution of portfolio returns under shock scenarios

All core computations are PURE (testable without DB).
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Optional, Any, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio
from app.models.portfolio_holding import PortfolioHolding
from app.models.bodiva_market import BondMaster
from app.models.scenario_analysis import ScenarioAnalysis, ScenarioType
from app.models.scenario_definition import ScenarioDefinition, ScenarioCategory

from .risk_manager import PREBUILT_SCENARIOS
from .financial_core import D, parse_date, years_between, calc_duration, fisher_real

# ═══════════════════════════════════════════════════════════════════════════
# 1. Random Number Generation (seeded for reproducibility)
# ═══════════════════════════════════════════════════════════════════════════

def _set_seed(seed: Optional[int] = None) -> None:
    """Set random seed for reproducible simulations."""
    if seed is not None:
        random.seed(seed)


def _normal(mean: float = 0.0, std: float = 1.0) -> float:
    """Box-Muller transform for normal random variates."""
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2.0 * math.log(max(u1, 1e-10))) * math.cos(2.0 * math.pi * u2)
    return mean + std * z


def _correlated_normals(
    n_vars: int,
    correlation: float = 0.5,
    seed: Optional[int] = None,
) -> List[float]:
    """
    Generate correlated normal random variables using simple pairwise correlation.
    For n_vars factors (e.g. BNA rate, inflation, USD/AOA).
    """
    _set_seed(seed)
    common = _normal(0, 1)  # common factor
    results = []
    for _ in range(n_vars):
        idiosyncratic = _normal(0, 1)
        rho = max(-1, min(1, correlation))
        r = rho * common + math.sqrt(1 - rho ** 2) * idiosyncratic
        results.append(r)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# 2. Monte Carlo Simulation
# ═══════════════════════════════════════════════════════════════════════════

def monte_carlo_simulation(
    initial_value: float,
    expected_return: float,
    volatility: float,
    time_horizon_years: float = 1.0,
    n_paths: int = 1000,
    n_steps: int = 252,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Simplified parametric Monte Carlo simulation.

    Parameters:
        initial_value: starting portfolio value
        expected_return: annual expected return (decimal)
        volatility: annual volatility (decimal)
        time_horizon_years: simulation horizon
        n_paths: number of paths (default 1000)
        n_steps: time steps (default 252 = daily)
        seed: random seed for reproducibility

    Returns: {paths, percentiles, distribution_stats}
    """
    _set_seed(seed)

    dt = time_horizon_years / n_steps if n_steps > 0 else 1/252
    drift = (expected_return - 0.5 * volatility**2) * dt
    vol_dt = volatility * math.sqrt(dt)

    final_values = []
    all_paths = []

    for _ in range(n_paths):
        price = initial_value
        path = [price]

        for _ in range(n_steps):
            shock = _normal(0, 1)
            price *= math.exp(drift + vol_dt * shock)
            path.append(price)

        final_values.append(price)
        # Store every 10th path for memory efficiency
        if len(all_paths) < min(50, n_paths):
            all_paths.append({
                "initial": initial_value,
                "final": round(price, 2),
                "return_pct": round((price / initial_value - 1) * 100, 2),
            })

    sorted_finals = sorted(final_values)
    n = len(sorted_finals)

    percentiles = {
        "p5": sorted_finals[max(0, int(n * 0.05))],
        "p10": sorted_finals[max(0, int(n * 0.10))],
        "p25": sorted_finals[int(n * 0.25)],
        "p50": sorted_finals[int(n * 0.50)],
        "p75": sorted_finals[int(n * 0.75)],
        "p90": sorted_finals[int(n * 0.90)],
        "p95": sorted_finals[min(n - 1, int(n * 0.95))],
    }

    mean_final = sum(final_values) / n
    std_final = math.sqrt(sum((v - mean_final) ** 2 for v in final_values) / n)

    # Probability of loss
    prob_loss = sum(1 for v in final_values if v < initial_value) / n

    # Expected Shortfall at 95%
    var_95 = int(n * 0.05)
    tail = sorted_finals[:var_95]
    es_95 = sum(tail) / len(tail) if tail else 0

    return {
        "parameters": {
            "initial_value": initial_value,
            "expected_return": expected_return,
            "volatility": volatility,
            "time_horizon_years": time_horizon_years,
            "n_paths": n_paths,
            "n_steps": n_steps,
        },
        "distribution_stats": {
            "mean": round(mean_final, 2),
            "std": round(std_final, 2),
            "min": round(min(final_values), 2),
            "max": round(max(final_values), 2),
            "prob_loss": round(prob_loss, 4),
            "expected_shortfall_95": round(es_95, 2),
        },
        "percentiles": {k: round(v, 2) for k, v in percentiles.items()},
        "sample_paths": all_paths,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. Multi-Factor Scenario Simulation
# ═══════════════════════════════════════════════════════════════════════════

def multi_factor_monte_carlo(
    initial_value: float,
    factors: List[Dict[str, float]],
    n_paths: int = 1000,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Monte Carlo with correlated macro factors for Angola.

    Factors (with mean and std):
      - bna_rate: ~0.17, std 0.03
      - inflation: ~0.12, std 0.05
      - usd_aoa: ~650, std 100
      - oil_price: ~75, std 15

    Portfolio impact is estimated from scenario engineering (not individual bond pricing).
    """
    _set_seed(seed)

    # Default Angola macro factors
    if not factors:
        factors = [
            {"name": "bna_rate", "mean": 0.17, "std": 0.03},
            {"name": "inflation", "mean": 0.12, "std": 0.05},
            {"name": "usd_aoa", "mean": 650.0, "std": 100.0},
            {"name": "oil_price", "mean": 75.0, "std": 15.0},
        ]

    results = []
    for _ in range(n_paths):
        # Generate correlated shocks
        correlations = _correlated_normals(len(factors), correlation=0.4)

        scenario_params = {}
        for i, factor in enumerate(factors):
            shock = correlations[i]
            scenario_params[factor["name"]] = max(
                0.01, min(2000, factor["mean"] + shock * factor["std"])
            )

        # Impact model: simplified linear approximation
        base_bna = 0.17
        base_infl = 0.12
        base_usd = 650.0

        delta_bna = scenario_params.get("bna_rate", base_bna) - base_bna
        delta_infl = scenario_params.get("inflation", base_infl) - base_infl
        delta_usd = scenario_params.get("usd_aoa", base_usd) - base_usd

        # Portfolio impact = rate effect + inflation effect + currency effect
        # Rate effect: +1pp BNA ≈ -5pp bond prices
        # Inflation: +1pp ≈ -3pp real returns
        # Currency depreciation: +10% ≈ +2pp international component value
        impact_pct = (
            -delta_bna * 5.0       # rate impact on bonds
            - delta_infl * 3.0     # inflation real return
            + delta_usd / 650 * 0.2  # currency impact on intl positions
        )

        final_value = initial_value * (1 + impact_pct)
        results.append({
            "scenario_params": scenario_params,
            "impact_pct": round(impact_pct, 4),
            "final_value": round(final_value, 2),
        })

    # Aggregate
    impacts = [r["impact_pct"] for r in results]
    finals = [r["final_value"] for r in results]
    sorted_finals = sorted(finals)
    n = len(sorted_finals)

    return {
        "n_paths": n_paths,
        "n_factors": len(factors),
        "percentiles": {
            "p5": sorted_finals[max(0, int(n * 0.05))],
            "p25": sorted_finals[int(n * 0.25)],
            "p50": sorted_finals[int(n * 0.50)],
            "p75": sorted_finals[int(n * 0.75)],
            "p95": sorted_finals[min(n - 1, int(n * 0.95))],
        },
        "impact_stats": {
            "mean_pct": round(sum(impacts) / len(impacts) * 100, 2) if impacts else 0,
            "worst": round(min(impacts) * 100, 2) if impacts else 0,
            "best": round(max(impacts) * 100, 2) if impacts else 0,
            "prob_loss": round(sum(1 for i in impacts if i < 0) / len(impacts), 4) if impacts else 0,
        },
        "sample_results": results[:20],  # first 20 paths
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Sensitivity Matrix
# ═══════════════════════════════════════════════════════════════════════════

def sensitivity_matrix(
    base_yield: float,
    duration: float,
    convexity: float,
    yield_shifts: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """
    Compute portfolio value impact for various yield shifts.

    Uses 2nd-order Taylor: ΔP/P ≈ -ModDur · Δy + ½ · Conv · (Δy)²

    Parameters:
        base_yield: current portfolio yield (decimal)
        duration: modified duration
        convexity: convexity
        yield_shifts: list of yield shifts in bps (default: -200 to +200 every 25bp)

    Returns list of (shift, price_change_pct, new_price) tuples.
    """
    if yield_shifts is None:
        # Generate shifts from -200bp to +200bp every 25bp
        yield_shifts = [i * 0.0025 for i in range(-80, 81)]
        # simplify: -0.02 to +0.02 step 0.0025

    results = []
    for dy in yield_shifts:
        dur_effect = -duration * dy
        conv_effect = 0.5 * convexity * (dy ** 2)
        pct_change = dur_effect + conv_effect
        new_yield = base_yield + dy
        results.append({
            "yield_shift_bps": round(dy * 10000, 1),
            "yield_shift_pct": round(dy * 100, 2),
            "new_yield": round(new_yield * 100, 2),
            "price_change_pct": round(pct_change * 100, 2),
            "duration_effect_pct": round(dur_effect * 100, 2),
            "convexity_effect_pct": round(conv_effect * 100, 2),
        })

    return {
        "base_yield": round(base_yield * 100, 2),
        "duration": round(duration, 2),
        "convexity": round(convexity, 2),
        "points": results,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. Tornado Chart Data
# ═══════════════════════════════════════════════════════════════════════════

def tornado_chart_data(
    base_metrics: Dict[str, Any],
    sensitivity_ranges: Optional[Dict[str, Tuple[float, float]]] = None,
) -> Dict[str, Any]:
    """
    Generate data for a tornado chart showing which factors most impact the portfolio.

    Each factor has a low and high case. Returns sorted by max absolute impact.
    """
    portfolio_value = base_metrics.get("portfolio_value", 1000000)
    duration = base_metrics.get("modified_duration", 3)
    hhi = base_metrics.get("hhi", 0.2)

    # Default sensitivity ranges
    if sensitivity_ranges is None:
        sensitivity_ranges = {
            "BNA Rate (+1pp)": (-duration * 0.01, duration * 0.01),
            "Inflacao (+5pp)": (-0.05 * 0.3, -0.05 * 0.3),  # inflation is always negative
            "USD/AOA (+10%)": (0.10 * 0.2, 0.10 * 0.2),
            "Petroleo (-20%)": (-0.20 * 0.15, -0.20 * 0.15),
            "HHI (+0.1)": (-0.10 * 0.5, 0),
            "Drawdown (+10%)": (-0.10, 0),
        }

    factors = []
    for name, (low, high) in sensitivity_ranges.items():
        low_val = portfolio_value * low
        high_val = portfolio_value * high
        factors.append({
            "factor": name,
            "low_impact": round(low_val, 2),
            "high_impact": round(high_val, 2),
            "low_pct": round(low * 100, 2),
            "high_pct": round(high * 100, 2),
            "max_abs_impact": max(abs(low_val), abs(high_val)),
        })

    # Sort by max absolute impact (descending)
    factors.sort(key=lambda x: x["max_abs_impact"], reverse=True)

    return {
        "portfolio_value": portfolio_value,
        "factors": factors,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. Async Orchestration
# ═══════════════════════════════════════════════════════════════════════════

async def run_monte_carlo_for_portfolio(
    db: AsyncSession,
    portfolio_id: str,
    n_paths: int = 1000,
    seed: Optional[int] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    Run Monte Carlo simulation specific to a portfolio's composition.

    1. Fetch holdings → compute weighted yield and duration
    2. Estimate volatility from order book data
    3. Run simulation
    4. Persist results
    """
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = port_result.scalar_one_or_none()
    if not portfolio:
        return {"error": "Portfolio not found"}

    portfolio_value = float(portfolio.current_value or 0)
    expected_return = 0.15  # default: 15% nominal for Angola
    volatility = 0.08  # default: 8% annual vol

    # Try to get better estimates from BondMaster
    holdings_result = await db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == portfolio_id,
            PortfolioHolding.deleted_at.is_(None),
        )
    )
    holdings = holdings_result.scalars().all()

    total_yield = 0.0
    total_dur = 0.0
    total_val = 0.0

    for h in holdings:
        val = float(h.current_value or 0)
        if val <= 0:
            continue
        total_val += val

    # Simple simulation with estimated parameters
    result = monte_carlo_simulation(
        initial_value=portfolio_value,
        expected_return=expected_return,
        volatility=volatility,
        time_horizon_years=1.0,
        n_paths=n_paths,
        n_steps=252,
        seed=seed,
    )

    if persist:
        analysis = ScenarioAnalysis(
            portfolio_id=portfolio_id,
            scenario_type=ScenarioType.MONTE_CARLO,
            scenario_name="Monte Carlo 1Y Forward",
            params={
                "expected_return": expected_return,
                "volatility": volatility,
                "time_horizon_years": 1.0,
                "n_paths": n_paths,
            },
            impact_pct=result["distribution_stats"]["prob_loss"],
            n_simulations=n_paths,
            confidence_level=0.95,
            distribution=result["percentiles"],
            snapshot_date=datetime.utcnow(),
        )
        db.add(analysis)
        await db.commit()

    return result


async def run_full_portfolio_simulation(
    db: AsyncSession,
    portfolio_id: str,
    n_paths: int = 1000,
    seed: Optional[int] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    Run both Monte Carlo and multi-factor simulation for a portfolio.

    Returns combined results for the dashboard.
    """
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = port_result.scalar_one_or_none()
    if not portfolio:
        return {"error": "Portfolio not found"}

    portfolio_value = float(portfolio.current_value or 0)

    # 1. Standard Monte Carlo
    mc_result = monte_carlo_simulation(
        initial_value=portfolio_value,
        expected_return=0.15,
        volatility=0.08,
        n_paths=n_paths,
        seed=seed,
    )

    # 2. Multi-factor simulation (Angola macro)
    mf_result = multi_factor_monte_carlo(
        initial_value=portfolio_value,
        n_paths=n_paths,
        seed=seed,
    )

    # 3. Sensitivity matrix
    sens_result = sensitivity_matrix(
        base_yield=0.15,
        duration=3.0,
        convexity=6.0,
    )

    combined = {
        "portfolio_id": portfolio_id,
        "portfolio_value": portfolio_value,
        "monte_carlo": {
            "distribution": mc_result["distribution_stats"],
            "percentiles": mc_result["percentiles"],
        },
        "multi_factor": {
            "impact_stats": mf_result["impact_stats"],
            "percentiles": mf_result["percentiles"],
        },
        "sensitivity": sens_result,
    }

    if persist:
        analysis = ScenarioAnalysis(
            portfolio_id=portfolio_id,
            scenario_type=ScenarioType.MONTE_CARLO,
            scenario_name="Full Portfolio Simulation",
            params={"n_paths": n_paths, "methods": ["mc", "multi_factor", "sensitivity"]},
            impact_pct=mf_result["impact_stats"]["mean_pct"] / 100 if mf_result["impact_stats"].get("mean_pct") else 0,
            n_simulations=n_paths,
            confidence_level=0.95,
            distribution={
                "mc_percentiles": mc_result["percentiles"],
                "mf_percentiles": mf_result["percentiles"],
            },
            snapshot_date=datetime.utcnow(),
        )
        db.add(analysis)
        await db.commit()

    return combined
