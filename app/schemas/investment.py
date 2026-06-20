"""
Pydantic schemas para os novos modelos de investimento.
Agrupados por domínio para facilitar manutenção.
"""
import uuid
from datetime import date, datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict

from app.models.investor_profile import InvestorRiskProfile, QuizMode
from app.models.investment_signal import SignalType, SignalSeverity
from app.models.investment_goal import GoalStatus
from app.models.scenario_analysis import ScenarioType


# ===========================================================================
# Investor Profile
# ===========================================================================
class QuizAnswer(BaseModel):
    pergunta_id: int
    resposta: int  # 1-5
    score: float


class InvestorProfileCreate(BaseModel):
    mode: QuizMode = QuizMode.RAPIDO
    respostas: list[QuizAnswer]


class InvestorProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    perfil: InvestorRiskProfile
    score_total: float
    tolerancia_risco: Optional[float] = None
    horizonte_temporal: Optional[float] = None
    objectivos_retorno: Optional[float] = None
    capacidade_financeira: Optional[float] = None
    conhecimento: Optional[float] = None
    alocacao_sugerida: Optional[dict] = None
    ips_url: Optional[str] = None
    recommended_strategies: Optional[list] = None
    quiz_date: date


# ===========================================================================
# Portfolio Analytics
# ===========================================================================
class PortfolioAnalyticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID

    var_95_1m: Optional[float] = None
    var_95_1m_pct: Optional[float] = None
    cvar_95_1m: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    information_ratio: Optional[float] = None
    macaulay_duration: Optional[float] = None
    modified_duration: Optional[float] = None
    convexity: Optional[float] = None
    hhi: Optional[float] = None
    gini: Optional[float] = None
    effective_n: Optional[float] = None
    liquidity_score: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    snapshot_date: datetime


# ===========================================================================
# Scenario & Risk
# ===========================================================================
class ScenarioAnalysisCreate(BaseModel):
    scenario_type: ScenarioType
    scenario_name: Optional[str] = None
    params: Optional[dict] = None
    confidence_level: float = 0.95
    n_simulations: Optional[int] = None


class ScenarioAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    scenario_type: ScenarioType
    scenario_name: Optional[str] = None
    impact_value: Optional[float] = None
    impact_pct: Optional[float] = None
    probability: Optional[float] = None
    snapshot_date: datetime


class ScenarioDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    params_schema: dict
    is_active: bool
    severity: int


# ===========================================================================
# Investment Signal
# ===========================================================================
class InvestmentSignalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    signal_type: SignalType
    severity: SignalSeverity
    title: str
    description: Optional[str] = None
    source_ticker: Optional[str] = None
    target_ticker: Optional[str] = None
    estimated_benefit: Optional[float] = None
    justification: Optional[str] = None
    is_actionable: bool
    is_dismissed: bool
    created_at: datetime


# ===========================================================================
# Investment Goal
# ===========================================================================
class InvestmentGoalCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    target_amount: float
    currency: str = "AOA"
    target_date: date
    monthly_saving: Optional[float] = None
    current_amount: float = 0.0
    priority: int = 0
    category: Optional[str] = None


class InvestmentGoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    target_amount: float
    currency: str
    target_date: date
    monthly_saving: Optional[float] = None
    current_amount: Optional[float] = None
    progress_pct: Optional[float] = None
    status: GoalStatus
    priority: int
    category: Optional[str] = None


# ===========================================================================
# International Positions
# ===========================================================================
class InternationalPositionCreate(BaseModel):
    ticker: str
    exchange: Optional[str] = None
    name: Optional[str] = None
    currency: str = "USD"
    market: Optional[str] = None
    quantity: float
    purchase_price: Optional[float] = None
    purchase_date: Optional[date] = None


class InternationalPositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticker: str
    exchange: Optional[str] = None
    name: Optional[str] = None
    currency: str
    quantity: float
    current_value_aoa: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None


# ===========================================================================
# Currency Pair
# ===========================================================================
class CurrencyPairRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pair: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: float
    variation_pct: Optional[float] = None
    source: str
    snapshot_date: datetime


# ===========================================================================
# Market Comparison
# ===========================================================================
class MarketComparisonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date
    end_date: date
    initial_amount: float
    currency: str
    results: dict
    years: Optional[float] = None


# ===========================================================================
# Country Risk Metrics
# ===========================================================================
class CountryRiskMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    country: str
    metric_date: date
    crp: Optional[float] = None
    rating: Optional[str] = None
    cds_spread: Optional[int] = None
    bna_rate: Optional[float] = None
    inflation_rate: Optional[float] = None
    usd_aoa: Optional[float] = None


# ===========================================================================
# Tax Rule
# ===========================================================================
class TaxRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    instrument_class: str
    coupon_tax_rate: float
    capgain_tax_rate: Optional[float] = None
    valid_from: date
    valid_to: Optional[date] = None


class TaxRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    instrument_class: str
    coupon_tax_rate: float
    capgain_tax_rate: Optional[float] = None
    valid_from: date
    valid_to: Optional[date] = None
    is_active: bool
