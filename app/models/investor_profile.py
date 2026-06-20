"""
Perfil de Investidor — questionário psicométrico e alocação estratégica.

Duas modalidades:
  - RÁPIDO  (6 perguntas, 3 dimensões) → para beginners
  - COMPLETO (10 perguntas, 5 dimensões) → intermédios/avançados, gera IPS

Base técnica: CFA Institute Standards (IPS — Investment Policy Statement).
"""
import enum
from datetime import date
from sqlalchemy import Column, String, Integer, Float, Date, Enum as SAEnum, JSON, ForeignKey
from app.database import Base
from app.utils.base import BaseMixin


class InvestorRiskProfile(str, enum.Enum):
    CONSERVADOR = "CONSERVADOR"
    MODERADO = "MODERADO"
    DINAMICO = "DINAMICO"
    AGRESSIVO = "AGRESSIVO"


class QuizMode(str, enum.Enum):
    RAPIDO = "RAPIDO"        # 6 perguntas
    COMPLETO = "COMPLETO"    # 10 perguntas


class InvestorProfile(Base, BaseMixin):
    """
    Perfil de investidor calculado a partir do questionário psicométrico.
    Guarda o resultado mais recente; o histórico fica na tabela risk_profile_answers.
    """
    __tablename__ = "investor_profiles"

    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mode = Column(SAEnum(QuizMode), default=QuizMode.RAPIDO, nullable=False)

    # Scores por dimensão (1.0 - 5.0)
    tolerancia_risco = Column(Float, nullable=True)
    horizonte_temporal = Column(Float, nullable=True)
    objectivos_retorno = Column(Float, nullable=True)
    capacidade_financeira = Column(Float, nullable=True)
    conhecimento = Column(Float, nullable=True)
    score_total = Column(Float, nullable=False)

    # Perfil resultante
    perfil = Column(SAEnum(InvestorRiskProfile), nullable=False)

    # Alocação sugerida em JSON: {"ot_bodiva": 0.35, "usd_equities": 0.15, ...}
    alocacao_sugerida = Column(JSON, nullable=True)

    # Respostas brutas ao questionário (JSON array: [{pergunta_id, resposta, score}])
    respostas = Column(JSON, nullable=True)

    # Data do questionário
    quiz_date = Column(Date, nullable=False, default=date.today)

    # URL do IPS gerado (PDF)
    ips_url = Column(String(500), nullable=True)

    # Estratégias recomendadas (JSON array de strings)
    recommended_strategies = Column(JSON, nullable=True)
