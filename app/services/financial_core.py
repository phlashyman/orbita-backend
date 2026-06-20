"""
financial_core.py
=================
Core financial math with Decimal precision (28 digits).

Functions:
  - solve_ytm()       — Newton-Raphson YTM solver
  - calc_duration()    — Macaulay, Modified, Convexity
  - fisher_real()      — Fisher equation (real vs nominal vs inflation)
  - calc_liquidation() — Settlement with commission + IRC + IAC
  - generate_cash_flows() — Projected coupon + redemption flows
  - price_impact_yield_shock() — 2nd-order Taylor approximation

Ported from Claude AI version (Snapshots S1-S10) for the Orbita FastAPI backend.
All functions are PURE (no DB, no async) — testable without infrastructure.
"""
from __future__ import annotations

from decimal import Decimal, getcontext, ROUND_HALF_UP
from datetime import date, datetime
from typing import List, Tuple, Dict, Optional

getcontext().prec = 28

# ── Constants ──────────────────────────────────────────────────────────────
_ONE = Decimal("1")
_TWO = Decimal("2")
_HUNDRED = Decimal("100")
_HALF = Decimal("0.5")

# ── Frequency mapping ──────────────────────────────────────────────────────
FREQUENCY_MAP: dict[str, int] = {
    "Anual": 1, "anual": 1,
    "Semestral": 2, "semestral": 2,
    "Trimestral": 4, "trimestral": 4,
    "Mensal": 12, "mensal": 12,
}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def D(x) -> Decimal:
    """Safe Decimal conversion. None / "" → 0."""
    if x is None or x == "":
        return Decimal("0")
    return Decimal(str(x))


def quantize_money(x: Decimal) -> Decimal:
    """Round to 2 decimal places (AOA)."""
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quantize_pct(x: Decimal) -> Decimal:
    """Round to 6 decimal places (percentages)."""
    return x.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def parse_date(v) -> Optional[date]:
    """Parse Portuguese / ISO dates: DD/MM/YYYY, YYYY-MM-DD, etc."""
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def freq_n(frequency: str | None) -> int:
    """Map frequency string → payments/year. Default: 2 (semestral)."""
    if not frequency:
        return 2
    return FREQUENCY_MAP.get(frequency.strip(), 2)


def years_between(d1: Optional[date], d2: Optional[date]) -> float:
    """Years elapsed between two dates (365.25 basis)."""
    if not d1 or not d2:
        return 0.0
    return (d2 - d1).days / 365.25


# ═══════════════════════════════════════════════════════════════════════════
# Fisher Equation
# ═══════════════════════════════════════════════════════════════════════════

def fisher_real(yield_nominal: Decimal, inflation: Decimal) -> Decimal:
    """Fisher exact: Real = (1 + Nominal) / (1 + Inflation) − 1"""
    return (_ONE + yield_nominal) / (_ONE + inflation) - _ONE


def yield_after_tax(yield_gross: Decimal, tax_rate: Decimal) -> Decimal:
    """Net yield after applying tax to coupon."""
    return yield_gross * (_ONE - tax_rate)


# ═══════════════════════════════════════════════════════════════════════════
# Accrued Interest & Settlement
# ═══════════════════════════════════════════════════════════════════════════

def days_since_last_coupon(
    issue_date: Optional[date],
    valuation_date: Optional[date],
    frequency_n: int = 2,
) -> int:
    """Days elapsed in the current coupon period (pro-rata)."""
    if not issue_date or not valuation_date:
        return 0
    days_total = (valuation_date - issue_date).days
    period_days = int(365 / frequency_n)
    return days_total % period_days if period_days > 0 else 0


def calc_juro_corrido(
    valor_nominal: Decimal,
    coupon_rate: Decimal,
    days_since_last: int,
    frequency_n: int = 2,
) -> Decimal:
    """Pro-rata accrued interest before tax."""
    days_period = Decimal(365) / Decimal(frequency_n)
    coupon_period = valor_nominal * coupon_rate / Decimal(frequency_n)
    return coupon_period * Decimal(days_since_last) / days_period


def calc_liquidation(
    quantity: int,
    par_value_unit: Decimal,
    clean_price_pct: Decimal,
    coupon_rate: Decimal,
    days_since_last: int,
    coupon_tax_rate: Decimal = Decimal("0.10"),
    commission_pct: Decimal = Decimal("0.00395"),
    frequency_n: int = 2,
) -> Dict[str, Decimal]:
    """
    Full settlement calculation:
      - Clean price
      - Accrued interest (gross → net after IAC)
      - Dirty price
      - Commission (0.395%)
      - Total settlement
    """
    vn_total = Decimal(quantity) * par_value_unit
    clean_price_unit = par_value_unit * clean_price_pct / _HUNDRED
    clean_price_total = Decimal(quantity) * clean_price_unit

    accrued_gross = calc_juro_corrido(vn_total, coupon_rate, days_since_last, frequency_n)
    accrued_tax = accrued_gross * coupon_tax_rate
    accrued_net = accrued_gross - accrued_tax

    dirty_price_total = clean_price_total + accrued_net
    commissions = dirty_price_total * commission_pct
    total_settlement = dirty_price_total + commissions

    return {
        "valor_nominal_total": quantize_money(vn_total),
        "clean_price_unit": quantize_money(clean_price_unit),
        "clean_price_total": quantize_money(clean_price_total),
        "accrued_gross": quantize_money(accrued_gross),
        "accrued_tax": quantize_money(accrued_tax),
        "accrued_net": quantize_money(accrued_net),
        "dirty_price_total": quantize_money(dirty_price_total),
        "commissions": quantize_money(commissions),
        "total_settlement": quantize_money(total_settlement),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Cash Flow Generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_cash_flows(
    par_value: Decimal,
    coupon_rate: Decimal,
    years_to_maturity: Decimal,
    frequency_n: int = 2,
    coupon_tax_rate: Decimal = Decimal("0.10"),
) -> List[Dict]:
    """Generate projected cash flows: coupons + redemption (no DB)."""
    n_coupons = int((years_to_maturity * Decimal(frequency_n)).quantize(Decimal("1")))
    if n_coupons <= 0:
        return []

    coupon_gross = par_value * coupon_rate / Decimal(frequency_n)
    tax = coupon_gross * coupon_tax_rate
    coupon_net = coupon_gross - tax

    flows: list[dict] = []
    for i in range(1, n_coupons + 1):
        t = Decimal(i) / Decimal(frequency_n)
        is_last = (i == n_coupons)
        redemption = par_value if is_last else Decimal(0)
        flows.append({
            "n": i,
            "t_years": float(t),
            "coupon_gross": float(coupon_gross),
            "tax": float(tax),
            "coupon_net": float(coupon_net),
            "redemption": float(redemption),
            "total_flow": float(coupon_net + redemption),
        })
    return flows


# ═══════════════════════════════════════════════════════════════════════════
# Duration, Convexity & Price
# ═══════════════════════════════════════════════════════════════════════════

def calc_duration(
    cash_flows: List[Tuple[Decimal, Decimal]],
    yield_market: Decimal,
) -> Dict[str, Decimal]:
    """
    From a list of (time_years, flow_amount), compute:
      - Macaulay duration
      - Modified duration
      - Convexity
      - Theoretical PV price
    """
    pv_total = Decimal(0)
    weighted_t = Decimal(0)
    convex_sum = Decimal(0)

    for t, cf in cash_flows:
        denom = (_ONE + yield_market) ** t
        pv = cf / denom
        pv_total += pv
        weighted_t += t * pv
        convex_sum += t * (t + _ONE) * pv

    if pv_total == 0:
        return {
            "macaulay": Decimal(0),
            "modified": Decimal(0),
            "convexity": Decimal(0),
            "theoretical_price": Decimal(0),
        }

    macaulay = weighted_t / pv_total
    modified = macaulay / (_ONE + yield_market)
    convexity = convex_sum / (pv_total * (_ONE + yield_market) ** 2)

    return {
        "macaulay": macaulay,
        "modified": modified,
        "convexity": convexity,
        "theoretical_price": pv_total,
    }


def price_impact_yield_shock(
    current_price: Decimal,
    modified_duration: Decimal,
    convexity: Decimal,
    delta_yield: Decimal,
) -> Dict[str, Decimal]:
    """
    2nd-order Taylor approximation for price impact of yield shock:
        ΔP/P ≈ -ModDur · Δy + ½ · Conv · (Δy)²
    """
    dur_effect = -modified_duration * delta_yield
    conv_effect = _HALF * convexity * (delta_yield ** 2)
    pct_change = dur_effect + conv_effect
    new_price = current_price * (_ONE + pct_change)

    return {
        "pct_change": pct_change,
        "duration_effect": dur_effect,
        "convexity_effect": conv_effect,
        "new_price": new_price,
        "pnl": new_price - current_price,
    }


# ═══════════════════════════════════════════════════════════════════════════
# YTM Solver
# ═══════════════════════════════════════════════════════════════════════════

def solve_ytm(
    cash_flows: List[Tuple[Decimal, Decimal]],
    market_price: Decimal,
    initial_guess: Decimal = Decimal("0.20"),
    max_iter: int = 60,
    tol: Decimal = Decimal("0.0000001"),
) -> Decimal:
    """
    Yield-to-Maturity via Newton-Raphson on the PV function.

    Returns the periodic yield that equates PV(cash_flows) with market_price.
    For Angola OT, typical initial guess is 0.20 (20% nominal).
    Converges in ~5-8 iterations in practice.
    """
    y = initial_guess
    for _ in range(max_iter):
        pv = Decimal(0)
        dpv = Decimal(0)
        for t, cf in cash_flows:
            denom = (_ONE + y) ** t
            pv += cf / denom
            dpv -= t * cf / (denom * (_ONE + y))
        diff = pv - market_price
        if abs(diff) < tol:
            return y
        if dpv == 0:
            break
        y = y - diff / dpv
        if y < Decimal("-0.99"):
            y = Decimal("-0.99")
    return y
