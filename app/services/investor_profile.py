"""
investor_profile.py
===================
Investment profile engine — calculates risk profile and suggests allocation based on
a psychometric questionnaire following CFA Institute IPS (Investment Policy Statement) standards.

Two modes:
  - RAPIDO (6 questions, 3 dimensions) — for beginners
  - COMPLETO (10 questions, 5 dimensions) — intermediate/advanced, generates IPS

Scoring:
  Mode RAPIDO: simple average of 6 questions → profile
  Mode COMPLETO: weighted average (Tolerancia 35%, Horizonte 20%, Objectivos 20%,
                 Capacidade 15%, Conhecimento 10%) → profile

Strategic allocation includes international exposure for inflation hedge (critical for Angola).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from app.models.investor_profile import InvestorRiskProfile, QuizMode, InvestorProfile
from app.schemas.investment import QuizAnswer, InvestorProfileCreate


# ═══════════════════════════════════════════════════════════════════════════
# Question data (pure, no DB)
# ═══════════════════════════════════════════════════════════════════════════

QUESTIONS_RAPIDO = [
    {
        "id": 1,
        "dimensao": "Tolerancia ao Risco",
        "pergunta": "Se investisses 1.000.000 AOA e o teu portfolio caisse 10% num mes (para 900.000 AOA), o que farias?",
        "opcoes": [
            {"valor": 1, "label": "Vendia tudo para nao perder mais"},
            {"valor": 2, "label": "Vendia metade, muito preocupado"},
            {"valor": 3, "label": "Mantinha, acreditando que recupera"},
            {"valor": 4, "label": "Comprava mais, e oportunidade"},
            {"valor": 5, "label": "Comprava mais com alavancagem"},
        ],
    },
    {
        "id": 2,
        "dimensao": "Tolerancia ao Risco",
        "pergunta": "Preferes um investimento que...",
        "opcoes": [
            {"valor": 1, "label": "Garanta o capital mas renda abaixo da inflacao (ex: Deposito a Prazo)"},
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
            {"valor": 5, "label": "Aguardo 5+ anos, confiante na estrategia"},
        ],
    },
    {
        "id": 5,
        "dimensao": "Situacao Financeira",
        "pergunta": "Tens poupancas equivalentes a quantos meses de despesas?",
        "opcoes": [
            {"valor": 1, "label": "Menos de 1 mes"},
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
            {"valor": 1, "label": "Nenhum - e a minha primeira vez"},
            {"valor": 2, "label": "Basico - sei o que sao OT e accoes"},
            {"valor": 3, "label": "Intermedio - entendo YTM, Duration, diversificacao"},
            {"valor": 4, "label": "Avancado - uso VaR, Sharpe, analises tecnicas"},
            {"valor": 5, "label": "Profissional - trabalho na area financeira"},
        ],
    },
]

QUESTIONS_COMPLETO_ADICIONAIS = [
    {
        "id": 7,
        "dimensao": "Objectivos",
        "pergunta": "Qual e o teu principal objectivo com este investimento?",
        "opcoes": [
            {"valor": 1, "label": "Preservar capital, sem risco de perda"},
            {"valor": 2, "label": "Gerar rendimento regular (ex: complementar salario)"},
            {"valor": 3, "label": "Crescimento moderado acima da inflacao"},
            {"valor": 4, "label": "Acumular para um objectivo grande (casa, educacao)"},
            {"valor": 5, "label": "Crescimento maximo de longo prazo"},
        ],
    },
    {
        "id": 8,
        "dimensao": "Objectivos",
        "pergunta": "Que retorno anual esperas (em AOA) apos impostos e inflacao?",
        "opcoes": [
            {"valor": 1, "label": "0-2% (acima da inflacao / preservar)"},
            {"valor": 2, "label": "2-5% (acima da inflacao / rendimento)"},
            {"valor": 3, "label": "5-10% (crescimento moderado)"},
            {"valor": 4, "label": "10-15% (crescimento agressivo)"},
            {"valor": 5, "label": "15%+ (maximo retorno)"},
        ],
    },
    {
        "id": 9,
        "dimensao": "Contexto Angolano",
        "pergunta": "O kwanza desvalorizou 30% face ao USD no ultimo ano. O que fazes?",
        "opcoes": [
            {"valor": 1, "label": "Fico so em AOA, o governo vai estabilizar"},
            {"valor": 2, "label": "Passo 10% para USD ou EUR"},
            {"valor": 3, "label": "Passo 25% para USD ou EUR"},
            {"valor": 4, "label": "Passo 50% para accoes internacionais"},
            {"valor": 5, "label": "Passo 80% para fora de Angola"},
        ],
    },
    {
        "id": 10,
        "dimensao": "Contexto Angolano",
        "pergunta": "Qual a percentagem do teu patrimonio total que este investimento representa?",
        "opcoes": [
            {"valor": 1, "label": "Mais de 75% do meu patrimonio"},
            {"valor": 2, "label": "50-75% do meu patrimonio"},
            {"valor": 3, "label": "25-50% do meu patrimonio"},
            {"valor": 4, "label": "10-25% do meu patrimonio"},
            {"valor": 5, "label": "Menos de 10% do meu patrimonio"},
        ],
    },
]

# Alocation models per profile (weights sum to 1.0)
# International component is critical for Angola — protects against Kwanza devaluation
ALLOCATION_MODELS = {
    InvestorRiskProfile.CONSERVADOR: {
        "ot_bodiva": 0.50,       # BODIVA government bonds
        "bt": 0.20,               # Treasury bills
        "accao_nacional": 0.00,  # National equities
        "usd_equities": 0.10,     # S&P 500 (USD)
        "jse": 0.00,              # Johannesburg Stock Exchange
        "europe_bonds": 0.10,    # European sovereign bonds
        "gold": 0.00,            # Gold ETF
        "emerging": 0.00,        # Emerging markets equities
        "imobiliario": 0.10,     # Real estate
        "international_pct": 0.20,  # Total international exposure
    },
    InvestorRiskProfile.MODERADO: {
        "ot_bodiva": 0.35,
        "bt": 0.10,
        "accao_nacional": 0.05,
        "usd_equities": 0.15,
        "jse": 0.10,
        "europe_bonds": 0.10,
        "gold": 0.05,
        "emerging": 0.10,
        "imobiliario": 0.00,
        "international_pct": 0.35,
    },
    InvestorRiskProfile.DINAMICO: {
        "ot_bodiva": 0.20,
        "bt": 0.05,
        "accao_nacional": 0.10,
        "usd_equities": 0.25,
        "jse": 0.10,
        "europe_bonds": 0.05,
        "gold": 0.05,
        "emerging": 0.10,
        "imobiliario": 0.10,
        "international_pct": 0.50,
    },
    InvestorRiskProfile.AGRESSIVO: {
        "ot_bodiva": 0.10,
        "bt": 0.00,
        "accao_nacional": 0.15,
        "usd_equities": 0.30,
        "jse": 0.15,
        "europe_bonds": 0.05,
        "gold": 0.10,
        "emerging": 0.10,
        "imobiliario": 0.05,
        "international_pct": 0.65,
    },
}

STRATEGIES_BY_PROFILE = {
    InvestorRiskProfile.CONSERVADOR: ["buy_and_hold", "ladder"],
    InvestorRiskProfile.MODERADO: ["buy_and_hold", "ladder", "rebalanceamento_semestral"],
    InvestorRiskProfile.DINAMICO: ["dollar_cost_averaging", "barbell", "rebalanceamento_trimestral"],
    InvestorRiskProfile.AGRESSIVO: ["dollar_cost_averaging", "riding_the_curve", "tax_loss_harvesting", "rebalanceamento_mensal"],
}


# ═══════════════════════════════════════════════════════════════════════════
# Pure functions
# ═══════════════════════════════════════════════════════════════════════════

def get_quiz_questions(mode: QuizMode) -> Dict[str, Any]:
    """Return the questionnaire for the given mode."""
    questions = list(QUESTIONS_RAPIDO)
    if mode == QuizMode.COMPLETO:
        questions.extend(QUESTIONS_COMPLETO_ADICIONAIS)
    return {"mode": mode, "questions": questions, "total": len(questions)}


def calculate_profile(respostas: list[QuizAnswer]) -> Dict[str, Any]:
    """
    Core scoring algorithm.

    Mode is auto-detected from number of answers:
      <= 6 answers  → RAPIDO: simple average of 6 questions
      > 6 answers   → COMPLETO: weighted CFA-aligned average

    Returns { perfil, score_total, scores_by_dimension,
              alocacao, estrategias, profile_description }
    """
    scores = {r.pergunta_id: r.score for r in respostas}
    scores_by_dim = {}

    if len(respostas) <= 6:
        # RAPIDO: 3 dimensions, simple average
        tolerancia = (scores.get(1, 3) + scores.get(2, 3)) / 2
        horizonte = (scores.get(3, 3) + scores.get(4, 3)) / 2
        capacidade = (scores.get(5, 3) + scores.get(6, 3)) / 2
        scores_by_dim = {
            "tolerancia_risco": round(tolerancia, 2),
            "horizonte_temporal": round(horizonte, 2),
            "capacidade_financeira": round(capacidade, 2),
        }
        media = (tolerancia + horizonte + capacidade) / 3
    else:
        # COMPLETO: 5 dimensions with CFA weights
        tolerancia = (scores.get(1, 3) + scores.get(2, 3)) / 2
        horizonte = (scores.get(3, 3) + scores.get(4, 3)) / 2
        objectivos = (scores.get(7, 3) + scores.get(8, 3)) / 2
        capacidade = (scores.get(5, 3) + scores.get(10, 3)) / 2
        conhecimento = float(scores.get(6, 3))
        scores_by_dim = {
            "tolerancia_risco": round(tolerancia, 2),
            "horizonte_temporal": round(horizonte, 2),
            "objectivos_retorno": round(objectivos, 2),
            "capacidade_financeira": round(capacidade, 2),
            "conhecimento": round(conhecimento, 2),
        }
        media = (
            tolerancia * 0.35 + horizonte * 0.20
            + objectivos * 0.20 + capacidade * 0.15
            + conhecimento * 0.10
        )

    media = round(media, 2)

    # Map score to profile
    if media <= 2.0:
        perfil = InvestorRiskProfile.CONSERVADOR
        desc = ("Prioriza seguranca do capital. Prefere rendimento modesto "
                "mas previsivel. Aversao a perdas.")
    elif media <= 3.0:
        perfil = InvestorRiskProfile.MODERADO
        desc = ("Equilibrio entre seguranca e crescimento. Aceita alguma "
                "volatilidade para obter retorno acima da inflacao.")
    elif media <= 4.0:
        perfil = InvestorRiskProfile.DINAMICO
        desc = ("Foco em crescimento. Aceita volatilidade significativa. "
                "Horizonte de medio-longo prazo.")
    else:
        perfil = InvestorRiskProfile.AGRESSIVO
        desc = ("Maximo retorno, alta tolerancia ao risco e a volatilidade. "
                "Investidor experiente com horizonte longo.")

    return {
        "perfil": perfil,
        "profile_description": desc,
        "score_total": media,
        "scores_by_dimension": scores_by_dim,
        "alocacao": dict(ALLOCATION_MODELS[perfil]),
        "estrategias": list(STRATEGIES_BY_PROFILE[perfil]),
    }


# ═══════════════════════════════════════════════════════════════════════════
# IPS Generator
# ═══════════════════════════════════════════════════════════════════════════

def generate_ips_text(profile: InvestorProfile, user_name: str) -> str:
    """
    Generate an Investment Policy Statement (IPS) as plain text.

    Follows CFA Institute IPS structure:
      - Client profile
      - Investment objectives
      - Risk tolerance
      - Asset allocation
      - Rebalancing policy
      - Strategy

    In production this would generate a PDF via weasyprint/reportlab.
    This placeholder returns structured markdown text.
    """
    scores = profile.respostas or []
    alocacao = profile.alocacao_sugerida or {}
    estrategias = profile.recommended_strategies or []

    # Alocacao em percentagens legiveis
    alocacao_lines = []
    friendly_names = {
        "ot_bodiva": "Obrigacoes do Tesouro (BODIVA)",
        "bt": "Bilhetes do Tesouro",
        "accao_nacional": "Accoes BODIVA",
        "usd_equities": "Accoes USA (S&P 500)",
        "jse": "Accoes Africa do Sul (JSE)",
        "europe_bonds": "Obrigacoes Europeias",
        "gold": "Ouro (ETF)",
        "emerging": "Mercados Emergentes",
        "imobiliario": "Imobiliario",
    }
    for k, v in alocacao.items():
        if k == "international_pct":
            continue
        if isinstance(v, (int, float)) and v > 0:
            name = friendly_names.get(k, k)
            alocacao_lines.append(f"  - {name}: {v*100:.0f}%")

    ips = f"""
================================================================================
                           INVESTMENT POLICY STATEMENT (IPS)
================================================================================

DATA: {profile.created_at.strftime('%d/%m/%Y') if profile.created_at else date.today().strftime('%d/%m/%Y')}
CLIENTE: {user_name}
PERFIL: {profile.perfil.value}

--------------------------------------------------------------------------------
1. PERFIL DE RISCO
--------------------------------------------------------------------------------
Score Total: {profile.score_total}/5.0

Dimensoes:
"""
    if scores and isinstance(scores, list):
        # Extract scores from the JSON
        respostas_list = scores if isinstance(scores, list) else []
        for r in respostas_list:
            if isinstance(r, dict):
                ips += f"  - Pergunta {r.get('pergunta_id', '?')}: score {r.get('score', '?')}/5\n"

    ips += f"""
--------------------------------------------------------------------------------
2. OBJECTIVOS DE INVESTIMENTO
--------------------------------------------------------------------------------
O investidor {user_name} apresenta um perfil {profile.perfil.value},
caracterizado por:
  - Tolerancia ao risco: {'Baixa' if profile.perfil.value == 'CONSERVADOR' else 'Moderada' if profile.perfil.value == 'MODERADO' else 'Alta' if profile.perfil.value == 'DINAMICO' else 'Muito Alta'}
  - Horizonte temporal: determinado pelo questionario
  - Capacidade financeira: conforme declarado

O objectivo principal e a {'preservacao de capital' if profile.perfil.value in ('CONSERVADOR', 'MODERADO') else 'maximizacao do retorno real'} do patrimonio
investido, considerando o contexto de inflacao elevada em Angola.

--------------------------------------------------------------------------------
3. ALOCACAO ESTRATEGICA DE ACTIVOS
--------------------------------------------------------------------------------
{chr(10).join(alocacao_lines)}

Nota: A componente internacional ({alocacao.get('international_pct', 0)*100:.0f}%) e
essencial para proteger contra a desvalorizacao do kwanza e diversificar o risco
de credito soberano de Angola.

--------------------------------------------------------------------------------
4. ESTRATEGIA DE INVESTIMENTO
--------------------------------------------------------------------------------
"""
    for s in estrategias:
        ips += f"  - {s.replace('_', ' ').title()}\n"

    ips += """
--------------------------------------------------------------------------------
5. POLITICA DE REBALANCEAMENTO
--------------------------------------------------------------------------------
  - Rebalanceamento semestral
  - Triggers: desvio > 5% na alocacao alvo
  - Revisao anual da estrategia e do perfil de risco

--------------------------------------------------------------------------------
6. RESTRICOES
--------------------------------------------------------------------------------
  - Fiscal: IAC de 10% sobre rendimentos (Lei 14/25)
  - Cambial: exposicao ao USD/AOA monitorizada trimestralmente
  - Liquidez: posicoes iliquidas limitadas a 20% do portfolio

--------------------------------------------------------------------------------
7. MONITORIZACAO
--------------------------------------------------------------------------------
  - Dashboard Orbita: actualizacao diaria
  - Relatorio mensal de desempenho
  - Revisao anual do IPS

================================================================================
                          ORBITA - PULSARSETC
                          Plataforma de Inteligencia Financeira
                          Documento gerado em {datetime.now().strftime('%d/%m/%Y as %H:%M')}
================================================================================
    """

    return ips.strip()
