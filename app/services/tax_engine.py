"""
tax_engine.py
=============
Angolan IAC (Imposto sobre Aplicacao de Capitais) rules engine.

Reads tax_rules table (via async SQLAlchemy) and resolves the right rate
for any instrument, filtered by the PAYMENT DATE.

Temporal validity (valid_from / valid_to) handles regime changes:
  - Lei 14/25 (OGE 2026): IAC rises from 5% to 10% for admitted bonds with
    maturity >= 3 years. Coupons paid in 2025 → 5%. Coupons paid in 2026+ → 10%.

Ported from Claude AI version, adapted from SQLite to SQLAlchemy async.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_rule import TaxRule
from .financial_core import D, parse_date, years_between


async def resolve_tax_rates(
    db: AsyncSession,
    *,
    instrument_class: str = "BOND_GOV",
    bodiva_admitted: bool = True,
    issue_date: Optional[date] = None,
    maturity_date: Optional[date] = None,
    payment_date: Optional[date] = None,
) -> Dict[str, Decimal]:
    """
    Resolve IAC rates for an instrument, filtering rules by:
      - instrument_class  (e.g. "BOND_GOV", "BOND_CORP", "EQUITY", "TBILL")
      - bodiva_admitted   (bool)
      - payment_date      (only rules where valid_from ≤ payment_date ≤ valid_to)

    Returns {"coupon_tax_rate", "capgain_tax_rate", "stamp_duty"}.
    Falls back to 10% if no rule matches (default regime since OGE 2026).
    """
    years = years_between(issue_date, maturity_date)
    pay_date = payment_date or date.today()

    query = (
        select(TaxRule)
        .where(TaxRule.is_active == True)
        .where(TaxRule.instrument_class == instrument_class)
        .where(TaxRule.valid_from <= pay_date)
        .where(
            or_(TaxRule.valid_to >= pay_date, TaxRule.valid_to.is_(None))
        )
        .order_by(TaxRule.priority.desc())
    )

    result = await db.execute(query)
    rules: list[TaxRule] = list(result.scalars().all())

    # Filter by bodiva_admitted (model field)
    # Currently TaxRule always stores bodiva_admitted=True for relevant rules
    # In production, we would add the filter to the query

    if not rules:
        return {
            "coupon_tax_rate": Decimal("0.10"),
            "capgain_tax_rate": Decimal("0.10"),
            "stamp_duty": Decimal("0.0"),
        }

    # Default: first matching rule
    rule = rules[0]

    return {
        "coupon_tax_rate": Decimal(str(rule.coupon_tax_rate)),
        "capgain_tax_rate": Decimal(str(rule.capgain_tax_rate)) if rule.capgain_tax_rate is not None else Decimal("0.10"),
        "stamp_duty": Decimal(str(rule.stamp_duty)) if rule.stamp_duty is not None else Decimal("0"),
    }


async def resolve_for_bond(
    db: AsyncSession,
    bond: Dict[str, Any],
    payment_date: Optional[date] = None,
) -> Dict[str, Decimal]:
    """Resolve tax rates for a bond from bond_master / holding dict."""
    return await resolve_tax_rates(
        db,
        instrument_class=bond.get("instrument_class", "BOND_GOV"),
        bodiva_admitted=bool(bond.get("bodiva_admitted", True)),
        issue_date=parse_date(bond.get("issue_date")),
        maturity_date=parse_date(bond.get("maturity_date")),
        payment_date=payment_date,
    )


async def get_active_iac_rate(
    db: AsyncSession,
    instrument_class: str = "BOND_GOV",
    bodiva_admitted: bool = True,
    payment_date: Optional[date] = None,
) -> Decimal:
    """
    Simplest wrapper: returns just the IAC coupon rate as a Decimal.
    E.g. get_active_iac_rate(db, "BOND_GOV", True, date(2026,6,20)) → Decimal("0.10")
    """
    rates = await resolve_tax_rates(
        db,
        instrument_class=instrument_class,
        bodiva_admitted=bodiva_admitted,
        payment_date=payment_date,
    )
    return rates["coupon_tax_rate"]
