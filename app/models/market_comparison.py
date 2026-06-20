"""
Comparação histórica de retornos entre mercados.
Calcula: "Se tivesse investido 1M AOA em OT vs S&P 500 vs JSE vs Ouro há N anos..."

Resultado armazenado para cache e consulta rápida.
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Date, DateTime, JSON
from app.database import Base
from app.utils.base import BaseMixin


class MarketComparison(Base, BaseMixin):
    """
    Resultado de uma comparação entre mercados para um período específico.
    """
    __tablename__ = "market_comparisons"

    # Período da comparação
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    initial_amount = Column(Float, nullable=False, default=1000000.0)
    currency = Column(String(3), default="AOA")

    # Resultados por mercado (JSON)
    results = Column(
        JSON, nullable=False,
        comment="""{
            'ot_bodiva': {'final_value': 1979316, 'annualized_return': 0.195, 'real_return': -0.063},
            'sp500_usd': {'final_value': 2753000, 'annualized_return': 0.224, 'real_return': -0.034},
            'jse_zar':   {'final_value': 1877000, 'annualized_return': 0.134, 'real_return': -0.123},
            'gold_usd':  {'final_value': 2197000, 'annualized_return': 0.171, 'real_return': -0.087},
        }"""
    )

    # Metadados
    years = Column(Float, nullable=True, comment="Duração em anos")
    inflation_rate = Column(Float, nullable=True, comment="Taxa de inflação no período")
    usd_aoa_start = Column(Float, nullable=True)
    usd_aoa_end = Column(Float, nullable=True)
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
