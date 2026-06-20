"""
cashflow_engine.py
==================
Dated cashflow projection at portfolio level.

Difference from financial_core.generate_cash_flows():
  - Generates REAL DATES for each coupon (not just t in years).
  - Resolves IAC AT EACH PAYMENT DATE (2025=5%, 2026+=10% under Lei 14/25).
  - Operates at position level (quantity × par_value).

Ported from Claude AI version, adapted to SQLAlchemy async + BondMaster.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bodiva_market import BondMaster
from .financial_core import D, parse_date, years_between
from .tax_engine import resolve_for_bond


# ═══════════════════════════════════════════════════════════════════════════
# Date helpers
# ═══════════════════════════════════════════════════════════════════════════

def _add_months(d: date, months: int) -> date:
    """Add `months` to a date, clamping to month-end when needed."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = d.day
    while day > 0:
        try:
            return date(y, m, day)
        except ValueError:
            day -= 1
    return date(y, m, 1)


def _coupon_dates(
    issue_date: date,
    maturity_date: date,
    frequency_n: int,
) -> List[date]:
    """
    Generate all coupon dates for a bond, anchored at issue date.
    Last coupon = maturity date (where redemption also occurs).
    """
    if not issue_date or not maturity_date or frequency_n <= 0:
        return []
    step = 12 // frequency_n  # months between coupons
    dates: list[date] = []
    i = 1
    while True:
        cd = _add_months(issue_date, step * i)
        if cd > maturity_date:
            break
        dates.append(cd)
        i += 1
    # Ensure maturity is in the list
    if not dates or dates[-1] != maturity_date:
        dates.append(maturity_date)
    return dates


# ═══════════════════════════════════════════════════════════════════════════
# Coupon schedule for a single bond position
# ═══════════════════════════════════════════════════════════════════════════

async def bond_coupon_schedule(
    db: AsyncSession,
    bond: Dict[str, Any],
    quantity: float,
    from_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    Future coupon schedule for a bond position (quantity held).

    First enriches the bond dict from BondMaster if fields are missing
    (par_value, issue_date, maturity_date, coupon_rate), then resolves
    IAC per payment date.
    """
    from_date = from_date or date.today()

    ticker = bond.get("ticker")
    needs = ("par_value", "issue_date", "maturity_date", "coupon_rate", "frequency_n")

    # Enrich from BondMaster if needed
    if ticker and any(not bond.get(k) for k in needs):
        result = await db.execute(select(BondMaster).where(BondMaster.ticker == ticker))
        master = result.scalar_one_or_none()
        if master:
            enriched = {
                "par_value": master.par_value,
                "issue_date": master.issue_date,
                "maturity_date": master.maturity_date,
                "coupon_rate": master.coupon_rate,
                "frequency_n": master.frequency_n or 2,
                "instrument_class": master.instrument_class,
                "bodiva_admitted": master.bodiva_admitted,
            }
            merged = {**enriched, **{k: v for k, v in bond.items() if v is not None}}
            bond = merged

    issue = parse_date(bond.get("issue_date"))
    maturity = parse_date(bond.get("maturity_date"))
    coupon_rate = bond.get("coupon_rate")
    freq_n_val = int(bond.get("frequency_n") or 2)
    par = bond.get("par_value")

    if not (issue and maturity and coupon_rate and par and quantity):
        return []

    nominal_total = D(quantity) * D(par)
    coupon_gross = nominal_total * D(coupon_rate) / D(freq_n_val)

    all_dates = _coupon_dates(issue, maturity, freq_n_val)
    out: list[dict] = []
    for idx, cd in enumerate(all_dates, start=1):
        if cd < from_date:
            continue  # already passed

        # IAC in effect AT the payment date
        rates = await resolve_for_bond(db, bond, payment_date=cd)
        iac = rates["coupon_tax_rate"]
        tax = coupon_gross * iac
        coupon_net = coupon_gross - tax
        is_maturity = (cd == maturity)
        redemption = nominal_total if is_maturity else Decimal(0)

        out.append({
            "date": cd,
            "ticker": bond.get("ticker"),
            "n": idx,
            "coupon_gross": float(coupon_gross),
            "iac_rate": float(iac),
            "tax": float(tax),
            "coupon_net": float(coupon_net),
            "redemption": float(redemption),
            "total_flow": float(coupon_net + redemption),
            "is_maturity": is_maturity,
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio-level aggregation
# ═══════════════════════════════════════════════════════════════════════════

async def portfolio_cashflows(
    db: AsyncSession,
    holdings: List[Dict[str, Any]],
    from_date: Optional[date] = None,
    horizon_months: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    All future cash flows for a portfolio (bonds only), sorted by date.
    horizon_months limits projection horizon (None = until last maturity).
    """
    from_date = from_date or date.today()
    limit_date = _add_months(from_date, horizon_months) if horizon_months else None

    flows: list[dict] = []
    for h in holdings:
        if h.get("instrument_class") not in ("BOND_GOV", "BOND_CORP"):
            continue
        qty = h.get("quantity_total") or h.get("quantity")
        if not qty:
            continue
        sched = await bond_coupon_schedule(db, h, qty, from_date=from_date)
        for f in sched:
            if limit_date and f["date"] > limit_date:
                continue
            f = dict(f)
            f["title"] = h.get("title") or h.get("ticker")
            flows.append(f)

    flows.sort(key=lambda x: x["date"])
    return flows


async def next_payment(
    db: AsyncSession,
    holdings: List[Dict[str, Any]],
    from_date: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """
    Next aggregated payment: all flows falling on the earliest future date.
    """
    flows = await portfolio_cashflows(db, holdings, from_date=from_date)
    if not flows:
        return None

    first_date = flows[0]["date"]
    same_day = [f for f in flows if f["date"] == first_date]
    total_net = sum(f["total_flow"] for f in same_day)
    total_gross = sum(f["coupon_gross"] + f["redemption"] for f in same_day)

    return {
        "date": first_date.isoformat(),
        "days_until": (first_date - (from_date or date.today())).days,
        "total_net": total_net,
        "total_gross": total_gross,
        "items": same_day,
        "tickers": [f["ticker"] for f in same_day],
    }


async def monthly_cashflow_table(
    db: AsyncSession,
    holdings: List[Dict[str, Any]],
    from_date: Optional[date] = None,
    months: int = 12,
) -> List[Dict[str, Any]]:
    """
    Aggregate cash flows by month for the next `months` (default 12).
    Returns one row per month (including zero months) for chart display.
    """
    flows = await portfolio_cashflows(db, holdings, from_date=from_date)
    from_date = from_date or date.today()

    # Build month buckets
    buckets: dict[str, dict] = {}
    labels: list[str] = []
    for i in range(months):
        md = _add_months(from_date, i)
        key = f"{md.year}-{md.month:02d}"
        labels.append(key)
        buckets[key] = {"coupons_net": 0.0, "redemptions": 0.0, "total": 0.0}

    label_set = set(labels)
    for f in flows:
        key = f"{f['date'].year}-{f['date'].month:02d}"
        if key not in label_set:
            continue
        buckets[key]["coupons_net"] += f["coupon_net"]
        buckets[key]["redemptions"] += f["redemption"]
        buckets[key]["total"] += f["total_flow"]

    return [{"month": k, **buckets[k]} for k in labels]
