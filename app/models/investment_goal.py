"""
Objectivos financeiros do investidor.
Cada objectivo tem: montante alvo, prazo, plano de poupança mensal e tracking de progresso.

Exemplo:
  - "Comprar casa em 2029 — preciso de AOA 10M, poupando AOA 200K/mês"
  - "Educação dos filhos — AOA 5M em 2032"
  - "Fundo de emergência — AOA 2M em USD"
"""
import enum
from datetime import date
from sqlalchemy import Column, String, Integer, Float, Date, ForeignKey, Enum as SAEnum, JSON
from app.database import Base
from app.utils.base import BaseMixin


class GoalStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ON_TRACK = "ON_TRACK"
    BEHIND = "BEHIND"


class InvestmentGoal(Base, BaseMixin):
    """
    Objectivo financeiro do utilizador.
    """
    __tablename__ = "investment_goals"

    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    nome = Column(String(200), nullable=False, comment="Ex: 'Comprar casa', 'Educação', 'Reforma'")
    description = Column(String(500), nullable=True)

    # Montante alvo
    target_amount = Column(Float, nullable=False)
    currency = Column(String(3), default="AOA")

    # Prazo
    target_date = Column(Date, nullable=False)

    # Plano de poupança
    monthly_saving = Column(Float, nullable=True)
    current_amount = Column(Float, nullable=True, default=0.0)
    initial_amount = Column(Float, nullable=True, default=0.0)

    # Progresso
    progress_pct = Column(Float, nullable=True, default=0.0)
    status = Column(SAEnum(GoalStatus), default=GoalStatus.ACTIVE)

    # Meta-informação
    priority = Column(Integer, default=0, comment="0=baixa, 1=média, 2=alta")
    category = Column(String(50), nullable=True, comment="casa/educação/reforma/fundo_emergência/viagem/outro")
    notes = Column(JSON, nullable=True)
