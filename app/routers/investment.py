"""
Router de investimento — cobre perfis, analytics, cenários, sinais, objectivos,
posições internacionais, taxas de câmbio, métricas de risco país e regras fiscais.

Estes são os endpoints que os motores de investimento (Sprints 4-5, 8-10) vão consumir.
"""
from datetime import date, datetime, timedelta
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_admin,
)
from app.models.user import User
from app.models.portfolio import Portfolio
from app.models.investment_goal import InvestmentGoal, GoalStatus
from app.models.investor_profile import InvestorProfile, InvestorRiskProfile, QuizMode
from app.models.scenario_definition import ScenarioDefinition
from app.models.investment_signal import InvestmentSignal, SignalType, SignalSeverity
from app.models.international_position import InternationalPosition
from app.models.currency_pair import CurrencyPair
from app.models.country_risk_metric import CountryRiskMetric
from app.models.market_comparison import MarketComparison
from app.models.tax_rule import TaxRule
from app.models.portfolio_analytics import PortfolioAnalytics
from app.schemas.investment import (
    QuizAnswer,
    InvestorProfileCreate,
    InvestorProfileRead,
    PortfolioAnalyticsRead,
    ScenarioDefinitionRead,
    InvestmentSignalRead,
    InvestmentGoalCreate,
    InvestmentGoalRead,
    InternationalPositionCreate,
    InternationalPositionRead,
    CurrencyPairRead,
    MarketComparisonRead,
    CountryRiskMetricRead,
    TaxRuleCreate,
    TaxRuleRead,
)
from app.services.investor_profile import (
    calculate_profile,
    get_quiz_questions as get_questions_service,
    generate_ips_text,
)

router = APIRouter(tags=["Investimento"])


# ===========================================================================
# 1. PERFIL DE INVESTIDOR
# ===========================================================================
investor_router = APIRouter(prefix="/investor-profile", tags=["Perfil Investidor"])


@investor_router.get("/questions", summary="Obter perguntas do questionario")
async def get_quiz_questions(mode: QuizMode = QuizMode.RAPIDO):
    """Devolve as perguntas do questionario psicometrico adaptado ao contexto angolano."""
    return get_questions_service(mode)


@investor_router.post("/submit", summary="Submeter respostas e obter perfil")
async def submit_quiz(
    data: InvestorProfileCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Processa o questionario e devolve o perfil de investidor."""
    result = calculate_profile(data.respostas)
    respostas_json = [r.model_dump() for r in data.respostas]
    mode = QuizMode.COMPLETO if len(data.respostas) > 6 else QuizMode.RAPIDO

    profile = InvestorProfile(
        user_id=current_user.id,
        mode=mode,
        perfil=result["perfil"],
        score_total=result["score_total"],
        tolerancia_risco=result["scores_by_dimension"].get("tolerancia_risco"),
        horizonte_temporal=result["scores_by_dimension"].get("horizonte_temporal"),
        objectivos_retorno=result["scores_by_dimension"].get("objectivos_retorno"),
        capacidade_financeira=result["scores_by_dimension"].get("capacidade_financeira"),
        conhecimento=result["scores_by_dimension"].get("conhecimento"),
        alocacao_sugerida=result["alocacao"],
        respostas=respostas_json,
        recommended_strategies=result["estrategias"],
        quiz_date=date.today(),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return {
        "profile_id": str(profile.id),
        "perfil": result["perfil"].value,
        "score_total": result["score_total"],
        "profile_description": result["profile_description"],
        "alocacao_sugerida": result["alocacao"],
        "estrategias": result["estrategias"],
        "message": "PERFIL_DEFINIDO",
    }


@investor_router.get("/my-profile", summary="Ver o meu perfil actual")
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Devolve o perfil de investidor mais recente do utilizador."""
    result = await db.execute(
        select(InvestorProfile)
        .where(InvestorProfile.user_id == current_user.id)
        .order_by(desc(InvestorProfile.created_at))
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado - responde ao questionario primeiro.")
    return InvestorProfileRead.model_validate(profile)


@investor_router.get("/ips", summary="Gerar IPS do meu perfil")
async def get_ips(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Gera o Investment Policy Statement (IPS) em formato texto."""
    result = await db.execute(
        select(InvestorProfile)
        .where(InvestorProfile.user_id == current_user.id)
        .order_by(desc(InvestorProfile.created_at))
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado - responde ao questionario primeiro.")

    ips_text = generate_ips_text(profile, current_user.name)
    return {
        "profile_id": str(profile.id),
        "ips": ips_text,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ===========================================================================
# 2. ESTRATEGIAS DE INVESTIMENTO
# ===========================================================================
strategies_router = APIRouter(prefix="/strategies", tags=["Estrategias"])

from app.services.investment_strategies import (
    suggest_strategies,
    compare_strategies,
    simulate_dca_vs_lump_sum,
    STRATEGY_DESCRIPTIONS,
)


@strategies_router.get("/descriptions", summary="Descricoes das estrategias disponiveis")
async def get_strategy_descriptions():
    """Devolve as descricoes de todas as estrategias de yield curve."""
    return STRATEGY_DESCRIPTIONS


@strategies_router.get("/suggest", summary="Sugerir estrategias para o perfil")
async def get_suggestions(
    profile: str = Query("MODERADO", description="Perfil: CONSERVADOR, MODERADO, DINAMICO, AGRESSIVO"),
    yield_curve_slope: Optional[float] = Query(None, description="Declive da curva (10yr-2yr) em %"),
    volatility_regime: Optional[str] = Query(None, description="low / normal / high"),
):
    """Sugere estrategias ordenadas por score para o perfil e condicoes de mercado."""
    suggestions = suggest_strategies(profile, yield_curve_slope, volatility_regime)
    return {
        "profile": profile,
        "yield_curve_slope": yield_curve_slope,
        "volatility_regime": volatility_regime,
        "suggestions": suggestions,
    }


@strategies_router.post("/compare", summary="Comparar estrategias de yield curve")
async def compare(
    portfolio_value: float = Query(..., description="Valor total do portfolio (AOA)"),
    average_yield: float = Query(0.195, description="Yield medio atual (decimal, ex: 0.195 = 19.5%)"),
    time_horizon_years: int = Query(5, description="Horizonte de investimento em anos"),
):
    """Compara a projecao financeira das estrategias Bullet, Barbell, Ladder e Riding the Curve."""
    return compare_strategies(portfolio_value, average_yield, time_horizon_years)


@strategies_router.post("/dca-vs-lump", summary="Simular DCA vs Lump Sum")
async def dca_vs_lump_simulation(
    total_amount: float = Query(..., description="Montante total a investir (AOA)"),
    time_horizon_years: int = Query(5, description="Horizonte em anos"),
    expected_return: float = Query(0.195, description="Retorno anual esperado (decimal)"),
    volatility: float = Query(0.0, description="Volatilidade anual (decimal, 0 = deterministico)"),
    num_installments: int = Query(12, description="Prestacoes DCA por ano"),
):
    """Compara DCA (investimento periodico) vs Lump Sum (investimento unico)."""
    return simulate_dca_vs_lump_sum(total_amount, time_horizon_years, expected_return, volatility, num_installments)


# ===========================================================================
# 3. OBJECTIVOS FINANCEIROS
# ===========================================================================
goals_router = APIRouter(prefix="/goals", tags=["Objectivos"])


@goals_router.get("/", summary="Listar objectivos")
async def list_goals(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Optional[GoalStatus] = None,
):
    query = select(InvestmentGoal).where(InvestmentGoal.user_id == current_user.id)
    if status_filter:
        query = query.where(InvestmentGoal.status == status_filter)
    query = query.order_by(desc(InvestmentGoal.priority), InvestmentGoal.target_date)
    result = await db.execute(query)
    goals = result.scalars().all()
    return [InvestmentGoalRead.model_validate(g) for g in goals]


@goals_router.post("/", summary="Criar objectivo", status_code=201)
async def create_goal(
    data: InvestmentGoalCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    goal = InvestmentGoal(
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return InvestmentGoalRead.model_validate(goal)


@goals_router.delete("/{goal_id}", summary="Eliminar objectivo")
async def delete_goal(
    goal_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(InvestmentGoal).where(
            InvestmentGoal.id == goal_id,
            InvestmentGoal.user_id == current_user.id,
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Objectivo não encontrado")
    await db.delete(goal)
    await db.commit()
    return {"status": "eliminado"}


# ===========================================================================
# 3. CENÁRIOS PREDEFINIDOS
# ===========================================================================
scenarios_router = APIRouter(prefix="/scenarios", tags=["Cenários"])


@scenarios_router.get("/prebuilt", summary="Listar cenários predefinidos")
async def list_prebuilt_scenarios(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(ScenarioDefinition).where(ScenarioDefinition.is_active == True)
        .order_by(ScenarioDefinition.severity)
    )
    scenarios = result.scalars().all()
    if not scenarios:
        # Seed data para quando a BD estiver vazia
        return [
            {"name": "Estabilidade", "severity": 0, "params": {"bna_rate": 0.17, "inflation": 0.12, "usd_aoa": 650.0, "oil_price": 75.0}},
            {"name": "Choque Moderado", "severity": 2, "params": {"bna_rate": 0.19, "inflation": 0.15, "usd_aoa": 715.0, "oil_price": 63.75}},
            {"name": "Choque Severo", "severity": 3, "params": {"bna_rate": 0.22, "inflation": 0.20, "usd_aoa": 812.5, "oil_price": 52.5}},
            {"name": "Crise Cambial", "severity": 4, "params": {"bna_rate": 0.27, "inflation": 0.27, "usd_aoa": 975.0, "oil_price": 37.5}},
        ]
    return [ScenarioDefinitionRead.model_validate(s) for s in scenarios]


# ===========================================================================
# 4. SINAIS DE INVESTIMENTO
# ===========================================================================
signals_router = APIRouter(prefix="/signals", tags=["Sinais"])


@signals_router.get("/", summary="Listar sinais do portfolio")
async def list_signals(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    portfolio_id: Optional[str] = None,
    signal_type: Optional[SignalType] = None,
    severity: Optional[SignalSeverity] = None,
    active_only: bool = True,
):
    query = select(InvestmentSignal).where(InvestmentSignal.user_id == current_user.id)
    if portfolio_id:
        query = query.where(InvestmentSignal.portfolio_id == portfolio_id)
    if signal_type:
        query = query.where(InvestmentSignal.signal_type == signal_type)
    if severity:
        query = query.where(InvestmentSignal.severity == severity)
    if active_only:
        query = query.where(InvestmentSignal.is_dismissed == False)
    query = query.order_by(desc(InvestmentSignal.created_at)).limit(50)
    result = await db.execute(query)
    signals = result.scalars().all()
    return [InvestmentSignalRead.model_validate(s) for s in signals]


# ===========================================================================
# 5. POSIÇÕES INTERNACIONAIS
# ===========================================================================
international_router = APIRouter(prefix="/international", tags=["Internacional"])


@international_router.get("/positions", summary="Listar posições internacionais")
async def list_international_positions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(InternationalPosition).where(InternationalPosition.user_id == current_user.id)
    )
    positions = result.scalars().all()
    return [InternationalPositionRead.model_validate(p) for p in positions]


@international_router.post("/positions", summary="Adicionar posição internacional", status_code=201)
async def add_international_position(
    data: InternationalPositionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    pos = InternationalPosition(user_id=current_user.id, **data.model_dump())
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    return InternationalPositionRead.model_validate(pos)


@international_router.get("/currency-pairs", summary="Taxas de câmbio actuais")
async def get_currency_pairs(
    db: Annotated[AsyncSession, Depends(get_db)],
    pair: Optional[str] = None,
):
    query = select(CurrencyPair).order_by(desc(CurrencyPair.snapshot_date))
    if pair:
        query = query.where(CurrencyPair.pair == pair)
    result = await db.execute(query.limit(10))
    pairs = result.scalars().all()
    return [CurrencyPairRead.model_validate(p) for p in pairs]


@international_router.get("/country-risk", summary="Métricas de risco país")
async def get_country_risk(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(CountryRiskMetric).where(CountryRiskMetric.country_code == "AO")
        .order_by(desc(CountryRiskMetric.metric_date)).limit(1)
    )
    metric = result.scalar_one_or_none()
    if not metric:
        # Dados indicativos para desenvolvimento
        return {
            "country": "Angola",
            "metric_date": date.today().isoformat(),
            "crp": 8.25,
            "rating": "B- / Caa1",
            "cds_spread": 750,
            "bna_rate": 0.17,
            "inflation_rate": 0.1242,
            "usd_aoa": 650.0,
        }
    return CountryRiskMetricRead.model_validate(metric)


# ===========================================================================
# 6. REGRAS FISCAIS
# ===========================================================================
tax_router = APIRouter(prefix="/tax-rules", tags=["Regras Fiscais"])


@tax_router.get("/", summary="Listar regras fiscais activas")
async def list_tax_rules(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(TaxRule).where(TaxRule.is_active == True).order_by(TaxRule.priority)
    )
    rules = result.scalars().all()
    return [TaxRuleRead.model_validate(r) for r in rules]


@tax_router.post("/", summary="Criar regra fiscal (admin)")
async def create_tax_rule(
    data: TaxRuleCreate,
    current_user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    rule = TaxRule(**data.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return TaxRuleRead.model_validate(rule)


@tax_router.post("/resolve", summary="Resolver taxa IAC para instrumento+data")
async def resolve_tax_rate(
    db: Annotated[AsyncSession, Depends(get_db)],
    instrument_class: str = Query(...),
    payment_date: date = Query(...),
):
    """
    Resolve a taxa de IAC aplicável para um instrumento e data de pagamento.
    Exemplo: BOND_GOV + 2026-06-20 → 10% (Lei 14/25)
    """
    result = await db.execute(
        select(TaxRule).where(
            TaxRule.instrument_class == instrument_class,
            TaxRule.is_active == True,
            TaxRule.valid_from <= payment_date,
            (TaxRule.valid_to >= payment_date) | (TaxRule.valid_to.is_(None)),
        ).order_by(desc(TaxRule.priority)).limit(1)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        # Fallback: IAC 10% (regime actual desde Lei 14/25)
        return {
            "instrument_class": instrument_class,
            "payment_date": payment_date.isoformat(),
            "iac_rate": 0.10,
            "rule_name": "IAC 10% (default)",
            "valid_from": "2026-01-01",
        }
    return {
        "instrument_class": rule.instrument_class,
        "payment_date": payment_date.isoformat(),
        "iac_rate": rule.coupon_tax_rate,
        "rule_name": rule.name,
        "valid_from": rule.valid_from.isoformat(),
        "valid_to": rule.valid_to.isoformat() if rule.valid_to else None,
    }
