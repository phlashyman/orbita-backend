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

router = APIRouter(tags=["Investimento"])


# ===========================================================================
# 1. PERFIL DE INVESTIDOR
# ===========================================================================
investor_router = APIRouter(prefix="/investor-profile", tags=["Perfil Investidor"])


@investor_router.get("/questions", summary="Obter perguntas do questionário")
async def get_quiz_questions(mode: QuizMode = QuizMode.RAPIDO):
    """
    Devolve as perguntas do questionário psicométrico adaptado ao contexto angolano.
    - RAPIDO: 6 perguntas (3 dimensões) — para beginners
    - COMPLETO: 10 perguntas (5 dimensões) — intermédios/avançados
    """
    # Perguntas base (modo rápido)
    questions = [
        {
            "id": 1,
            "dimensao": "Tolerância ao Risco",
            "pergunta": "Se investisses 1.000.000 AOA e o teu portfolio caísse 10% num mês (para 900.000 AOA), o que farias?",
            "opcoes": [
                {"valor": 1, "label": "Vendia tudo para não perder mais"},
                {"valor": 2, "label": "Vendia metade, muito preocupado"},
                {"valor": 3, "label": "Mantinha, acreditando que recupera"},
                {"valor": 4, "label": "Comprava mais, é oportunidade"},
                {"valor": 5, "label": "Comprava mais com alavancagem"},
            ],
        },
        {
            "id": 2,
            "dimensao": "Tolerância ao Risco",
            "pergunta": "Preferes um investimento que...",
            "opcoes": [
                {"valor": 1, "label": "Garanta o capital mas renda abaixo da inflação (ex: Depósito a Prazo)"},
                {"valor": 2, "label": "Tenha 90% chance de ganhar 5% e 10% de perder 2%"},
                {"valor": 3, "label": "Tenha 70% chance de ganhar 10% e 30% de perder 5%"},
                {"valor": 4, "label": "Tenha 50% chance de ganhar 25% e 50% de perder 10%"},
                {"valor": 5, "label": "Tenha 30% chance de ganhar 50% e 70% de perder 20%"},
            ],
        },
        {
            "id": 3,
            "dimensao": "Horizonte Temporal",
            "pergunta": "Quando precisas do dinheiro que vais investir?",
            "opcoes": [
                {"valor": 1, "label": "Menos de 1 ano"},
                {"valor": 2, "label": "1-3 anos"},
                {"valor": 3, "label": "3-5 anos"},
                {"valor": 4, "label": "5-10 anos"},
                {"valor": 5, "label": "Mais de 10 anos"},
            ],
        },
        {
            "id": 4,
            "dimensao": "Horizonte Temporal",
            "pergunta": "Se o teu investimento perdesse valor nos primeiros 2 anos, esperarias quanto tempo para recuperar?",
            "opcoes": [
                {"valor": 1, "label": "Vendo ao fim de 6 meses"},
                {"valor": 2, "label": "Vendo ao fim de 1 ano"},
                {"valor": 3, "label": "Aguardo 2-3 anos"},
                {"valor": 4, "label": "Aguardo 4-5 anos"},
                {"valor": 5, "label": "Aguardo 5+ anos, confiante na estratégia"},
            ],
        },
        {
            "id": 5,
            "dimensao": "Situação Financeira",
            "pergunta": "Tens poupanças equivalentes a quantos meses de despesas?",
            "opcoes": [
                {"valor": 1, "label": "Menos de 1 mês"},
                {"valor": 2, "label": "1-3 meses"},
                {"valor": 3, "label": "3-6 meses"},
                {"valor": 4, "label": "6-12 meses"},
                {"valor": 5, "label": "Mais de 12 meses"},
            ],
        },
        {
            "id": 6,
            "dimensao": "Conhecimento",
            "pergunta": "Como descreves o teu conhecimento sobre investimentos?",
            "opcoes": [
                {"valor": 1, "label": "Nenhum — é a minha primeira vez"},
                {"valor": 2, "label": "Básico — sei o que são OT e acções"},
                {"valor": 3, "label": "Intermédio — entendo YTM, Duration, diversificação"},
                {"valor": 4, "label": "Avançado — uso VaR, Sharpe, análises técnicas"},
                {"valor": 5, "label": "Profissional — trabalho na área financeira"},
            ],
        },
    ]

    # Perguntas adicionais para o modo completo
    if mode == QuizMode.COMPLETO:
        questions.extend([
            {
                "id": 7,
                "dimensao": "Objectivos",
                "pergunta": "Qual é o teu principal objectivo com este investimento?",
                "opcoes": [
                    {"valor": 1, "label": "Preservar capital, sem risco de perda"},
                    {"valor": 2, "label": "Gerar rendimento regular (ex: complementar salário)"},
                    {"valor": 3, "label": "Crescimento moderado acima da inflação"},
                    {"valor": 4, "label": "Acumular para um objectivo grande (casa, educação)"},
                    {"valor": 5, "label": "Crescimento máximo de longo prazo"},
                ],
            },
            {
                "id": 8,
                "dimensao": "Objectivos",
                "pergunta": "Que retorno anual esperas (em AOA) após impostos e inflação?",
                "opcoes": [
                    {"valor": 1, "label": "0-2% (acima da inflação / preservar)"},
                    {"valor": 2, "label": "2-5% (acima da inflação / rendimento)"},
                    {"valor": 3, "label": "5-10% (crescimento moderado)"},
                    {"valor": 4, "label": "10-15% (crescimento agressivo)"},
                    {"valor": 5, "label": "15%+ (máximo retorno)"},
                ],
            },
            {
                "id": 9,
                "dimensao": "Contexto Angolano",
                "pergunta": "O kwanza desvalorizou 30% face ao USD no último ano. O que fazes?",
                "opcoes": [
                    {"valor": 1, "label": "Fico só em AOA, o governo vai estabilizar"},
                    {"valor": 2, "label": "Passo 10% para USD ou EUR"},
                    {"valor": 3, "label": "Passo 25% para USD ou EUR"},
                    {"valor": 4, "label": "Passo 50% para acções internacionais"},
                    {"valor": 5, "label": "Passo 80% para fora de Angola"},
                ],
            },
            {
                "id": 10,
                "dimensao": "Contexto Angolano",
                "pergunta": "Qual a percentagem do teu património total que este investimento representa?",
                "opcoes": [
                    {"valor": 1, "label": "Mais de 75% do meu património"},
                    {"valor": 2, "label": "50-75% do meu património"},
                    {"valor": 3, "label": "25-50% do meu património"},
                    {"valor": 4, "label": "10-25% do meu património"},
                    {"valor": 5, "label": "Menos de 10% do meu património"},
                ],
            },
        ])

    return {"mode": mode, "questions": questions, "total": len(questions)}


def _calculate_profile(respostas: list[QuizAnswer]) -> dict:
    """Calcula perfil e alocação a partir das respostas."""
    scores = {r.pergunta_id: r.score for r in respostas}

    # Agrupar por dimensão
    if len(respostas) <= 6:
        # Modo rápido: 3 dimensões
        tolerancia = (scores.get(1, 3) + scores.get(2, 3)) / 2
        horizonte = (scores.get(3, 3) + scores.get(4, 3)) / 2
        capacidade = (scores.get(5, 3) + scores.get(6, 3)) / 2
        media = (tolerancia + horizonte + capacidade) / 3
    else:
        # Modo completo: 5 dimensões com pesos CFA
        tolerancia = (scores.get(1, 3) + scores.get(2, 3)) / 2
        horizonte = (scores.get(3, 3) + scores.get(4, 3)) / 2
        objectivos = (scores.get(7, 3) + scores.get(8, 3)) / 2
        capacidade = (scores.get(5, 3) + scores.get(10, 3)) / 2
        conhecimento = float(scores.get(6, 3))
        media = (tolerancia * 0.35 + horizonte * 0.20 + objectivos * 0.20 + capacidade * 0.15 + conhecimento * 0.10)

    # Mapear score para perfil
    if media <= 2.0:
        perfil = InvestorRiskProfile.CONSERVADOR
        alocacao = {
            "ot_bodiva": 0.50, "bt": 0.20, "accao_nacional": 0.00,
            "usd_equities": 0.10, "jse": 0.00, "europe_bonds": 0.10,
            "gold": 0.00, "emerging": 0.00, "imobiliario": 0.10,
        }
    elif media <= 3.0:
        perfil = InvestorRiskProfile.MODERADO
        alocacao = {
            "ot_bodiva": 0.35, "bt": 0.10, "accao_nacional": 0.05,
            "usd_equities": 0.15, "jse": 0.10, "europe_bonds": 0.10,
            "gold": 0.05, "emerging": 0.10, "imobiliario": 0.05,
        }
    elif media <= 4.0:
        perfil = InvestorRiskProfile.DINAMICO
        alocacao = {
            "ot_bodiva": 0.20, "bt": 0.05, "accao_nacional": 0.10,
            "usd_equities": 0.25, "jse": 0.10, "europe_bonds": 0.05,
            "gold": 0.05, "emerging": 0.10, "imobiliario": 0.05,
        }
    else:
        perfil = InvestorRiskProfile.AGRESSIVO
        alocacao = {
            "ot_bodiva": 0.10, "bt": 0.00, "accao_nacional": 0.15,
            "usd_equities": 0.30, "jse": 0.15, "europe_bonds": 0.05,
            "gold": 0.10, "emerging": 0.10, "imobiliario": 0.00,
        }

    return {
        "perfil": perfil,
        "score_total": round(media, 2),
        "alocacao": alocacao,
        "estrategias": ["buy_and_hold", "rebalanceamento_semestral"],
    }


@investor_router.post("/submit", summary="Submeter respostas e obter perfil")
async def submit_quiz(
    data: InvestorProfileCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Processa o questionário e devolve o perfil de investidor."""
    result = _calculate_profile(data.respostas)
    respostas_json = [r.model_dump() for r in data.respostas]

    profile = InvestorProfile(
        user_id=current_user.id,
        mode=data.mode,
        perfil=result["perfil"],
        score_total=result["score_total"],
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
        raise HTTPException(status_code=404, detail="Perfil não encontrado — responde ao questionário primeiro.")
    return InvestorProfileRead.model_validate(profile)


# ===========================================================================
# 2. OBJECTIVOS FINANCEIROS
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
