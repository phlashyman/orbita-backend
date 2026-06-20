"""
ai_assistant.py
===============
AI Investment Assistant — chat contextual, geracao de relatorios, alertas inteligentes.

Controlos de custo (portados do Claude AI's ai_agent.py):
  - Tiering: Haiku para auto-insights ($0.0003/1K tokens), Sonnet para analises profundas
  - Daily spending cap (default $5/dia)
  - Audit logging em ai_assistant_logs
  - MD5 cache para insights repetidos
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_assistant_log import AIAssistantLog, AIFeature
from app.models.investor_profile import InvestorProfile

# ═══════════════════════════════════════════════════════════════════════════
# Cost control configuration
# ═══════════════════════════════════════════════════════════════════════════

DAILY_CAP_USD = float(os.environ.get("AI_DAILY_CAP_USD", "5.0"))

MODEL_TIERS = {
    "auto_insight": {
        "model": "claude-haiku-4-5",
        "cost_per_1k_input": 0.0003,
        "cost_per_1k_output": 0.0015,
        "description": "Para auto-insights, alertas e cache de metricas repetidas.",
    },
    "analysis": {
        "model": "claude-sonnet-4-6",
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "description": "Para analises profundas, chat e geracao de relatorios.",
    },
    "news": {
        "model": "claude-sonnet-4-6",
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "description": "Para geracao de noticias com web search (ai_news).",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Cost control helpers
# ═══════════════════════════════════════════════════════════════════════════

async def check_daily_cap(
    db: AsyncSession,
    feature: AIFeature,
) -> Dict[str, Any]:
    """
    Check if the daily spending cap has been reached.
    Returns {"allowed": bool, "spent_today": float, "remaining": float, "cap": float}.
    """
    today = datetime.utcnow().date()
    start_of_day = datetime(today.year, today.month, today.day)

    result = await db.execute(
        select(func.coalesce(func.sum(AIAssistantLog.cost_usd), 0))
        .where(
            AIAssistantLog.feature == feature,
            AIAssistantLog.created_at >= start_of_day,
            AIAssistantLog.was_capped == False,
        )
    )
    spent_today = float(result.scalar() or 0)
    remaining = max(0, DAILY_CAP_USD - spent_today)

    return {
        "allowed": remaining > 0 or DAILY_CAP_USD <= 0,
        "spent_today": round(spent_today, 4),
        "remaining": round(remaining, 4),
        "cap": DAILY_CAP_USD,
    }


def estimate_cost(
    tokens_input: int,
    tokens_output: int,
    tier: str = "analysis",
) -> float:
    """Estimate API cost based on model tier and token count."""
    config = MODEL_TIERS.get(tier, MODEL_TIERS["analysis"])
    cost_input = (tokens_input / 1000) * config["cost_per_1k_input"]
    cost_output = (tokens_output / 1000) * config["cost_per_1k_output"]
    return round(cost_input + cost_output, 6)


def md5_cache_key(data: Dict[str, Any]) -> str:
    """Create MD5 hash for caching repeated insights."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# System prompts (PT-PT)
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT_ANALYSIS = """Eres um analista financeiro especializado no mercado angolano (BODIVA).
O utilizador e um investidor Angolano que usa a plataforma Orbita.

Regras:
1. Responde SEMPRE em PT-PT (Portugues de Portugal).
2. Usa terminologia do mercado angolano (OT, IAC, BNA, BODIVA, kwanza).
3. Quando falares de valores, usa o formato angolano (ex: 1.000.000 AOA).
4. NAO recomendas compra ou venda de instrumentos especificos — apenas apresentas analise.
5. Se nao souberes um dado, diz que nao sabes em vez de inventar.
6. Quando apropriado, explica conceitos financeiros de forma simples.
7. O contexto atual do mercado angolano inclui:
   - IAC de 10% (Lei 14/25, OGE 2026)
   - BNA rate aproximadamente 17%
   - Inflacao anual aproximadamente 12-13%
   - USD/AOA aproximadamente 650"""

SYSTEM_PROMPT_REPORT = """Eres um analista financeiro a gerar um relatorio semanal de investimento
para um investidor angolano. O relatorio deve incluir:

1. Resumo do portfolio (valor total, yield, performance semanal)
2. Analise do mercado BODIVA (destaques da semana)
3. Mercados internacionais contexto (S&P 500, JSE, USD/AOA)
4. Alertas e recomendacoes (baseados em dados, nao opiniao)
5. Proximos eventos (copoes, vencimentos)

Formato: PT-PT, tom profissional mas acessivel, sem jargao desnecessario."""


# ═══════════════════════════════════════════════════════════════════════════
# Insight generators (simulated — real AI calls come from ai_news.py)
# ═══════════════════════════════════════════════════════════════════════════

def generate_portfolio_insight(
    portfolio_value: float,
    total_invested: float,
    weighted_real_yield: Optional[float],
    n_holdings: int,
    top_ticker: Optional[str] = None,
) -> str:
    """Generate a short portfolio insight (no API call — rule-based)."""
    gain_loss = portfolio_value - total_invested
    gain_loss_pct = ((portfolio_value / total_invested) - 1) * 100 if total_invested > 0 else 0

    lines = [f"Gestao de Carteira — {datetime.now().strftime('%d/%m/%Y')}"]
    lines.append("")
    lines.append(f"Valor total: {portfolio_value:,.0f} AOA")
    lines.append(f"Total investido: {total_invested:,.0f} AOA")

    if gain_loss >= 0:
        lines.append(f"Ganho nao realizado: +{gain_loss:,.0f} AOA (+{gain_loss_pct:.1f}%)")
    else:
        lines.append(f"Perda nao realizada: {gain_loss:,.0f} AOA ({gain_loss_pct:.1f}%)")

    if weighted_real_yield is not None:
        if weighted_real_yield > 0:
            lines.append(f"Yield real positivo: {weighted_real_yield:.2%} — o portfolio preserva poder de compra.")
        else:
            lines.append(f"Atencao: yield real de {weighted_real_yield:.2%} — o portfolio perde poder de compra.")

    lines.append(f"{n_holdings} posicoes na carteira.")
    if top_ticker:
        lines.append(f"Maior posicao: {top_ticker}.")

    return "\n".join(lines)


def generate_weekly_report_template(
    portfolio_name: str,
    portfolio_value: float,
    performance_pct: Optional[float],
    n_bodiva_signals: int = 0,
    next_payment_date: Optional[str] = None,
    next_payment_amount: Optional[float] = None,
) -> str:
    """Template for weekly report (values filled in by AI or data)."""
    lines = [
        "=" * 60,
        f"RELATORIO SEMANAL ORBITA",
        f"Gerado em: {datetime.now().strftime('%d/%m/%Y as %H:%M')}",
        f"Carteira: {portfolio_name}",
        "=" * 60,
        "",
        f"1. RESUMO DA CARTEIRA",
        f"   Valor: {portfolio_value:,.0f} AOA",
    ]

    if performance_pct is not None:
        direction = "subida" if performance_pct >= 0 else "descida"
        lines.append(f"   Performance semanal: {performance_pct:+.2f}% ({direction})")

    lines.append("")
    lines.append("2. MERCADO BODIVA")

    if n_bodiva_signals > 0:
        lines.append(f"   {n_bodiva_signals} sinais de mercado detetados esta semana.")
    else:
        lines.append("   Sem sinais relevantes esta semana.")

    if next_payment_date and next_payment_amount:
        lines.append("")
        lines.append("3. PROXIMOS EVENTOS")
        lines.append(f"   Proximo pagamento: {next_payment_date} — {next_payment_amount:,.0f} AOA")

    lines.append("")
    lines.append("4. CONTEXTO MACRO")
    lines.append("   BNA rate: ~17% | Inflacao: ~12.4% | USD/AOA: ~650")
    lines.append("   IAC vigente: 10% (Lei 14/25)")
    lines.append("")
    lines.append("=" * 60)
    lines.append("Orbita — PulsarTec. Este relatorio e gerado automaticamente.")
    lines.append("Nao constitui aconselhamento financeiro.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# AI usage logging
# ═══════════════════════════════════════════════════════════════════════════

async def log_ai_usage(
    db: AsyncSession,
    *,
    user_id: Optional[str],
    family_id: Optional[str],
    feature: AIFeature,
    model: str,
    tokens_input: int = 0,
    tokens_output: int = 0,
    cost_usd: float = 0.0,
    user_message: Optional[str] = None,
    response_excerpt: Optional[str] = None,
    duration_ms: int = 0,
    error: Optional[str] = None,
    was_capped: bool = False,
    cache_hit: bool = False,
) -> AIAssistantLog:
    """Log an AI API call for cost tracking and auditing."""
    log = AIAssistantLog(
        user_id=user_id,
        family_id=family_id,
        feature=feature,
        model=model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
        user_message=user_message,
        response_excerpt=response_excerpt,
        duration_ms=duration_ms,
        error=error,
        was_capped=was_capped,
        cache_hit=cache_hit,
    )
    db.add(log)
    await db.commit()
    return log


# ═══════════════════════════════════════════════════════════════════════════
# Proxy for ai_news — cost-controlled news generation
# ═══════════════════════════════════════════════════════════════════════════

async def can_generate_content(
    db: AsyncSession,
    feature: AIFeature,
    tier: str = "analysis",
) -> Dict[str, Any]:
    """
    Check if content generation is allowed (daily cap + features).
    Used by ai_news.py before calling the Anthropic API.
    """
    cap = await check_daily_cap(db, feature)
    config = MODEL_TIERS.get(tier, MODEL_TIERS["analysis"])

    return {
        "allowed": cap["allowed"],
        "model": config["model"],
        "daily_remaining": cap["remaining"],
        "daily_spent": cap["spent_today"],
        "daily_cap": cap["cap"],
    }
