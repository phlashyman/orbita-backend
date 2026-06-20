"""
Log de interacções com o AI Assistant (Claude).
Regista cada pedido para controlo de custos, auditoria e melhoria.

Pattern (portado do Claude AI's ai_agent.py):
  - Haiku para auto-insights (rápido, barato)
  - Sonnet para análises profundas e chat
  - Daily spending cap (default $5/dia)
  - MD5 cache para insights repetidos
"""
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text, JSON
from app.database import Base
from app.utils.base import BaseMixin


class AIFeature(str, enum.Enum):
    PORTFOLIO_ANALYSIS = "PORTFOLIO_ANALYSIS"
    CHAT = "CHAT"
    WEEKLY_REPORT = "WEEKLY_REPORT"
    ALERT = "ALERT"
    NEWS = "NEWS"
    AUTO_INSIGHT = "AUTO_INSIGHT"
    PORTFOLIO_BUILDER = "PORTFOLIO_BUILDER"


class AIAssistantLog(Base, BaseMixin):
    """
    Registo de uma interacção com a API da Anthropic (Claude).
    Usado para tracking de custos, auditoria e debugging.
    """
    __tablename__ = "ai_assistant_logs"

    user_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    family_id = Column(ForeignKey("families.id", ondelete="CASCADE"), nullable=True)

    # Feature que originou o pedido
    feature = Column(SAEnum(AIFeature), nullable=False)

    # Modelo usado
    model = Column(String(50), nullable=False, comment="claude-haiku-4-5 / claude-sonnet-4-6")
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True, comment="Custo estimado do request")

    # Conteúdo
    user_message = Column(Text, nullable=True)
    response_excerpt = Column(String(500), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Erro
    error = Column(String(500), nullable=True)
    was_capped = Column(Boolean, default=False, comment="Rejeitado por daily cap?")

    # Metadados
    cache_hit = Column(Boolean, default=False, comment="Usou cache MD5?")
    metadata_json = Column(JSON, nullable=True)
