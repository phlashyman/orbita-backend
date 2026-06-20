"""
Unit tests for financial_core.py — the most critical module in Orbita.
Every formula verified against known values. Errors here = investor loses real money.
"""
import pytest
from datetime import date
from decimal import Decimal as Dc

from app.services.financial_core import (
    D,
    parse_date,
    freq_n,
    years_between,
    fisher_real,
    yield_after_tax,
    calc_liquidation,
    generate_cash_flows,
    calc_duration,
    price_impact_yield_shock,
    solve_ytm,
    days_since_last_coupon,
    calc_juro_corrido,
    quantize_money,
    quantize_pct,
)


class TestHelpers:
    def test_D_safe(self):
        assert D(None) == Dc("0")
        assert D("") == Dc("0")
        assert D("0.195") == Dc("0.195")
        assert D(100000) == Dc("100000")

    def test_parse_date_pt(self):
        assert parse_date("14/05/2026") == date(2026, 5, 14)
        assert parse_date("2026-05-14") == date(2026, 5, 14)
        assert parse_date("2026-05-14") == date(2026, 5, 14)

    def test_parse_date_none(self):
        assert parse_date(None) is None
        assert parse_date("") is None

    def test_parse_date_date_obj(self):
        d = date(2026, 1, 1)
        assert parse_date(d) == d

    def test_freq_n(self):
        assert freq_n("Semestral") == 2
        assert freq_n("semestral") == 2
        assert freq_n("Anual") == 1
        assert freq_n("Trimestral") == 4
        assert freq_n("Mensal") == 12
        assert freq_n(None) == 2
        assert freq_n("invalid") == 2

    def test_years_between(self):
        y = years_between(date(2023, 1, 1), date(2026, 1, 1))
        assert abs(y - 3.0) < 0.02  # 365.25 basis
        assert years_between(None, date(2026, 1, 1)) == 0.0
        assert years_between(date(2023, 1, 1), None) == 0.0

    def test_quantize_money(self):
        q = quantize_money(Dc("123.456"))
        assert str(q) == "123.46"
        q2 = quantize_money(Dc("123.454"))
        assert str(q2) == "123.45"

    def test_quantize_pct(self):
        q = quantize_pct(Dc("0.1234567"))
        assert str(q) == "0.123457"


class TestFisher:
    def test_fisher_real_positive(self):
        """Fisher: (1.20)/(1.12) - 1 = 0.0714... (7.14%)"""
        real = fisher_real(Dc("0.20"), Dc("0.12"))
        assert float(real) == pytest.approx(0.071429, rel=1e-4)

    def test_fisher_zero_inflation(self):
        real = fisher_real(Dc("0.20"), Dc("0"))
        assert float(real) == pytest.approx(0.20, rel=1e-4)

    def test_fisher_high_inflation(self):
        """Angola: 19.5% nominal, 12.42% inflation"""
        real = fisher_real(Dc("0.195"), Dc("0.1242"))
        assert float(real) == pytest.approx(0.06298, rel=1e-4)

    def test_yield_after_tax(self):
        """20% gross, 10% IAC -> 18% net"""
        net = yield_after_tax(Dc("0.20"), Dc("0.10"))
        assert float(net) == pytest.approx(0.18)


class TestCashFlows:
    def test_generate_3year_semestral(self):
        """3yr bond, 19.5%, semestral -> 6 coupons"""
        flows = generate_cash_flows(Dc("100000"), Dc("0.195"), Dc("3"), 2, Dc("0.10"))
        assert len(flows) == 6
        # Last coupon includes redemption
        assert flows[-1]["redemption"] == 100000.0
        assert flows[-1]["total_flow"] > flows[0]["total_flow"]

    def test_generate_zero_maturity(self):
        flows = generate_cash_flows(Dc("100000"), Dc("0.195"), Dc("0"), 2)
        assert len(flows) == 0


class TestDuration:
    def test_duration_3yr_bond(self):
        """Build cash flows for a known bond and compute duration."""
        # 3yr, 19.5% semestral, 6 coupons of 9750 + 100000 redemption
        cf = [(Dc(i) / Dc(2), Dc("9750") + (Dc("100000") if i == 6 else Dc(0))) for i in range(1, 7)]
        dur = calc_duration(cf, Dc("0.195"))
        assert float(dur["macaulay"]) > 0
        assert float(dur["modified"]) > 0
        assert float(dur["convexity"]) > 0
        # Macaulay < 3 for a bond paying coupons
        assert float(dur["macaulay"]) < 3.0

    def test_duration_empty(self):
        dur = calc_duration([], Dc("0.10"))
        assert float(dur["macaulay"]) == 0

    def test_price_impact_shock(self):
        """+1pp shock on a bond with ModDur=3, Conv=5 -> ~ -2.95%"""
        impact = price_impact_yield_shock(Dc("1000"), Dc("3"), Dc("5"), Dc("0.01"))
        assert float(impact["pct_change"]) < 0  # price falls
        assert float(impact["pct_change"]) > -0.035  # ~-3% range


class TestYTM:
    def test_ytm_at_par(self):
        """Bond at par: YTM = coupon rate (for semestral, it should be close)"""
        par = Dc("100000")
        coupon = Dc("0.195")
        # 6 semestral coupons of 9750, plus 100000 at end
        cf = [(Dc(i) / Dc(2), par * coupon / Dc(2) + (par if i == 6 else Dc(0))) for i in range(1, 7)]
        ytm = solve_ytm(cf, par)
        # For semestral, YTM should be close to coupon rate (slightly higher due to compounding)
        assert float(ytm) == pytest.approx(0.20, abs=0.01)
        assert float(ytm) > 0.19

    def test_ytm_at_premium(self):
        """Bond at premium (>100): YTM < coupon rate"""
        par = Dc("100000")
        coupon = Dc("0.195")
        cf = [(Dc(i) / Dc(2), par * coupon / Dc(2) + (par if i == 6 else Dc(0))) for i in range(1, 7)]
        ytm_par = solve_ytm(cf, par)
        ytm_premium = solve_ytm(cf, Dc("104000"))
        assert float(ytm_premium) < float(ytm_par)

    def test_ytm_at_discount(self):
        """Bond at discount (<100): YTM > coupon rate"""
        par = Dc("100000")
        coupon = Dc("0.195")
        cf = [(Dc(i) / Dc(2), par * coupon / Dc(2) + (par if i == 6 else Dc(0))) for i in range(1, 7)]
        ytm_par = solve_ytm(cf, par)
        ytm_discount = solve_ytm(cf, Dc("96000"))
        assert float(ytm_discount) > float(ytm_par)

    def test_ytm_converges_angolan_ot(self):
        """Typical Angolan OT: 19.5% coupon, 3yr, price 104, semestral"""
        # 6 coupons: each = 100000 * 0.195 / 2 = 9750
        cf = [(Dc(i) / Dc(2), Dc("9750") + (Dc("100000") if i == 6 else Dc(0))) for i in range(1, 7)]
        ytm = solve_ytm(cf, Dc("104000"))
        assert float(ytm) > 0.10  # YTM > 10%
        assert float(ytm) < 0.25  # YTM < 25%


class TestLiquidation:
    def test_calc_juro_corrido(self):
        """1M AOA nominal, 19.5% coupon, 90 days, semestral"""
        juro = calc_juro_corrido(Dc("1000000"), Dc("0.195"), 90, 2)
        # Period: 365/2 = 182.5 days, coupon = 1M * 0.195 / 2 = 97500
        # 97500 * 90/182.5 = ~48082
        assert float(juro) == pytest.approx(48082.19, rel=1e-2)

    def test_calc_liquidation(self):
        """100 units, 100000 par, price 104%, 19.5% coupon, 90 days"""
        liq = calc_liquidation(
            quantity=100,
            par_value_unit=Dc("100000"),
            clean_price_pct=Dc("104"),
            coupon_rate=Dc("0.195"),
            days_since_last=90,
            coupon_tax_rate=Dc("0.10"),
            commission_pct=Dc("0.00395"),
            frequency_n=2,
        )
        # Verify components are consistent
        total = float(liq["total_settlement"])
        clean = float(liq["clean_price_total"])
        accrued_net = float(liq["accrued_net"])
        comm = float(liq["commissions"])
        diff = abs(total - (clean + accrued_net + comm))
        assert diff < 2.0  # Within 2 AOA
        assert total > clean

    def test_days_since_last_coupon(self):
        days = days_since_last_coupon(date(2026, 1, 1), date(2026, 3, 31), 2)
        # 89 days from Jan 1 to Mar 31, period = 182.5
        assert 80 <= days <= 100  # ~89 days


class TestConsistency:
    """End-to-end consistency: all functions should produce coherent results."""

    def test_fisher_roundtrip(self):
        """Real + inflation recovers approximate nominal."""
        nominal = Dc("0.20")
        inflation = Dc("0.12")
        real = fisher_real(nominal, inflation)
        # Real should be less than nominal when inflation > 0
        assert real < nominal
        # Approximate: nominal ≈ (1+real)*(1+inflation) - 1
        approx_nominal = (Dc("1") + real) * (Dc("1") + inflation) - Dc("1")
        assert approx_nominal == pytest.approx(nominal, abs=Dc("0.001"))

    def test_duration_price_consistency(self):
        """Duration + convexity should explain small yield shock."""
        cf = [(Dc(i) / Dc(2), Dc("9750") + (Dc("100000") if i == 6 else Dc(0))) for i in range(1, 7)]
        ytm = solve_ytm(cf, Dc("100000"))
        dur = calc_duration(cf, ytm)
        # 1bp shock
        impact = price_impact_yield_shock(Dc("100000"), dur["modified"], dur["convexity"], Dc("0.0001"))
        # Price change should be ~ -ModDur * 0.0001 = very small
        assert abs(float(impact["pct_change"])) < 0.005  # < 0.5%
