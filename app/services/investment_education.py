"""
investment_education.py
=======================
Orbita Academy — camada educacional para investidores angolanos.

Fornece:
  - Tooltips contextualizados para metricas do dashboard
  - Glossario financeiro PT-PT
  - Explicacoes adaptadas ao nivel do utilizador
  - Calculadoras interactivas

Base tecnica: CFA Program + Qualitative Methods skills.
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional


# ═══════════════════════════════════════════════════════════════════════════
# Glossario Financeiro
# ═══════════════════════════════════════════════════════════════════════════

GLOSSARY = {
    "ot": {
        "term": "Obrigacao do Tesouro (OT)",
        "definition": "Titulo de divida emitido pelo Governo Angolano atraves do Ministerio das Financas. Representa um emprestimo do investidor ao Estado, que paga juros (cupao) e devolve o capital no vencimento.",
        "example": "Se comprares 1.000.000 AOA em OT com cupao de 19.5%, recebes 195.000 AOA por ano em juros.",
        "level": "beginner",
        "see_also": ["ot_nr", "bt", "iac"],
    },
    "ot_nr": {
        "term": "OT-NR (Obrigacao do Tesouro — Nominativas e Reembolsaveis)",
        "definition": "OT tradicional emitida em AOA, com taxa de juro fixa e pagamento semestral de cupoes. Sao o instrumento mais comum na BODIVA para investidores de retalho.",
        "level": "beginner",
        "see_also": ["ot", "ytm"],
    },
    "bt": {
        "term": "Bilhete do Tesouro (BT)",
        "definition": "Titulo de divida de curto prazo (ate 1 ano), emitido com desconto (sem pagamento de juros). O retorno e a diferenca entre o preco de compra e o valor de reembolso.",
        "example": "Compras um BT por 95.000 AOA que reembolsa 100.000 AOA em 1 ano — ganho de ~5.26%.",
        "level": "beginner",
        "see_also": ["ot"],
    },
    "iac": {
        "term": "IAC (Imposto sobre Aplicacao de Capitais)",
        "definition": "Imposto aplicado sobre rendimentos de instrumentos financeiros em Angola. Desde 1 de Janeiro de 2026 (Lei 14/25), a taxa e de 10% para a maioria dos titulos admitidos na BODIVA.",
        "example": "Se receberes 100.000 AOA de juros de uma OT, pagas 10.000 AOA de IAC.",
        "level": "beginner",
        "see_also": ["ytm"],
    },
    "ytm": {
        "term": "YTM (Yield to Maturity / Rendimento ate ao Vencimento)",
        "definition": "O retorno total que obterias se mantivesses um titulo ate ao seu vencimento, considerando todos os pagamentos de juros (cupoes) e a diferenca entre o preco de compra e o valor de reembolso.",
        "formula": "YTM = taxa que iguala o valor presente dos fluxos futuros ao preco de mercado",
        "level": "intermediate",
        "see_also": ["duration", "fisher"],
        "for_beginners": "E como se fosse a taxa de juro 'verdadeira' do teu investimento, ja incluindo os cupoes e o ganho/perda na venda.",
    },
    "duration": {
        "term": "Duration (Macaulay)",
        "definition": "Medida de risco de taxa de juro. Representa o tempo medio (em anos) que demoras a recuperar o teu investimento atraves dos fluxos de caixa. Quanto maior a duration, maior a sensibilidade a subidas de taxa.",
        "formula": "Modified Duration = Macaulay / (1 + YTM)",
        "example": "Uma OT com duration de 5 anos perde ~5% se a taxa subir 1 ponto percentual.",
        "level": "intermediate",
        "see_also": ["ytm", "convexidade"],
    },
    "convexidade": {
        "term": "Convexidade",
        "definition": "Correcao de 2.a ordem a duration para grandes movimentos de taxa. Uma convexidade positiva significa que o titulo valoriza mais quando as taxas descem do que perde quando as taxas sobem.",
        "level": "advanced",
        "see_also": ["duration"],
    },
    "var": {
        "term": "VaR (Value at Risk / Valor em Risco)",
        "definition": "Perda maxima esperada num periodo com um dado nivel de confianca. Por exemplo, VaR 95% de 100.000 AOA num mes significa que ha 5% de probabilidade de perder mais de 100.000 AOA num mes.",
        "level": "intermediate",
        "see_also": ["cvar"],
    },
    "cvar": {
        "term": "CVaR (Expected Shortfall)",
        "definition": "Media das perdas que excedem o VaR. Mais informativo que o VaR para mercados com caudas pesadas (como Angola).",
        "level": "advanced",
        "see_also": ["var"],
    },
    "sharpe": {
        "term": "Indice de Sharpe",
        "definition": "Mede o retorno ajustado ao risco: (Retorno do Portfolio — Taxa Livre de Risco) / Volatilidade. Quanto maior, melhor a compensacao pelo risco assumido.",
        "example": "Sharpe de 0.5 significa que por cada 1% de volatilidade, o portfolio gera 0.5% de retorno extra acima da taxa livre de risco.",
        "level": "intermediate",
        "see_also": ["sortino"],
    },
    "sortino": {
        "term": "Indice de Sortino",
        "definition": "Similar ao Sharpe, mas penaliza apenas a volatilidade negativa (downside deviation). Mais relevante para investidores preocupados com perdas.",
        "level": "intermediate",
        "see_also": ["sharpe"],
    },
    "calmar": {
        "term": "Indice de Calmar",
        "definition": "Retorno anualizado dividido pelo maximo drawdown. Util em mercados de alta inflacao onde a protecao contra perdas e prioritario.",
        "level": "intermediate",
        "see_also": ["sharpe"],
    },
    "hhi": {
        "term": "HHI (Indice de Hirschman-Herfindahl)",
        "definition": "Soma dos quadrados dos pesos de cada posicao no portfolio. HHI < 0.10 indica boa diversificacao. HHI > 0.25 indica concentracao excessiva.",
        "example": "Um portfolio com 5 posicoes iguais tem HHI = 0.20. Com 10 posicoes iguais, HHI = 0.10.",
        "level": "intermediate",
        "see_also": ["gini"],
    },
    "fisher": {
        "term": "Equacao de Fisher",
        "definition": "(1 + Yield Nominal) / (1 + Inflacao) — 1. Determina o retorno real, ajustado pela perda de poder de compra devido a inflacao.",
        "example": "Se uma OT rende 19.5% e a inflacao e 12.4%: (1.195/1.124) — 1 = 6.3% de retorno real.",
        "level": "intermediate",
        "see_also": ["ytm"],
    },
    "bodiva": {
        "term": "BODIVA (Bolsa de Divida e Valores de Angola)",
        "definition": "A bolsa de valores oficial de Angola, operacional desde 2014. Negocia Obrigacoes do Tesouro (OT), Bilhetes do Tesouro (BT), Accoes de empresas e outros instrumentos financeiros.",
        "level": "beginner",
        "see_also": ["ot", "bt"],
    },
    "bna": {
        "term": "BNA (Banco Nacional de Angola)",
        "definition": "Banco central de Angola. Define a taxa de juro de referencia (BNA rate), que influencia o rendimento de todos os instrumentos financeiros no pais.",
        "level": "beginner",
        "see_also": ["ot"],
    },
    "kwanza_risk": {
        "term": "Risco Cambial / Desvalorizacao do Kwanza",
        "definition": "O Kwanza (AOA) pode desvalorizar face a moedas fortes (USD, EUR). Para o investidor angolano, isto significa que investir apenas em AOA pode resultar em perda de poder de compra internacional.",
        "tip": "Para proteger o teu patrimonio contra a desvalorizacao do kwanza, considera alocar 30-50% do teu portfolio a ativos internacionais (USD, EUR, ZAR).",
        "level": "beginner",
        "see_also": ["diversificacao"],
    },
    "diversificacao": {
        "term": "Diversificacao",
        "definition": "Estrategia de distribuir o investimento por diferentes ativos, setores ou paises para reduzir o risco. Em Angola, diversificar entre AOA e moedas fortes e essencial.",
        "level": "beginner",
        "see_also": ["kwanza_risk"],
    },
    "dca": {
        "term": "DCA (Dollar Cost Averaging)",
        "definition": "Investir montantes fixos em intervalos regulares, independentemente do preco. Reduz o impacto da volatilidade e elimina a tentacao de tentar acertar o timing do mercado.",
        "example": "Investir 100.000 AOA por mes em vez de 1.200.000 AOA de uma so vez.",
        "level": "beginner",
        "see_also": ["lump_sum"],
    },
    "lump_sum": {
        "term": "Lump Sum (Investimento Unico)",
        "definition": "Investir todo o capital de uma so vez. Estudos mostram que, em mercados com tendencia de alta, o lump sum tende a superar o DCA em ~67% dos casos.",
        "level": "beginner",
        "see_also": ["dca"],
    },
    "bullet_barbell_ladder": {
        "term": "Estrategias de Yield Curve (Bullet, Barbell, Ladder)",
        "definition": "Tres abordagens para distribuir investimentos ao longo da curva de juros:\n- Bullet: concentrar numa unica maturidade\n- Barbell: pesos nos extremos (curto + longo prazo)\n- Ladder: escalonar maturidades (1,2,3,4,5 anos)",
        "level": "intermediate",
        "see_also": ["ytm", "duration"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# Tooltips (metric -> short explanation for dashboard overlays)
# ═══════════════════════════════════════════════════════════════════════════

TOOLTIPS = {
    "var_95": "Perda maxima esperada com 95% de confianca num mes. Ha 5% de probabilidade de perder mais que este valor.",
    "cvar_95": "Media das perdas que excedem o VaR. Mais conservador que o VaR — considera o 'pior dos piores' cenarios.",
    "sharpe_ratio": "Retorno ajustado ao risco. >0.5 = bom, >1.0 = excelente. Compara o ganho extra com a volatilidade suportada.",
    "sortino_ratio": "Similar ao Sharpe mas so penaliza a volatilidade negativa (perdas). Melhor para avaliar protecao contra quedas.",
    "calmar_ratio": "Retorno anual / max drawdown. Mede a consistencia — util em mercados com alta inflacao como Angola.",
    "macaulay_duration": "Prazo medio de recuperacao do investimento (anos). Quanto maior, mais o titulo sofre com subidas de taxa.",
    "modified_duration": "Variacao % estimada no preco para cada 1pp de variacao na taxa de juro.",
    "convexity": "Correcao a duration. Positiva = o titulo valoriza mais em descidas de taxa do que perde em subidas.",
    "hhi": "Indice de concentracao. <0.10 = bem diversificado, 0.10-0.25 = moderado, >0.25 = concentrado.",
    "gini": "Coeficiente de desigualdade na alocacao. 0 = todos iguais, 1 = tudo num ativo so.",
    "effective_n": "Numero efetivo de posicoes. Se HHI = 0.2, N_efetivo = 5 (equivalente a 5 posicoes iguais).",
    "liquidity_score": "Medida de facilidade de saida do mercado. >100 = alta, 30-100 = media, <30 = baixa.",
    "weighted_yield": "Yield medio do portfolio, ponderado pelo peso de cada posicao. Inclui efeito de IAC.",
    "weighted_real_yield": "Yield medio real (apos IAC e inflacao). Se negativo, o portfolio perde poder de compra.",
    "max_drawdown": "Maior queda do portfolio desde o pico ate ao vale. Indica o risco historico maximo.",
    "crp": "Country Risk Premium — premio de risco Angola segundo Damodaran. Adicionado ao custo do capital.",
}


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def get_glossary(
    search: Optional[str] = None,
    level: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get glossary terms, optionally filtered by search query or level.
    """
    results = []
    for key, entry in GLOSSARY.items():
        if level and entry.get("level") != level:
            continue
        if search:
            query = search.lower()
            if (query not in entry["term"].lower()
                    and query not in entry.get("definition", "").lower()):
                continue
        results.append({
            "key": key,
            "term": entry["term"],
            "definition": entry.get("definition", ""),
            "level": entry.get("level", "beginner"),
            "has_example": "example" in entry,
            "has_formula": "formula" in entry,
        })

    return results


def get_explanation(concept: str, level: str = "beginner") -> Optional[Dict[str, Any]]:
    """Get explanation for a specific concept, adapted to user level."""
    entry = GLOSSARY.get(concept)
    if not entry:
        return None

    result = {
        "term": entry["term"],
        "definition": entry["definition"],
        "level": entry.get("level", "beginner"),
    }

    if level == "beginner" and "for_beginners" in entry:
        result["simplified"] = entry["for_beginners"]

    if "example" in entry and level != "advanced":
        result["example"] = entry["example"]

    if "formula" in entry and level != "beginner":
        result["formula"] = entry["formula"]

    if "tip" in entry:
        result["tip"] = entry["tip"]

    return result


def get_tooltip(metric: str) -> Optional[Dict[str, str]]:
    """Get tooltip for a dashboard metric."""
    text = TOOLTIPS.get(metric)
    if not text:
        return None
    return {"metric": metric, "tooltip": text}


def get_popular_terms(limit: int = 6) -> List[Dict[str, Any]]:
    """Get most popular/requested glossary terms."""
    popular_keys = ["ot", "iac", "ytm", "duration", "sharpe", "hhi"]
    return [
        {"key": k, "term": GLOSSARY[k]["term"], "definition": GLOSSARY[k]["definition"][:120] + "..."}
        for k in popular_keys[:limit]
        if k in GLOSSARY
    ]


def calc_simple_ytm(
    current_price: float,
    par_value: float,
    coupon_rate: float,
    years_to_maturity: float,
    tax_rate: float = 0.10,
) -> Dict[str, Any]:
    """
    Simplified YTM calculator for educational purposes (approximation).
    Real YTM uses Newton-Raphson (financial_core.solve_ytm).
    """
    annual_coupon = par_value * coupon_rate
    capital_gain = (par_value - current_price) / years_to_maturity
    annual_return = (annual_coupon + capital_gain) / ((current_price + par_value) / 2)
    after_tax_return = annual_return * (1 - tax_rate)

    return {
        "current_price": round(current_price, 2),
        "par_value": round(par_value, 2),
        "coupon_rate": round(coupon_rate * 100, 2),
        "years_to_maturity": years_to_maturity,
        "ytm_approximate_pct": round(annual_return * 100, 2),
        "ytm_after_tax_pct": round(after_tax_return * 100, 2),
        "annual_coupon_aoa": round(annual_coupon, 2),
        "capital_gain_annual_aoa": round(capital_gain, 2),
        "disclaimer": "Valor aproximado. Para calculo exato, usa o YTM solver no portfolio analytics.",
    }


def calc_iac_impact(
    gross_return: float,
    iac_rate: float = 0.10,
    inflation: float = 0.1242,
) -> Dict[str, Any]:
    """Educational calculator: shows the impact of IAC + inflation on returns."""
    after_iac = gross_return * (1 - iac_rate)
    real_after_iac = (1 + after_iac) / (1 + inflation) - 1

    return {
        "gross_return": round(gross_return * 100, 2),
        "iac_rate": round(iac_rate * 100, 2),
        "after_iac_return": round(after_iac * 100, 2),
        "inflation": round(inflation * 100, 2),
        "real_return_after_iac": round(real_after_iac * 100, 2),
        "tax_impact_pct": round((gross_return - after_iac) * 100, 2),
        "total_erosion_pct": round((gross_return - real_after_iac) * 100, 2),
    }
