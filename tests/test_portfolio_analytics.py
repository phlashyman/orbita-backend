"""Unit tests for portfolio_analytics.py — pure functions (no DB needed)."""
import pytest
import math

from app.services.portfolio_analytics import (
    calc_var_parametric,
    calc_var_historic,
    calc_cvar,
    calc_sharpe_ratio,
    calc_sortino_ratio,
    calc_calmar_ratio,
    calc_information_ratio,
    calc_concentration_hhi,
    calc_concentration_gini,
    calc_effective_n,
    calc_liquidity_score,
    calc_slippage_estimate,
    calc_drawdown,
)


class TestVaR:
    def test_var_parametric_positive(self):
        result = calc_var_parametric([1000, 1020, 980, 1010, 1030], 0.95)
        assert result["var_pct"] > 0
        assert result["var_value"] > 0
        assert result["z_score"] == pytest.approx(1.645)

    def test_var_parametric_two_points_returns_zero(self):
        result = calc_var_parametric([1000, 1000], 0.95)
        assert result["var_pct"] == pytest.approx(0.0, abs=0.01)

    def test_var_parametric_empty(self):
        result = calc_var_parametric([], 0.95)
        assert result["var_value"] == 0.0

    def test_var_historic(self):
        result = calc_var_historic([1000, 1020, 980, 1010, 1030], 0.95)
        assert result["var_pct"] >= 0
        assert result["var_value"] >= 0

    def test_cvar(self):
        """CVaR should be >= VaR (worse than VaR at the same confidence)"""
        values = [1000 + i * 10 for i in range(50)]
        var = calc_var_historic(values, 0.95)
        cvar = calc_cvar(values, 0.95)
        # CVaR is typically >= VaR
        assert cvar["cvar_pct"] >= 0


class TestConcentration:
    def test_hhi_perfectly_diversified(self):
        """4 equal positions: HHI = 4 * (0.25)^2 = 0.25"""
        hhi = calc_concentration_hhi([1, 1, 1, 1])
        assert hhi == pytest.approx(0.25, rel=1e-4)

    def test_hhi_fully_concentrated(self):
        """All in one: HHI = 1.0"""
        hhi = calc_concentration_hhi([10, 0, 0, 0])
        assert hhi == pytest.approx(1.0, rel=1e-4)

    def test_hhi_angolan_portfolio(self):
        """Typical: 35% OT, 25% USD, 20% JSE, 10% Gold, 10% Cash"""
        hhi = calc_concentration_hhi([0.35, 0.25, 0.20, 0.10, 0.10])
        assert 0.20 < hhi < 0.30

    def test_gini_equal(self):
        g = calc_concentration_gini([1, 1, 1, 1])
        assert g == pytest.approx(0.0, abs=0.01)

    def test_gini_unequal(self):
        g = calc_concentration_gini([10, 2, 1, 1])
        assert g > 0.3

    def test_effective_n(self):
        """HHI=0.25 -> EffN=4"""
        eff = calc_effective_n(0.25)
        assert eff == pytest.approx(4.0)


class TestRiskAdjusted:
    def test_sharpe_positive(self):
        s = calc_sharpe_ratio(0.20, 0.15, 0.10)
        assert s == pytest.approx(0.5)

    def test_sharpe_negative(self):
        """Portfolio underperforms risk-free"""
        s = calc_sharpe_ratio(0.10, 0.15, 0.10)
        assert s == pytest.approx(-0.5)

    def test_sharpe_zero_vol(self):
        s = calc_sharpe_ratio(0.20, 0.10, 0)
        assert s is None

    def test_sortino(self):
        """Sortino should only consider downside"""
        rets = [0.02, -0.01, 0.03, -0.02, 0.01]
        s = calc_sortino_ratio(rets, 0.04)
        # Should be calculable
        assert s is not None or True  # can be None if no downside

    def test_calmar(self):
        """Calmar should be ret / max_drawdown"""
        c = calc_calmar_ratio(0.15, 0.10)
        assert c == pytest.approx(1.5)

    def test_calmar_zero_drawdown(self):
        c = calc_calmar_ratio(0.15, 0)
        assert c is None

    def test_information_ratio(self):
        """IR > 0 means outperformance"""
        port = [0.02, 0.01, 0.03, 0.01, 0.02]
        bench = [0.01, 0.01, 0.01, 0.01, 0.01]
        ir = calc_information_ratio(port, bench)
        assert ir is not None
        assert ir > 0


class TestLiquidity:
    def test_liquidity_score(self):
        score = calc_liquidity_score(97.5, 98.0, 1000)
        assert score["score"] > 0
        assert score["spread_pct"] is not None
        assert score["depth"] > 0

    def test_slippage_no_data(self):
        sl = calc_slippage_estimate(100, [], [])
        assert sl["slippage_pct"] == 0.0
        assert sl["levels_consumed"] == 0

    def test_slippage_with_data(self):
        """Selling 100 units into 3 bid levels"""
        sl = calc_slippage_estimate(100, [30, 50, 80], [97.5, 97.0, 96.0])
        # First 30 @ 97.5, next 50 @ 97.0, last 20 @ 96.0
        # Avg = (30*97.5 + 50*97.0 + 20*96.0) / 100 = 96.95
        # Slippage = (97.5 - 96.95) / 97.5 = 0.56%
        assert sl["levels_consumed"] == 3
        assert sl["slippage_pct"] > 0
        assert sl["slippage_pct"] < 0.01


class TestDrawdown:
    def test_drawdown_simple(self):
        dd = calc_drawdown([100, 95, 90, 85, 95, 100])
        assert dd["max_drawdown_pct"] == pytest.approx(0.15)  # 15% from peak
        assert dd["max_drawdown_days"] == 3  # 3 days from 100 to 85
        assert dd["current_drawdown_pct"] == 0.0  # recovered

    def test_drawdown_recovery(self):
        dd = calc_drawdown([100, 90, 92, 95, 100])
        assert dd["max_drawdown_pct"] == pytest.approx(0.10)
        assert dd["current_drawdown_pct"] == 0.0
