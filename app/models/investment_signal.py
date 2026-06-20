"""
Sinais de investimento — unifica recomendação de estratégia, oportunidade de swap,
e alertas de portfolio num único modelo.

Tipos:
  - SWAP: oportunidade de trocar um título por outro
  - BUY/SELL/HOLD: recomendação de acção
  - DCA: sugestão de reforço periódico
  - BULLET/BARBELL/LADDER: estratégias de yield curve
  - REBALANCE: necessidade de rebalanceamento
  - RISK_ALERT: alerta de risco (duration, concentração, liquidez)
  - MARKET_SIGNAL: sinal de mercado (spread compression, volume anomaly)
"""
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Enum as SAEnum, JSON, Text
from app.database import Base
from app.utils.base import BaseMixin


class SignalType(str, enum.Enum):
    SWAP = "SWAP"
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    DCA = "DCA"
    BULLET = "BULLET"
    BARBELL = "BARBELL"
    LADDER = "LADDER"
    REBALANCE = "REBALANCE"
    RISK_ALERT = "RISK_ALERT"
    MARKET_SIGNAL = "MARKET_SIGNAL"


class SignalSeverity(str, enum.Enum):
    INFO = "INFO"
    WATCH = "WATCH"
    ALERT = "ALERT"
    CRITICAL = "CRITICAL"


class InvestmentSignal(Base, BaseMixin):
    """
    Sinal de investimento — pode ser uma recomendação, alerta ou oportunidade.
    """
    __tablename__ = "investment_signals"

    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    portfolio_id = Column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Tipo e severidade
    signal_type = Column(SAEnum(SignalType), nullable=False)
    severity = Column(SAEnum(SignalSeverity), default=SignalSeverity.INFO)

    # Título e descrição (PT-PT)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Campos específicos para SWAP
    source_ticker = Column(String(20), nullable=True, comment="Ticker detido (para swap)")
    target_ticker = Column(String(20), nullable=True, comment="Ticker candidato (para swap)")
    estimated_benefit = Column(Float, nullable=True, comment="Benefício líquido estimado (AOA)")

    # Justificação
    justification = Column(Text, nullable=True, comment="Justificação detalhada (pode ser AI-gerada)")

    # Acção recomendada
    action_url = Column(String(500), nullable=True, comment="Link para executar a acção")
    is_actionable = Column(Boolean, default=False)
    is_dismissed = Column(Boolean, default=False)
    executed_at = Column(DateTime, nullable=True)

    # Metadados
    expires_at = Column(DateTime, nullable=True, comment="Sinal expira após esta data")
    source = Column(String(50), nullable=True, comment="Origem: 'plan_engine', 'market_intelligence', 'risk_manager', 'ai'")
    metadata_json = Column(JSON, nullable=True)
