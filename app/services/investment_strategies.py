"""
investment_strategies.py
=======================
Investment strategies engine — suggests optimal strategies based on investor profile
and market conditions.

Strategies (yield curve):
  - Bullet:     Concentrate in a specific maturity band (e.g. 2-3 years)
  - Barbell:    Weights at short and long extremes
  - Ladder:     Stagger maturities (1,2,3,4,5 years)
  - Riding the Curve: Buy long, sell before maturity (steep curve)

Quantitative:
  - DCA vs Lump Sum: periodic investing vs lump sum simulation
  - Tax-Aware Swap: recommends swaps based on IAC regime

All core functions are PURE (testable without DB).
"""
from __future__ import annotations

import math
from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, List, Optional, Any


# ═══════════════════════════════════════════════════════════════════════════
# Yield Curve Strategies
# ═══════════════════════════════════════════════════════════════════════════

STRATEGY_DESCRIPTIONS = {
    "bullet": {
        "name": "Bullet",
        "desc": "Concentrar investimentos numa maturidade especifica (ex: 2-3 anos). "
                "Ideal quando se preve que as taxas se vao manter estaveis.",
        "ideal_for": "Investidor com conviccao forte sobre direcao das taxas",
        "risk_level": "Medio",
    },
    "barbell": {
        "name": "Barbell",
        "desc": "Distribuir o capital entre prazos muito curtos e muito longos. "
                "Protege contra movimentos bruscos nas taxas de medio prazo.",
        "ideal_for": "Cenarios de incerteza sobre a direcao das taxas",
        "risk_level": "Baixo-Médio",
    },
    "ladder": {
        "name": "Ladder (Escada)",
        "desc": "Escalonar as maturidades (ex: 1, 2, 3, 4, 5 anos). "
                "A cada ano uma parcela vence e pode ser reinvestida a taxa corrente.",
        "ideal_for": "Investidor que quer fluxo de caixa previsivel e reinvestimento regular",
        "risk_level": "Baixo",
    },
    "riding_the_curve": {
        "name": "Riding the Curve",
        "desc": "Comprar titulos de longo prazo e vender antes do vencimento "
                "para beneficiar de uma curva de juros inclinada.",
        "ideal_for": "Curva de juros inclinada (longo prazo rende significativamente mais)",
        "risk_level": "Alto",
    },
}


def suggest_strategies(
    profile: str,
    yield_curve_slope: Optional[float] = None,
    volatility_regime: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Suggest investment strategies based on investor profile and market conditions.

    Parameters:
        profile: CONSERVADOR | MODERADO | DINAMICO | AGRESSIVO
        yield_curve_slope: steepness of yield curve (10yr - 2yr) in %
        volatility_regime: "low" | "normal" | "high"

    Returns ranked list of strategy recommendations with scores.
    """
    profile = profile.upper()
    suggestions = []

    for key, meta in STRATEGY_DESCRIPTIONS.items():
        score = _score_strategy(key, profile, yield_curve_slope, volatility_regime)
        if score > 0:
            suggestions.append({
                "key": key,
                "name": meta["name"],
                "description": meta["desc"],
                "ideal_for": meta["ideal_for"],
                "risk_level": meta["risk_level"],
                "score": round(score, 2),
            })

    suggestions.sort(key=lambda x: x["score"], reverse=True)
    return suggestions


def _score_strategy(
    strategy: str,
    profile: str,
    yield_curve_slope: Optional[float],
    volatility_regime: Optional[str],
) -> float:
    """Score a strategy for a given profile and market conditions (0 to 10)."""
    # Base score by profile
    profile_scores = {
        "bullet": {"CONSERVADOR": 7, "MODERADO": 6, "DINAMICO": 4, "AGRESSIVO": 2},
        "barbell": {"CONSERVADOR": 3, "MODERADO": 7, "DINAMICO": 8, "AGRESSIVO": 4},
        "ladder": {"CONSERVADOR": 9, "MODERADO": 8, "DINAMICO": 5, "AGRESSIVO": 3},
        "riding_the_curve": {"CONSERVADOR": 1, "MODERADO": 3, "DINAMICO": 7, "AGRESSIVO": 9},
    }

    score = profile_scores.get(strategy, {}).get(profile, 5)

    # Adjust for yield curve slope
    if yield_curve_slope is not None:
        if strategy == "riding_the_curve":
            if yield_curve_slope > 2.0:
                score += 3  # steep curve = good for riding
            elif yield_curve_slope < 0.5:
                score -= 3  # flat curve = bad
        elif strategy == "bullet":
            if yield_curve_slope < 1.0:
                score += 2  # flat curve = bullet is fine

    # Adjust for volatility
    if volatility_regime:
        if volatility_regime == "high":
            if strategy in ("ladder", "barbell"):
                score += 2  # defensive strategies
            if strategy == "riding_the_curve":
                score -= 3  # risky in high vol
        elif volatility_regime == "low":
            if strategy == "bullet":
                score += 2

    return max(0, min(10, score))


def compare_strategies(
    portfolio_value: float,
    average_yield: float,
    time_horizon_years: int,
) -> Dict[str, Any]:
    """
    Compare projected outcomes of different yield curve strategies.

    Parameters:
        portfolio_value: total amount invested (AOA)
        average_yield: current average portfolio yield (decimal)
        time_horizon_years: investment horizon

    Returns projected values for each strategy.
    """
    base = portfolio_value
    results = {}

    # Bullet: single maturity, reinvest at same rate
    bullet_final = base * (1 + average_yield) ** time_horizon_years
    results["bullet"] = {
        "final_value": round(bullet_final, 2),
        "description": f"Investir {base:,.0f} AOA numa unica maturidade a {average_yield:.1%}",
    }

    # Ladder: staggered maturities, each rung matures and reinvests
    # Simulate rolling reinvestment
    ladder_value = 0.0
    n_rungs = min(time_horizon_years, 5)
    for i in range(1, n_rungs + 1):
        rung_value = base / n_rungs
        rung_years = time_horizon_years - i + 1
        if rung_years > 0:
            ladder_value += rung_value * (1 + average_yield) ** rung_years
        else:
            ladder_value += rung_value
    results["ladder"] = {
        "final_value": round(ladder_value, 2),
        "description": f"Escalonar em {n_rungs} prazos (1-{n_rungs} anos), reinvestindo a cada vencimento",
    }

    # Barbell: 50% short (1yr), 50% long (horizon_years)
    short_half = base * 0.5 * (1 + average_yield * 0.7) ** 1  # short yields less
    long_half = base * 0.5 * (1 + average_yield * 1.1) ** time_horizon_years  # long yields more
    barbell_final = short_half + long_half
    results["barbell"] = {
        "final_value": round(barbell_final, 2),
        "description": "50% em prazo curto (1 ano), 50% em prazo longo (vencimento)",
    }

    # Riding the curve: buy long, sell halfway
    mid_yield = average_yield * 1.2  # steeper yield
    riding_final = base * (1 + mid_yield) ** (time_horizon_years * 0.6)
    results["riding_the_curve"] = {
        "final_value": round(riding_final, 2),
        "description": f"Comprar longo prazo, vender antes do vencimento (yield estimado {mid_yield:.1%})",
    }

    # Determine best
    best = max(results, key=lambda k: results[k]["final_value"])
    results["best"] = {
        "strategy": best,
        "name": STRATEGY_DESCRIPTIONS[best]["name"] if best in STRATEGY_DESCRIPTIONS else best,
        "final_value": results[best]["final_value"],
    }

    return results


# ═══════════════════════════════════════════════════════════════════════════
# DCA vs Lump Sum Simulation
# ═══════════════════════════════════════════════════════════════════════════

def simulate_dca_vs_lump_sum(
    total_amount: float,
    time_horizon_years: int,
    expected_annual_return: float,
    volatility: float = 0.0,
    num_installments: int = 12,
) -> Dict[str, Any]:
    """
    Compare Dollar Cost Averaging vs Lump Sum investing.

    Parameters:
        total_amount: total amount to invest (AOA)
        time_horizon_years: how long until you need the money
        expected_annual_return: expected return (decimal)
        volatility: annual volatility (decimal, default 0 = deterministic)
        num_installments: DCA periods per year (default 12 = monthly)

    Returns projected final values for both strategies.
    """
    if time_horizon_years <= 0 or total_amount <= 0:
        return {
            "lump_sum": 0,
            "dca": 0,
            "difference": 0,
            "conclusion": "Parametros invalidos",
        }

    monthly_return = (1 + expected_annual_return) ** (1 / 12) - 1
    total_months = time_horizon_years * 12
    installment_months = max(1, 12 // num_installments) if num_installments > 0 else 1
    installment_amount = total_amount / (num_installments * time_horizon_years)

    # Lump Sum: invest everything immediately
    lump_sum_value = total_amount * (1 + expected_annual_return) ** time_horizon_years

    # DCA: invest in installments, each one grows for the remainder of the period
    dca_value = 0.0
    months_invested = 0
    for m in range(total_months):
        if m % installment_months == 0 and months_invested < num_installments * time_horizon_years:
            months_remaining = total_months - m
            dca_value += installment_amount * (1 + monthly_return) ** months_remaining
            months_invested += 1

    difference = dca_value - lump_sum_value
    pct_diff = difference / lump_sum_value if lump_sum_value > 0 else 0

    # Conclusion
    if pct_diff > 0.05:
        conclusion = "DCA supera Lump Sum em {:.1f}% — mercado com elevada volatilidade ou timing desfavoravel.".format(pct_diff * 100)
    elif pct_diff < -0.05:
        conclusion = "Lump Sum supera DCA em {:.1f}% — mercado com tendencia de alta consistente.".format(abs(pct_diff) * 100)
    else:
        conclusion = "Diferenca marginal ({:.1f}%). Para horizontes longos (>10 anos), Lump Sum tende a superar DCA.".format(abs(pct_diff) * 100)

    return {
        "lump_sum": round(lump_sum_value, 2),
        "dca": round(dca_value, 2),
        "difference": round(difference, 2),
        "pct_difference": round(pct_diff * 100, 2),
        "total_amount": total_amount,
        "time_horizon_years": time_horizon_years,
        "expected_annual_return": expected_annual_return,
        "conclusion": conclusion,
    }
