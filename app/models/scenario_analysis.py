"""
Análise de cenários — stress tests paramétricos e Monte Carlo simplificado.
Unifica StressTestResult + MonteCarloResult num único modelo genérico.

Para o MVP usamos simulação paramétrica com 1K paths.
GARCH(1,1) + cópula Gaussiana fica para a v2.
"""
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum as SAEnum, JSON
from app.database import Base
from app.utils.base import BaseMixin


class ScenarioType(str, enum.Enum):
    PARAMETRIC = "PARAMETRIC"            # Stress test paramétrico
    MONTE_CARLO = "MONTE_CARLO"          # Simulação Monte Carlo simplificada
    SENSITIVITY = "SENSITIVITY"          # Matriz de sensibilidade
    CUSTOM = "CUSTOM"                    # Cenário definido pelo utilizador


class ScenarioAnalysis(Base, BaseMixin):
    """
    Resultado de uma análise de cenário aplicada a um portfolio.
    """
    __tablename__ = "scenario_analyses"

    portfolio_id = Column(
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_type = Column(SAEnum(ScenarioType), nullable=False)
    scenario_name = Column(String(100), nullable=True)

    # Parâmetros do cenário (JSON)
    params = Column(JSON, nullable=True, comment="Ex: {'bna_rate': 0.22, 'inflation': 0.20}")

    # Resultados
    impact_value = Column(Float, nullable=True, comment="Impacto em AOA no portfolio")
    impact_pct = Column(Float, nullable=True, comment="Impacto percentual")
    probability = Column(Float, nullable=True, comment="Probabilidade estimada do cenário")

    # Distribuição completa (para Monte Carlo)
    distribution = Column(JSON, nullable=True, comment="Percentis 5/25/50/75/95 + todos os paths")

    # Metadados
    n_simulations = Column(Integer, nullable=True, comment="Nº de caminhos (Monte Carlo)")
    confidence_level = Column(Float, nullable=True, default=0.95)
    snapshot_date = Column(DateTime, nullable=False, default=datetime.utcnow)
