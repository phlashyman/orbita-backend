"""
Snapshot de métricas de analytics e risco do portfolio.
Calculado periodicamente (ou on-demand) pelo portfolio_analytics service.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, JSON
from app.database import Base
from app.utils.base import BaseMixin


class PortfolioAnalytics(Base, BaseMixin):
    """
    Snapshot completo de métricas de um portfolio num dado momento.
    Permite análise temporal e comparação entre períodos.
    """
    __tablename__ = "portfolio_analytics"

    portfolio_id = Column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Métricas de risco
    var_95_1m = Column(Float, nullable=True, comment="VaR 95%, 1 mês — perda máxima esperada")
    var_95_1m_pct = Column(Float, nullable=True, comment="VaR em percentagem do portfolio")
    cvar_95_1m = Column(Float, nullable=True, comment="CVaR / Expected Shortfall 95%")
    cvar_95_1m_pct = Column(Float, nullable=True)

    # Métricas de retorno ajustado ao risco
    sharpe_ratio = Column(Float, nullable=True, comment="(Rp−Rf)/σp, Rf = BNA rate − IAC")
    sortino_ratio = Column(Float, nullable=True, comment="Apenas downside deviation")
    calmar_ratio = Column(Float, nullable=True, comment="Retorno / Max Drawdown")
    information_ratio = Column(Float, nullable=True, comment="Tracking error vs benchmark OT")

    # Métricas de duração e convexidade
    macaulay_duration = Column(Float, nullable=True)
    modified_duration = Column(Float, nullable=True)
    convexity = Column(Float, nullable=True)

    # Métricas de concentração
    hhi = Column(Float, nullable=True, comment="Hirschman-Herfindahl Index")
    gini = Column(Float, nullable=True, comment="Coeficiente de Gini")
    effective_n = Column(Float, nullable=True, comment="N = 1/HHI — diversificação efectiva")

    # Liquidez
    liquidity_score = Column(Float, nullable=True, comment="(Bid-Ask Spread%)⁻¹ × profundidade")
    estimated_slippage_pct = Column(Float, nullable=True)

    # Drawdown
    max_drawdown_pct = Column(Float, nullable=True)
    max_drawdown_duration_days = Column(Integer, nullable=True)

    # Metadados do snapshot
    snapshot_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    portfolio_value = Column(Float, nullable=True)
    total_invested = Column(Float, nullable=True)
    unrealized_pnl = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)

    # Dados brutos do cálculo (úteis para debug/reprocessamento)
    raw_data = Column(JSON, nullable=True)
