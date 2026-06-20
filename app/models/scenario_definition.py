"""
Cenários macro predefinidos — Angola-specific.
Usados pelo risk_manager e scenario_engine para stress tests.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Enum as SAEnum, JSON
from app.database import Base
from app.utils.base import BaseMixin


class ScenarioCategory(str, enum.Enum):
    MACRO = "MACRO"                    # Cenário macroeconómico
    CREDIT = "CREDIT"                  # Risco de crédito
    CURRENCY = "CURRENCY"              # Risco cambial
    COMMODITY = "COMMODITY"            # Risco de commodity
    POLITICAL = "POLITICAL"            # Risco político
    CUSTOM = "CUSTOM"                  # Definido pelo utilizador


class ScenarioDefinition(Base, BaseMixin):
    """
    Definição de um cenário macroeconómico para stress testing.

    Cenários predefinidos (seed data):
      - 🟢 Estabilidade:  BNA=17%, Inflação=12%, USD/AOA=650, Petróleo=$75
      - 🟡 Choque Moderado: +2pp BNA, +3pp inflação, +10% USD/AOA, -15% petróleo
      - 🔴 Choque Severo:  +5pp BNA, +8pp inflação, +25% USD/AOA, -30% petróleo
      - ⚫ Crise Cambial:  +10pp BNA, +15pp inflação, +50% USD/AOA, -50% petróleo
    """
    __tablename__ = "scenario_definitions"

    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    category = Column(SAEnum(ScenarioCategory), nullable=False)

    # Parâmetros do cenário (todos opcionais, o que não for usado fica None)
    params_schema = Column(
        JSON, nullable=False,
        comment="""Estrutura: {
            'bna_rate': 0.17,         # Taxa BNA (decimal)
            'inflation': 0.12,        # Inflação (decimal)
            'usd_aoa': 650.0,         # Taxa de câmbio USD/AOA
            'eur_aoa': 710.0,         # Taxa EUR/AOA
            'oil_price': 75.0,        # Preço petróleo (USD)
            'gdp_growth': 0.03,       # Crescimento PIB (decimal)
            'cds_spread': 500,        # CDS Angola (bps)
        }"""
    )

    is_active = Column(Boolean, default=True)
    created_by = Column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Severidade (para ordenação nos slugs)
    severity = Column(Integer, default=0, comment="0=baseline, 1=leve, 2=moderado, 3=severo, 4=critico")
