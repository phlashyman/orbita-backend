# -*- coding: utf-8 -*-
"""
orbita_ingest.detect
====================
Deteção do tipo de ficheiro. Cada candidato devolve um score 0..1 a partir de:
  - extensão (.xlsx / .pdf)
  - nome do ficheiro (timestamps, 'boletimdiario', 'relatoriomensal', ...)
  - nome da folha (Excel) e cabeçalhos
  - palavras-chave da 1.ª página (PDF)

detect_file() devolve a chave do parser de score mais alto acima do threshold.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import openpyxl
import pdfplumber

THRESHOLD = 0.5


def _excel_first_rows(path: str, n: int = 3) -> Tuple[str, List[str]]:
    """Devolve (nome_da_folha, lista de cabeçalhos em minúsculas das 1.as linhas)."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    headers = []
    for r in range(1, n + 1):
        for c in range(1, 18):
            v = ws.cell(row=r, column=c).value
            if v is not None:
                headers.append(str(v).strip().lower())
    return ws.title or "", headers


def _pdf_head_text(path: str, pages: int = 3) -> str:
    out = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages[:pages]:
            out.append((p.extract_text() or ""))
    return "\n".join(out).upper()


def _score_excel(path: str) -> Dict[str, float]:
    fname = os.path.basename(path).lower()
    try:
        sheet, headers = _excel_first_rows(path)
    except Exception:
        return {}
    sheet_l = sheet.lower()
    H = " | ".join(headers)
    s: Dict[str, float] = {k: 0.0 for k in
                           ("aurea_carteira", "aurea_destaques",
                            "ordens_disponiveis", "bodiva_resumo")}

    # aurea_carteira
    if "título" in headers or "titulo" in headers:
        s["aurea_carteira"] += 0.25
        s["aurea_destaques"] += 0.2
    if "ticker" in headers:
        s["aurea_carteira"] += 0.2
        s["aurea_destaques"] += 0.2
    if "mercado" in headers:
        s["aurea_carteira"] += 0.25
    if "aquisição" in H or "aquisicao" in H:
        s["aurea_carteira"] += 0.3
    if any("cotação" in h or "cotacao" in h for h in headers):
        s["aurea_carteira"] += 0.1

    # aurea_destaques
    if any("var. diária" in h or "var. diaria" in h for h in headers):
        s["aurea_destaques"] += 0.3
    if "compra" in headers and "venda" in headers and "volume" in headers:
        s["aurea_destaques"] += 0.3
    if any("últ. cotação" in h or "ult. cotacao" in h for h in headers):
        s["aurea_destaques"] += 0.2

    # ordens disponíveis
    if "ordens disponíveis" in sheet_l or "ordens disponiveis" in sheet_l:
        s["ordens_disponiveis"] += 0.6
    if fname.startswith("ordens_disponiveis"):
        s["ordens_disponiveis"] += 0.3
    if "yield" in H and "isin" in H:
        s["ordens_disponiveis"] += 0.2

    # bodiva resumo
    if "resumo dos mercados" in sheet_l:
        s["bodiva_resumo"] += 0.5
    if fname.startswith("resumo_dos_mercados"):
        s["bodiva_resumo"] += 0.3
    if any("valor mobiliário" in h or "valor mobiliario" in h for h in headers):
        s["bodiva_resumo"] += 0.3
    if any("n° de negócios" in h or "negócios" in h or "negocios" in h for h in headers):
        s["bodiva_resumo"] += 0.1

    return s


def _score_pdf(path: str) -> Dict[str, float]:
    fname = os.path.basename(path).lower()
    try:
        txt = _pdf_head_text(path)
    except Exception:
        txt = ""
    s: Dict[str, float] = {k: 0.0 for k in
                           ("standard_carteira", "ficha_tecnica", "bodiva_boletim",
                            "bodiva_relatorio_mensal", "bodiva_relatorio_trimestral")}

    if "A MINHA CARTEIRA" in txt:
        s["standard_carteira"] += 0.5
    if "FEIVMA" in txt:
        s["standard_carteira"] += 0.3
    if "GANHOS NÃO REALIZADOS" in txt or "PRODUTO" in txt:
        s["standard_carteira"] += 0.2

    if "FICHA TÉCNICA" in txt or "FICHA TECNICA" in txt:
        s["ficha_tecnica"] += 0.5
    if "ISIN" in txt and ("CÓDIGO DE NEGOCIAÇÃO" in txt or "CODIGO DE NEGOCIACAO" in txt):
        s["ficha_tecnica"] += 0.3
    if "VALOR NOMINAL" in txt and "EMITENTE" in txt:
        s["ficha_tecnica"] += 0.2

    if "BOLETIM" in txt and "BODIVA" in txt:
        s["bodiva_boletim"] += 0.6
    if fname.startswith("boletimdiario"):
        s["bodiva_boletim"] += 0.3
    if "RESUMO DE MERCADO" in txt:
        s["bodiva_boletim"] += 0.1

    if "RELATÓRIO MENSAL" in txt or "RELATORIO MENSAL" in txt or fname.startswith("relatoriomensal"):
        s["bodiva_relatorio_mensal"] += 0.7
    if "TRIMESTRE" in txt or "TRIMESTRAL" in txt or "trimestral" in fname:
        s["bodiva_relatorio_trimestral"] += 0.7

    return s


def detect_file(path: str) -> Tuple[Optional[str], float, Dict[str, float]]:
    """
    Devolve (parser_key, score, todos_os_scores).
    parser_key é None se nada ultrapassar o THRESHOLD.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        scores = _score_excel(path)
    elif ext == ".pdf":
        scores = _score_pdf(path)
    else:
        return None, 0.0, {}

    if not scores:
        return None, 0.0, {}
    best_key = max(scores, key=scores.get)
    best_score = scores[best_key]
    return (best_key if best_score >= THRESHOLD else None), best_score, scores
