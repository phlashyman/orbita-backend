"""
Integration tests — cross-module consistency.

Tests key flows:
  1. YTM -> IAC -> Real yield pipeline
  2. Portfolio analytics pure function consistency
  3. Scenario signal detection chain
  4. Strategy recommendation consistency
"""
import pytest
from decimal import Decimal as Dc

from app.services.financial_core import (
    generate_cash_flows, solve_ytm, yield_after_tax, fisher_real,
    D, parse_date, calc_duration, calc_liquidation,
)
from app.services.portfolio_analytics import (
    calc_sharpe_ratio, calc_concentration_hhi, calc_effective_n,
    calc_var_parametric, calc_var_historic, calc_cvar, calc_drawdown,
)
from app.services.plan_engine import (
    instrument_real_yield, buy_window, swap_benefit, is_swap_recommended,
    classify_plan_instruments, _is_stale,
)
from app.services.market_intelligence import (
    detect_spread_compression, detect_imbalance_flip, detect_liquidity_vacuum,
    detect_volume_anomaly, run_detection,
)
from app.services.risk_manager import generate_early_warnings, PREBUILT_SCENARIOS, stress_test_holding
from app.services.investment_strategies import suggest_strategies, compare_strategies
from app.services.investor_profile import calculate_profile, get_quiz_questions
from app.models.investor_profile import QuizMode
from app.schemas.investment import QuizAnswer


class TestYTMPipeline:
    """YTM -> IAC -> Real yield should be coherent."""

    def test_full_pipeline(self):
        """Angolan OT: 19.5% coupon, 3yr, price 104%, inflation 12%, IAC 10%"""
        result = instrument_real_yield(
            par_value=100000, coupon_rate=0.195, years_to_maturity=3.0,
            frequency_n=2, market_price_pct=104.0, inflation=0.12, iac_rate=0.10,
        )
        assert result["ytm"] is not None
        assert result["net_yield"] is not None
        assert result["real_yield"] is not None
        # Real yield should be lower than net yield when inflation > 0
        assert result["real_yield"] < result["net_yield"]

    def test_premium_lowers_yield(self):
        """Higher price = lower YTM."""
        at_par = instrument_real_yield(
            par_value=100000, coupon_rate=0.195, years_to_maturity=3.0,
            frequency_n=2, market_price_pct=100.0, inflation=0.12, iac_rate=0.10)
        at_premium = instrument_real_yield(
            par_value=100000, coupon_rate=0.195, years_to_maturity=3.0,
            frequency_n=2, market_price_pct=110.0, inflation=0.12, iac_rate=0.10)
        assert at_par["ytm"] > at_premium["ytm"]

    def test_IAC_reduces_yield(self):
        """Higher IAC = lower net yield."""
        low_iac = instrument_real_yield(
            par_value=100000, coupon_rate=0.195, years_to_maturity=3.0,
            frequency_n=2, market_price_pct=104.0, inflation=0.12, iac_rate=0.05)
        high_iac = instrument_real_yield(
            par_value=100000, coupon_rate=0.195, years_to_maturity=3.0,
            frequency_n=2, market_price_pct=104.0, inflation=0.12, iac_rate=0.10)
        assert low_iac["net_yield"] > high_iac["net_yield"]


class TestBuyWindow:
    def test_buy_at_good_yield(self):
        bw = buy_window(real_yield=0.08, objective_real_yield=0.05, cap_entry=5.0)
        assert bw["status"] == "COMPRAR"

    def test_wait_at_bad_yield(self):
        bw = buy_window(real_yield=0.02, objective_real_yield=0.05, cap_entry=5.0)
        assert bw["status"] == "AGUARDAR"

    def test_wait_at_zero_liquidity(self):
        bw = buy_window(real_yield=0.08, objective_real_yield=0.05, cap_entry=0.0, min_cap_entry=1.0)
        assert bw["status"] == "AGUARDAR"

    def test_wait_at_stale_price(self):
        bw = buy_window(real_yield=0.08, objective_real_yield=0.05, cap_entry=5.0, price_is_stale=True)
        assert bw["status"] == "AGUARDAR"


class TestSwapBenefit:
    def test_positive_swap(self):
        """Swapping a 6% real bond for a 9% real bond over 3 years."""
        sb = swap_benefit(
            h_clean_value=1040000, h_accrued_net=24000, h_acquisition_clean=1000000,
            h_real_yield=0.06, h_capgain_rate=0.10, c_real_yield=0.09,
            commission_pct=0.00395, horizon_years=3.0,
        )
        assert sb["swap_gain"] > 0  # Positive gain

    def test_negative_swap(self):
        """Swapping for a worse bond should lose money."""
        sb = swap_benefit(
            h_clean_value=1040000, h_accrued_net=24000, h_acquisition_clean=1000000,
            h_real_yield=0.09, h_capgain_rate=0.10, c_real_yield=0.06,
            commission_pct=0.00395, horizon_years=3.0,
        )
        assert sb["swap_gain"] < 0

    def test_recommended_with_entry(self):
        sb = swap_benefit(
            h_clean_value=1040000, h_accrued_net=24000, h_acquisition_clean=1000000,
            h_real_yield=0.06, h_capgain_rate=0.10, c_real_yield=0.09,
            commission_pct=0.00395, horizon_years=3.0,
        )
        rec = is_swap_recommended(sb, cap_exit_h=5.0, cap_entry_c=5.0, min_gain_pct=1.0)
        assert rec["recommended"] == True

    def test_not_recommended_no_liquidity(self):
        sb = swap_benefit(
            h_clean_value=1040000, h_accrued_net=24000, h_acquisition_clean=1000000,
            h_real_yield=0.06, h_capgain_rate=0.10, c_real_yield=0.09,
            commission_pct=0.00395, horizon_years=3.0,
        )
        rec = is_swap_recommended(sb, cap_exit_h=0.0, cap_entry_c=0.0)
        assert rec["recommended"] == False


class TestSignals:
    def test_spread_compression(self):
        s = detect_spread_compression(0.5, 2.0)
        assert s is not None
        assert "compressao" in s["title"].lower()

    def test_no_compression(self):
        s = detect_spread_compression(1.9, 2.0)
        assert s is None

    def test_imbalance_flip(self):
        s = detect_imbalance_flip(0.15, -0.10)
        assert s is not None
        assert "compradora" in s["title"].lower()

    def test_liquidity_vacuum(self):
        s = detect_liquidity_vacuum(True, False)
        assert s is not None
        assert "unilateral" in s["title"].lower()

    def test_no_vacuum_if_both_sides(self):
        s = detect_liquidity_vacuum(True, True)
        assert s is None

    def test_volume_anomaly(self):
        s = detect_volume_anomaly(50000, 10000)
        assert s is not None
        assert "Volume" in s["title"]

    def test_run_detection_comprehensive(self):
        """Run all detectors on rich test data."""
        current = {
            "spread_pct": 0.5, "imbalance": 0.2, "volume_qty": 50000,
            "n_trades": 1, "bid_qty": 50000, "ask_qty": 10000,
        }
        baseline = {
            "spread_median": 2.0, "previous_imbalance": -0.1,
            "volume_median": 10000, "bid_qty_median": 10000,
        }
        signals = run_detection(current, baseline)
        assert len(signals) >= 3  # spread, imbalance, volume, trade, bid surge


class TestEarlyWarnings:
    def test_all_warnings_trigger(self):
        """A portfolio in dire straits should trigger most warnings."""
        metrics = {
            "modified_duration": 8.5, "hhi": 0.30, "liquidity_score": 1.5,
            "max_drawdown_pct": 0.18, "weighted_real_yield": -0.02,
            "cvar_95_1m_pct": 0.12, "convexity": -1.0,
        }
        warnings = generate_early_warnings(metrics)
        assert len(warnings) >= 5  # Should trigger most

    def test_healthy_portfolio_no_warnings(self):
        metrics = {
            "modified_duration": 3.0, "hhi": 0.15, "liquidity_score": 10.0,
            "max_drawdown_pct": 0.05, "weighted_real_yield": 0.05,
            "cvar_95_1m_pct": 0.03, "convexity": 2.0,
        }
        warnings = generate_early_warnings(metrics)
        assert len(warnings) == 0


class TestScenarios:
    def test_all_scenarios_defined(self):
        assert len(PREBUILT_SCENARIOS) == 4
        names = [s["name"] for s in PREBUILT_SCENARIOS]
        assert "Estabilidade" in names
        assert "Crise Cambial" in names


class TestStressTest:
    def test_bond_stress(self):
        bond = {
            "ticker": "OT-TEST", "coupon_rate": 0.195, "par_value": 100000,
            "current_price": 104000, "quantity": 10, "current_value": 1040000,
            "instrument_class": "BOND_GOV",
            "issue_date": "2023-01-01", "maturity_date": "2026-01-01",
            "frequency_n": 2,
        }
        result = stress_test_holding(bond, PREBUILT_SCENARIOS[2]["params"])
        assert result["impact_pct"] < 0  # Adverse scenario
        assert result["new_value"] < result["current_value"]


class TestStrategies:
    def test_suggest_for_conservador(self):
        suggestions = suggest_strategies("CONSERVADOR")
        assert len(suggestions) > 0
        assert suggestions[0]["key"] == "ladder"  # Ladder best for conservative

    def test_suggest_for_aggressivo(self):
        suggestions = suggest_strategies("AGRESSIVO", yield_curve_slope=2.5)
        assert suggestions[0]["key"] == "riding_the_curve"

    def test_compare_returns_all_strategies(self):
        c = compare_strategies(1000000, 0.195, 5)
        for k in ["bullet", "ladder", "barbell", "riding_the_curve"]:
            assert k in c, f"Missing {k}"


class TestInvestorProfile:
    def test_rapid_all_ones(self):
        answers = [QuizAnswer(pergunta_id=i, resposta=1, score=1.0) for i in range(1, 7)]
        result = calculate_profile(answers)
        assert result["perfil"].value == "CONSERVADOR"

    def test_rapid_all_fives(self):
        answers = [QuizAnswer(pergunta_id=i, resposta=5, score=5.0) for i in range(1, 7)]
        result = calculate_profile(answers)
        assert result["perfil"].value == "AGRESSIVO"

    def test_rapid_all_threes(self):
        answers = [QuizAnswer(pergunta_id=i, resposta=3, score=3.0) for i in range(1, 7)]
        result = calculate_profile(answers)
        assert result["perfil"].value == "MODERADO"

    def test_allocation_sums_to_one(self):
        answers = [QuizAnswer(pergunta_id=i, resposta=3, score=3.0) for i in range(1, 7)]
        result = calculate_profile(answers)
        alloc = {k: v for k, v in result["alocacao"].items() if k != "international_pct"}
        total = sum(alloc.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_quiz_questions_rapido(self):
        q = get_quiz_questions(QuizMode.RAPIDO)
        assert q["total"] == 6

    def test_quiz_questions_completo(self):
        q = get_quiz_questions(QuizMode.COMPLETO)
        assert q["total"] == 10
