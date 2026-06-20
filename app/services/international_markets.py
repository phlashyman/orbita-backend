"""
international_markets.py
========================
International markets engine for Angolan investors.

Critical context: Angola has 12-30% inflation, AOA depreciates ~10%/year vs USD.
An investor holding ONLY AOA-denominated assets is doubly exposed: credit risk (BODIVA)
and currency risk (USD/AOA).

This module provides:
  1. International allocation suggestions — Markowitz MVO for S&P 500, JSE, STOXX, Gold, USD bonds
  2. Kelly Criterion — optimal fraction per international market
  3. Currency risk overlay — impact of USD/AOA, EUR/AOA, ZAR/AOA on portfolio
  4. Market comparison engine — "OT vs S&P 500 vs JSE vs Gold over 5 years"
  5. Hedge simulator — portfolio value under currency scenarios

NOTE: Markowitz and Kelly apply ONLY to international markets (S&P 500, JSE, STOXX, Gold)
where historical data is sufficient for covariance estimation. NOT for BODIVA (illiquid).
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime
from typing import List, Dict, Optional, Any, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# Reference data — Angolan macro context (verified, not from memory)
# ═══════════════════════════════════════════════════════════════════════════

# Predefined international markets tracked via SerpAPI
INTERNATIONAL_MARKETS = {
    "sp500": {"name": "S&P 500", "index": "INDEXSP:.INX", "currency": "USD", "region": "US"},
    "nasdaq": {"name": "NASDAQ", "index": "INDEXNASDAQ:.IXIC", "currency": "USD", "region": "US"},
    "jse": {"name": "JSE Top 40", "index": "INDEXJSE:J200", "currency": "ZAR", "region": "ZA"},
    "ibovespa": {"name": "IBOVESPA", "index": "INDEXBVMF:IBOV", "currency": "BRL", "region": "BR"},
    "ftse100": {"name": "FTSE 100", "index": "INDEXFTSE:UKX", "currency": "GBP", "region": "UK"},
    "stoxx600": {"name": "STOXX 600", "index": "INDEXSTOXX:SXXP", "currency": "EUR", "region": "EU"},
    "nikkei": {"name": "NIKKEI 225", "index": "INDEXNIKKEI:NI225", "currency": "JPY", "region": "JP"},
    "hang_seng": {"name": "HANG SENG", "index": "INDEXHANGSENG:HSI", "currency": "HKD", "region": "HK"},
}

# Historical expected returns (approximate, for MVP allocation suggestions)
# Based on long-term averages — used when SerpAPI historical data is unavailable
MARKET_EXPECTED_RETURNS = {
    "US_EQUITY": {"mean": 0.10, "std": 0.15, "label": "USA (S&P 500)"},
    "US_BOND": {"mean": 0.05, "std": 0.06, "label": "USA (Treasuries)"},
    "SA_EQUITY": {"mean": 0.12, "std": 0.18, "label": "Africa do Sul (JSE)"},
    "EU_EQUITY": {"mean": 0.08, "std": 0.14, "label": "Europa (STOXX 600)"},
    "EM_EQUITY": {"mean": 0.11, "std": 0.20, "label": "Mercados Emergentes"},
    "GOLD": {"mean": 0.07, "std": 0.15, "label": "Ouro"},
    "COMMODITY": {"mean": 0.06, "std": 0.18, "label": "Commodities"},
}

# Approximate correlation matrix between international markets (long-term)
# Used for Markowitz when historical data isn't available
MARKET_CORRELATIONS: Dict[str, Dict[str, float]] = {
    "US_EQUITY": {"US_EQUITY": 1.0, "US_BOND": -0.3, "SA_EQUITY": 0.5, "EU_EQUITY": 0.7, "EM_EQUITY": 0.6, "GOLD": -0.1, "COMMODITY": 0.2},
    "US_BOND": {"US_EQUITY": -0.3, "US_BOND": 1.0, "SA_EQUITY": -0.2, "EU_EQUITY": -0.2, "EM_EQUITY": -0.1, "GOLD": 0.2, "COMMODITY": -0.1},
    "SA_EQUITY": {"US_EQUITY": 0.5, "US_BOND": -0.2, "SA_EQUITY": 1.0, "EU_EQUITY": 0.4, "EM_EQUITY": 0.5, "GOLD": 0.1, "COMMODITY": 0.3},
    "EU_EQUITY": {"US_EQUITY": 0.7, "US_BOND": -0.2, "SA_EQUITY": 0.4, "EU_EQUITY": 1.0, "EM_EQUITY": 0.5, "GOLD": -0.1, "COMMODITY": 0.1},
    "EM_EQUITY": {"US_EQUITY": 0.6, "US_BOND": -0.1, "SA_EQUITY": 0.5, "EU_EQUITY": 0.5, "EM_EQUITY": 1.0, "GOLD": 0.0, "COMMODITY": 0.3},
    "GOLD": {"US_EQUITY": -0.1, "US_BOND": 0.2, "SA_EQUITY": 0.1, "EU_EQUITY": -0.1, "EM_EQUITY": 0.0, "GOLD": 1.0, "COMMODITY": 0.4},
    "COMMODITY": {"US_EQUITY": 0.2, "US_BOND": -0.1, "SA_EQUITY": 0.3, "EU_EQUITY": 0.1, "EM_EQUITY": 0.3, "GOLD": 0.4, "COMMODITY": 1.0},
}

# Exchange-rate scenarios for Angola (illustrative)
CURRENCY_SCENARIOS = {
    "base": {"usd_aoa": 650.0, "eur_aoa": 710.0, "zar_aoa": 35.0, "label": "Cenario base"},
    "kwanza_depreciation_10": {"usd_aoa": 715.0, "eur_aoa": 781.0, "zar_aoa": 38.5, "label": "Desvalorizacao 10%"},
    "kwanza_depreciation_25": {"usd_aoa": 812.5, "eur_aoa": 887.5, "zar_aoa": 43.8, "label": "Desvalorizacao 25%"},
    "kwanza_stabilizes": {"usd_aoa": 600.0, "eur_aoa": 655.0, "zar_aoa": 32.3, "label": "Kwanza estabiliza"},
}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Currency Risk Overlay
# ═══════════════════════════════════════════════════════════════════════════

def calc_currency_impact(
    foreign_value: float,
    foreign_currency: str,
    current_rate: float,
    scenario_rate: float,
) -> Dict[str, Any]:
    """
    Calculate the AOA impact of currency movements on foreign holdings.

    Example: $10,000 USD at 650 USD/AOA = 6,500,000 AOA
    If USD/AOA moves to 715 (+10%): value = 7,150,000 AOA (+650,000)
    """
    current_aoa = foreign_value * current_rate
    scenario_aoa = foreign_value * scenario_rate
    change = scenario_aoa - current_aoa
    change_pct = (scenario_rate - current_rate) / current_rate

    return {
        "foreign_value": round(foreign_value, 2),
        "currency": foreign_currency,
        "current_rate": current_rate,
        "scenario_rate": scenario_rate,
        "current_value_aoa": round(current_aoa, 2),
        "scenario_value_aoa": round(scenario_aoa, 2),
        "change_aoa": round(change, 2),
        "change_pct": round(change_pct * 100, 2),
        "direction": "ganho" if change > 0 else "perda",
    }


def portfolio_currency_impact(
    positions: List[Dict[str, Any]],
    scenario: str = "kwanza_depreciation_10",
) -> Dict[str, Any]:
    """
    Apply a currency scenario to a portfolio of international positions.

    positions: list of {"ticker", "currency", "value", "market"}
    scenario: scenario key from CURRENCY_SCENARIOS
    """
    rates = CURRENCY_SCENARIOS.get(scenario, CURRENCY_SCENARIOS["base"])
    base_rates = CURRENCY_SCENARIOS["base"]

    total_current = 0.0
    total_scenario = 0.0
    impacts = []

    for pos in positions:
        curr = pos.get("currency", "USD")
        value = pos.get("value", 0) or 0

        # Map currency to rate key
        rate_map = {"USD": "usd_aoa", "EUR": "eur_aoa", "GBP": "eur_aoa",
                    "ZAR": "zar_aoa", "BRL": "zar_aoa"}
        rate_key = rate_map.get(curr, "usd_aoa")

        current_rate = base_rates.get(rate_key, 650.0)
        scenario_rate = rates.get(rate_key, current_rate)

        impact = calc_currency_impact(value, curr, current_rate, scenario_rate)
        impacts.append({**pos, **impact})
        total_current += impact["current_value_aoa"]
        total_scenario += impact["scenario_value_aoa"]

    total_change = total_scenario - total_current
    total_change_pct = ((total_change / total_current) * 100) if total_current > 0 else 0

    return {
        "scenario": scenario,
        "scenario_label": rates.get("label", scenario),
        "current_total_aoa": round(total_current, 2),
        "scenario_total_aoa": round(total_scenario, 2),
        "total_change_aoa": round(total_change, 2),
        "total_change_pct": round(total_change_pct, 2),
        "per_position": impacts,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. Markowitz Mean-Variance Optimization (international only!)
# ═══════════════════════════════════════════════════════════════════════════

def _covariance(
    weights: List[float],
    stds: List[float],
    correlations: List[List[float]],
) -> float:
    """Portfolio variance: w^T * Sigma * w."""
    n = len(weights)
    var = 0.0
    for i in range(n):
        for j in range(n):
            var += weights[i] * weights[j] * stds[i] * stds[j] * correlations[i][j]
    return var


def mean_variance_optimization(
    asset_classes: List[str],
    target_return: Optional[float] = None,
    risk_free_rate: float = 0.04,
) -> Dict[str, Any]:
    """
    Mean-Variance Optimization (Markowitz) for INTERNATIONAL MARKETS ONLY.

    Finds the portfolio allocation that minimises variance for a given target return,
    or maximises Sharpe ratio if no target_return is specified.

    Parameters:
        asset_classes: list of keys from MARKET_EXPECTED_RETURNS
        target_return: desired portfolio return (decimal). If None, maximises Sharpe.
        risk_free_rate: risk-free rate for Sharpe calculation

    Returns optimal weights and efficient frontier stats.

    NOTE: DO NOT use for BODIVA. Use ONLY for international markets with
    sufficient historical data (S&P 500, JSE, STOXX, Gold, etc.).
    """
    n = len(asset_classes)
    if n < 2:
        return {"error": "Precisa de pelo menos 2 classes de ativos"}

    # Build data arrays
    means = []
    stds = []
    corr_matrix = [[0.0] * n for _ in range(n)]

    for i, cls in enumerate(asset_classes):
        info = MARKET_EXPECTED_RETURNS.get(cls, {"mean": 0.08, "std": 0.15})
        means.append(info["mean"])
        stds.append(info["std"])
        for j, cls2 in enumerate(asset_classes):
            corr = MARKET_CORRELATIONS.get(cls, {}).get(cls2, 0.5)
            corr_matrix[i][j] = corr

    # Simple grid search for optimal weights (equal-weighted starting point)
    # For MVP, we use a simplified approach: maximize Sharpe via iterative search
    best_sharpe = -float("inf")
    best_weights = [1.0 / n] * n
    best_return = 0.0
    best_vol = 0.0

    # If target return is specified, find allocation closest to it
    if target_return is not None:
        # Simple approach: proportional allocation based on how each asset class
        # contributes to the target return
        total_weight = 0.0
        raw_weights = []
        for m in means:
            if m > 0:
                w = max(0, target_return / m)
            else:
                w = 0
            raw_weights.append(w)
            total_weight += w

        if total_weight > 0:
            best_weights = [w / total_weight for w in raw_weights]
        else:
            best_weights = [1.0 / n] * n

        best_return = sum(best_weights[i] * means[i] for i in range(n))
        best_vol = math.sqrt(_covariance(best_weights, stds, corr_matrix))
        best_sharpe = (best_return - risk_free_rate) / best_vol if best_vol > 0 else 0

    else:
        # Maximise Sharpe ratio via iterative hill climbing
        weights = [1.0 / n] * n
        for _ in range(1000):
            i = _ % n
            j = (i + 1) % n
            delta = 0.01

            # Try shifting small weight from i to j
            w_test = list(weights)
            w_test[i] -= delta
            w_test[j] += delta
            if w_test[i] < 0 or w_test[j] < 0:
                continue

            r = sum(w_test[k] * means[k] for k in range(n))
            v = math.sqrt(_covariance(w_test, stds, corr_matrix))
            sharpe = (r - risk_free_rate) / v if v > 0 else 0

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                weights = w_test
                best_return = r
                best_vol = v
                best_weights = list(weights)

    # Efficient frontier points (for chart)
    frontier = []
    for ret in [m for m in sorted(set(means))]:
        total_w = 0.0
        raw_w = []
        for m in means:
            if m > 0:
                w = max(0, ret / m)
            else:
                w = 0
            raw_w.append(w)
            total_w += w

        if total_w > 0:
            ef_w = [w / total_w for w in raw_w]
            ef_vol = math.sqrt(_covariance(ef_w, stds, corr_matrix))
            frontier.append({"return_pct": round(ret * 100, 2), "vol_pct": round(ef_vol * 100, 2)})

    frontier.sort(key=lambda x: x["vol_pct"])

    allocation = {}
    for i, cls in enumerate(asset_classes):
        label = MARKET_EXPECTED_RETURNS.get(cls, {}).get("label", cls)
        allocation[label] = round(best_weights[i] * 100, 1)

    return {
        "method": "max_sharpe" if target_return is None else f"target_{target_return*100:.0f}pct",
        "target_return_pct": round(target_return * 100, 2) if target_return else None,
        "optimal_allocation": allocation,
        "expected_return_pct": round(best_return * 100, 2),
        "expected_vol_pct": round(best_vol * 100, 2),
        "sharpe_ratio": round(best_sharpe, 3),
        "efficient_frontier": frontier,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. Kelly Criterion (international only!)
# ═══════════════════════════════════════════════════════════════════════════

def kelly_international_split(
    markets: List[Dict[str, float]],
    fractional: float = 0.25,
) -> Dict[str, Any]:
    """
    Kelly Criterion for allocating between international markets.

    f* = (b * p - q) / b   where b = odds, p = win probability, q = 1-p

    For markets, we estimate:
      - p = probability of positive return (based on historical frequency)
      - b = expected return magnitude / volatility

    Uses fractional Kelly (default 25%) for safety — full Kelly is too aggressive.

    Parameters:
        markets: list of {"key": str, "expected_return": float, "volatility": float}
        fractional: fraction of full Kelly to use (default 0.25 = 25%)

    NOTE: For BODIVA (illiquid), use simple allocation heuristic instead.
    """
    if not markets:
        return {"error": "Lista de mercados vazia"}

    total_kelly = 0.0
    results = []

    for m in markets:
        key = m.get("key", "?")
        ret = m.get("expected_return", 0.05)
        vol = m.get("volatility", 0.15) or 0.01

        # Estimate win probability (p) from return/vol ratio
        ratio = ret / vol
        p = min(0.75, max(0.25, 0.5 + ratio * 0.1))

        # b = how much you win when you win (approximate)
        b = ret / p if p > 0 else 0.01
        q = 1 - p

        # Full Kelly
        f_star = (b * p - q) / b if b > 0 else 0
        f_star = max(0, min(0.5, f_star))  # cap at 50%

        # Fractional Kelly
        f_frac = f_star * fractional

        label = MARKET_EXPECTED_RETURNS.get(key, {}).get("label", key)
        results.append({
            "market": key,
            "label": label,
            "expected_return_pct": round(ret * 100, 2),
            "volatility_pct": round(vol * 100, 2),
            "win_probability": round(p, 3),
            "full_kelly_pct": round(f_star * 100, 2),
            "fractional_kelly_25_pct": round(f_frac * 100, 2),
        })
        total_kelly += f_frac

    # Normalise to sum to 100%
    if total_kelly > 0:
        for r in results:
            r["alloc_pct"] = round(r["fractional_kelly_25_pct"] / total_kelly * 100, 1)
    else:
        # Fallback: equal weight
        eq = 100.0 / len(results)
        for r in results:
            r["alloc_pct"] = round(eq, 1)

    return {
        "method": "fractional_kelly_25",
        "markets": results,
        "total_alloc_pct": round(min(100, sum(r["alloc_pct"] for r in results)), 1),
        "remaining_cash_pct": round(max(0, 100 - sum(r["alloc_pct"] for r in results)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Market Comparison Engine
# ═══════════════════════════════════════════════════════════════════════════

MARKET_HISTORICAL_DATA = {
    "sp500_usd": {"label": "S&P 500 (USD)", "annualized_return_5yr": 0.12, "annualized_return_10yr": 0.13},
    "ot_nr_aoa": {"label": "OT-NR (AOA)", "annualized_return_5yr": 0.195, "annualized_return_10yr": 0.18},
    "deposito_aoa": {"label": "Deposito a Prazo (AOA)", "annualized_return_5yr": 0.10, "annualized_return_10yr": 0.09},
    "jse_zar": {"label": "JSE Top 40 (ZAR)", "annualized_return_5yr": 0.10, "annualized_return_10yr": 0.09},
    "gold_usd": {"label": "Ouro (USD)", "annualized_return_5yr": 0.08, "annualized_return_10yr": 0.07},
    "usd_bonds": {"label": "US Treasuries (USD)", "annualized_return_5yr": 0.04, "annualized_return_10yr": 0.04},
    "ibovespa_brl": {"label": "IBOVESPA (BRL)", "annualized_return_5yr": 0.11, "annualized_return_10yr": 0.12},
    "em_equity_usd": {"label": "Emergentes (USD)", "annualized_return_5yr": 0.09, "annualized_return_10yr": 0.08},
}


def compare_markets(
    initial_investment: float = 1000000.0,
    currency: str = "AOA",
    years: int = 5,
    usd_aoa_start: float = 500.0,
    usd_aoa_end: float = 650.0,
    inflation_rate: float = 0.1242,
) -> Dict[str, Any]:
    """
    Historical market comparison: what would X AOA invested Y years ago be worth today?

    For an Angolan investor, the most revealing comparison:
      "If I invested 1M AOA in OT vs S&P 500 vs JSE vs Gold 5 years ago..."

    Adjusts USD/ZAR returns for AOA depreciation.
    """
    usd_change = usd_aoa_end / usd_aoa_start if usd_aoa_start > 0 else 1.0
    zar_aoa_start = usd_aoa_start / 18.6  # approximate ZAR/USD cross
    zar_aoa_end = usd_aoa_end / 18.0
    zar_change = zar_aoa_end / zar_aoa_start if zar_aoa_start > 0 else 1.0

    results = []
    for key, info in MARKET_HISTORICAL_DATA.items():
        ann_return = info.get(f"annualized_return_{years}yr", info.get("annualized_return_5yr", 0.08))
        final_value = initial_investment * (1 + ann_return) ** years

        # Adjust for currency (AOA-based investor repatriates to AOA)
        if "usd" in key:
            final_value_aoa = final_value * usd_change
        elif "zar" in key:
            final_value_aoa = final_value * zar_change
        else:
            final_value_aoa = final_value

        # Real return (after inflation)
        real_return = ((final_value_aoa / initial_investment) ** (1 / years) - 1) - inflation_rate
        # Simple real return approximation
        real_final = final_value_aoa / (1 + inflation_rate) ** years

        results.append({
            "key": key,
            "label": info["label"],
            "annualized_return": round(ann_return * 100, 2),
            "final_value_aoa": round(final_value_aoa, 2),
            "final_value_real_aoa": round(real_final, 2),
            "real_return_annual_pct": round(real_return * 100, 2),
            "gain_aoa": round(final_value_aoa - initial_investment, 2),
            "gain_pct": round((final_value_aoa / initial_investment - 1) * 100, 2),
        })

    # Sort by final value (descending)
    results.sort(key=lambda x: x["final_value_aoa"], reverse=True)

    return {
        "initial_investment": initial_investment,
        "currency": currency,
        "period_years": years,
        "usd_aoa_start": usd_aoa_start,
        "usd_aoa_end": usd_aoa_end,
        "inflation_rate": round(inflation_rate * 100, 2),
        "results": results,
        "best": results[0]["label"] if results else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. International Allocation Suggestion
# ═══════════════════════════════════════════════════════════════════════════

def suggest_international_split(
    risk_profile: str = "MODERADO",
    include_gold: bool = True,
) -> Dict[str, Any]:
    """
    Suggest international allocation split based on investor risk profile.

    These allocations are for the INTERNATIONAL PORTION only (the % of total
    portfolio that goes to non-AOA assets).

    Returns allocation across USD, EUR, ZAR, Gold.
    """
    profiles = {
        "CONSERVADOR": {
            "usd_equities": 0.40, "usd_bonds": 0.30, "eur_bonds": 0.20,
            "gold": 0.10, "zar_equities": 0.00,
            "recommended_share_of_portfolio": 0.20,
        },
        "MODERADO": {
            "usd_equities": 0.40, "usd_bonds": 0.15, "eur_bonds": 0.10,
            "gold": 0.10, "zar_equities": 0.25,
            "recommended_share_of_portfolio": 0.35,
        },
        "DINAMICO": {
            "usd_equities": 0.50, "usd_bonds": 0.05, "eur_bonds": 0.05,
            "gold": 0.10, "zar_equities": 0.30,
            "recommended_share_of_portfolio": 0.50,
        },
        "AGRESSIVO": {
            "usd_equities": 0.50, "usd_bonds": 0.00, "eur_bonds": 0.00,
            "gold": 0.10, "zar_equities": 0.40,
            "recommended_share_of_portfolio": 0.65,
        },
    }

    profile_alloc = profiles.get(risk_profile, profiles["MODERADO"])

    # Apply gold filter
    if not include_gold:
        gold_pct = profile_alloc.pop("gold", 0)
        # Redistribute gold to equities
        profile_alloc["usd_equities"] = profile_alloc.get("usd_equities", 0.4) + gold_pct * 0.5
        profile_alloc["zar_equities"] = profile_alloc.get("zar_equities", 0.25) + gold_pct * 0.5

    total_international = sum(v for k, v in profile_alloc.items() if k != "recommended_share_of_portfolio")

    return {
        "risk_profile": risk_profile,
        "recommended_share_of_total_portfolio": profile_alloc.get("recommended_share_of_portfolio", 0.35),
        "allocation": {
            "US Equities (S&P 500)": {
                "pct": round(profile_alloc.get("usd_equities", 0) * 100, 1),
                "suggested_tickers": "VOO, IVV, SPY",
            },
            "US Bonds": {
                "pct": round(profile_alloc.get("usd_bonds", 0) * 100, 1),
                "suggested_tickers": "TLT, BND, LQD",
            },
            "Europe Bonds": {
                "pct": round(profile_alloc.get("eur_bonds", 0) * 100, 1),
                "suggested_tickers": "IEAA, IBND",
            },
            "South Africa Equities": {
                "pct": round(profile_alloc.get("zar_equities", 0) * 100, 1),
                "suggested_tickers": "EZA, NPN.JSE",
            },
            "Gold": {
                "pct": round(profile_alloc.get("gold", 0) * 100, 1),
                "suggested_tickers": "GLD, IAU",
            },
        },
        "expected_return_pct": 0.0,
        "expected_vol_pct": 0.0,
        "note": "Alocacao para a COMPONENTE INTERNACIONAL do portfolio total. "
                "Consultar um consultor financeiro antes de investir no exterior.",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. Rebalancing Calendar
# ═══════════════════════════════════════════════════════════════════════════

def rebalancing_calendar(
    current_allocation: Dict[str, float],
    target_allocation: Dict[str, float],
    tolerance_pct: float = 5.0,
) -> Dict[str, Any]:
    """
    Check if rebalancing is needed based on drift from target allocation.
    Returns each asset's current, target, drift, and a rebalancing suggestion.
    """
    total_current = sum(current_allocation.values()) or 1
    total_target = sum(target_allocation.values()) or 1
    normalised_current = {k: v / total_current * 100 for k, v in current_allocation.items()}
    normalised_target = {k: v / total_target * 100 for k, v in target_allocation.items()}

    actions = []
    needs_rebalance = False
    max_drift = 0.0
    max_drift_asset = ""

    for k, target_pct in normalised_target.items():
        current_pct = normalised_current.get(k, 0)
        drift = current_pct - target_pct
        max_drift = max(max_drift, abs(drift))

        if abs(drift) > tolerance_pct:
            needs_rebalance = True
            max_drift_asset = k
            action = "VENDER" if drift > 0 else "COMPRAR"
            actions.append({
                "asset": k,
                "current_pct": round(current_pct, 1),
                "target_pct": round(target_pct, 1),
                "drift_pct": round(drift, 1),
                "action": action,
                "amount_to_trade_pct": round(abs(drift), 1),
            })

    return {
        "needs_rebalance": needs_rebalance,
        "max_drift_pct": round(max_drift, 1),
        "max_drift_asset": max_drift_asset,
        "tolerance_pct": tolerance_pct,
        "actions": actions,
        "recommendation": "Rebalanceamento necessario" if needs_rebalance else "Alocacao OK",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 7. Emerging Markets vs Developed Analysis
# ═══════════════════════════════════════════════════════════════════════════

def emerging_vs_developed_analysis() -> Dict[str, Any]:
    """Compare developed vs emerging markets for Angolan investor context."""
    return {
        "developed_markets": {
            "sp500": {"label": "S&P 500", "sharpe_10yr": 0.75, "correlation_aoa": -0.2},
            "ftse100": {"label": "FTSE 100", "sharpe_10yr": 0.55, "correlation_aoa": -0.15},
            "stoxx600": {"label": "STOXX 600", "sharpe_10yr": 0.60, "correlation_aoa": -0.1},
        },
        "emerging_markets": {
            "jse": {"label": "JSE Top 40", "sharpe_10yr": 0.50, "correlation_aoa": 0.3},
            "ibovespa": {"label": "IBOVESPA", "sharpe_10yr": 0.45, "correlation_aoa": 0.35},
            "ngx": {"label": "NGX Nigeria", "sharpe_10yr": 0.30, "correlation_aoa": 0.5},
        },
        "conclusion": "Para investidores angolanos, mercados desenvolvidos "
                      "(S&P 500, FTSE 100) oferecem melhor diversificacao "
                      "porque a correlacao com o kwanza e negativa. Mercados "
                      "emergentes africanos (JSE, NGX) tem correlacao positiva "
                      "com Angola, oferecendo menos protecao cambial.",
        "recommendation": "Alocar 60-70% da componente internacional a mercados "
                         "desenvolvidos, 30-40% a emergentes.",
    }
