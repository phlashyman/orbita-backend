# -*- coding: utf-8 -*-
"""
service - Orquestrador de ingestão (Órbita)
===========================================
Recebe um ficheiro, detecta o tipo, escolhe o parser certo, executa-o e devolve
um IngestResult. A ESCRITA na base de dados é feita à parte (persistence), para
o orquestrador ser independente do dialecto e de sync/async.

Há DOIS pontos de entrada:

  parse_file(...)  -> devolve um IngestResult (NÃO toca na base de dados).
                      É este que deves usar num backend assíncrono (asyncpg):
                      fazes parse_file() e depois await apply_ingest_result_async().

  ingest_file(...) -> faz parse + apply numa só chamada (caminho SÍNCRONO:
                      sqlite3 / psycopg2). Mantido para scripts e testes.

Regra de papéis: ficheiros institucionais BODIVA só podem ser carregados pelo admin.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from .common import IngestResult, sha256_of_file
from .detect import detect_file
from .excel_parsers import (
    parse_aurea_carteira,
    parse_aurea_destaques,
    parse_bodiva_resumo,
    parse_ordens_disponiveis,
)
from .pdf_parsers import (
    parse_bodiva_boletim,
    parse_bodiva_relatorio,
    parse_ficha_tecnica,
    parse_standard_carteira,
)

# ficheiros institucionais BODIVA -> só o admin pode carregar (regra do projecto)
ADMIN_ONLY = {
    "bodiva_resumo", "bodiva_boletim",
    "bodiva_relatorio_mensal", "bodiva_relatorio_trimestral",
}


class ForbiddenFile(Exception):
    """Ficheiro institucional carregado por não-admin."""


class UndetectedFile(Exception):
    """Tipo de ficheiro não reconhecido (score abaixo do limiar)."""


def _dispatch(parser_key, path, file_hash, user_id, portfolio_id, snapshot_date, source_hint):
    if parser_key == "aurea_carteira":
        return parse_aurea_carteira(path, file_hash, user_id, portfolio_id, snapshot_date)
    if parser_key == "aurea_destaques":
        return parse_aurea_destaques(path, file_hash, user_id)
    if parser_key == "ordens_disponiveis":
        src = source_hint or "bodiva_ordens"
        return parse_ordens_disponiveis(path, file_hash, src, user_id)
    if parser_key == "bodiva_resumo":
        return parse_bodiva_resumo(path, file_hash, user_id)
    if parser_key == "standard_carteira":
        return parse_standard_carteira(path, file_hash, user_id, portfolio_id, snapshot_date)
    if parser_key == "ficha_tecnica":
        return parse_ficha_tecnica(path, file_hash, user_id)
    if parser_key == "bodiva_boletim":
        return parse_bodiva_boletim(path, file_hash, user_id)
    if parser_key == "bodiva_relatorio_mensal":
        return parse_bodiva_relatorio(path, file_hash, user_id, "mensal")
    if parser_key == "bodiva_relatorio_trimestral":
        return parse_bodiva_relatorio(path, file_hash, user_id, "trimestral")
    return None


# =========================================================================== #
# PARSE-ONLY (recomendado para backend assíncrono asyncpg)
# =========================================================================== #
def parse_file(
    path: str,
    user_id: Optional[int],
    *,
    is_admin: bool = False,
    portfolio_id: Optional[int] = None,
    snapshot_date=None,
    source_hint: Optional[str] = None,
) -> IngestResult:
    """
    Detecta + processa. Devolve o IngestResult (sem tocar na base de dados).

    Levanta:
      UndetectedFile  -> tipo não reconhecido (mapear para HTTP 415/422).
      ForbiddenFile   -> ficheiro institucional sem permissões de admin (HTTP 403).

    O file_hash é calculado aqui (idempotência) e guardado no result.
    """
    file_hash = sha256_of_file(path)
    parser_key, score, all_scores = detect_file(path)

    if parser_key is None:
        raise UndetectedFile(
            "Tipo de ficheiro não reconhecido (melhor score %.2f): %s"
            % (score, all_scores)
        )
    if parser_key in ADMIN_ONLY and not is_admin:
        raise ForbiddenFile(
            "Ficheiro institucional BODIVA (%s) - apenas o admin pode carregar." % parser_key
        )

    result = _dispatch(parser_key, path, file_hash, user_id,
                       portfolio_id, snapshot_date, source_hint)
    if result is None:
        raise UndetectedFile("Sem parser associado a '%s'." % parser_key)

    # anexar metadados de detecção (úteis para logs/respostas)
    result.detected_key = parser_key            # type: ignore[attr-defined]
    result.detected_score = round(score, 3)     # type: ignore[attr-defined]
    return result


def detect_only(path: str) -> Dict[str, Any]:
    """Só detecção - útil para um endpoint /preview ou para depurar."""
    file_hash = sha256_of_file(path)
    parser_key, score, all_scores = detect_file(path)
    return {
        "file": os.path.basename(path),
        "file_hash": file_hash,
        "detected": parser_key,
        "score": round(score, 3),
        "all_scores": {k: round(v, 3) for k, v in all_scores.items()},
        "admin_only": parser_key in ADMIN_ONLY if parser_key else None,
    }


# =========================================================================== #
# PARSE + APPLY síncrono (sqlite3 / psycopg2). NÃO usar com asyncpg.
# =========================================================================== #
def ingest_file(
    path: str,
    user_id: Optional[int],
    conn: Optional[Any] = None,
    *,
    portfolio_id: Optional[int] = None,
    snapshot_date=None,
    source_hint: Optional[str] = None,
    paramstyle: str = "qmark",       # 'qmark' (sqlite) | 'format' (psycopg2/PyMySQL)
    is_admin: bool = False,
    apply: bool = True,
) -> Dict[str, Any]:
    """
    Caminho síncrono completo. Para asyncpg, usar antes parse_file() +
    apply_ingest_result_async() (ver persistence_async.py).
    """
    # importação tardia para não obrigar a ter a persistência síncrona presente
    try:
        from .persistence import apply_ingest_result
    except ImportError:
        from persistence import apply_ingest_result

    out: Dict[str, Any] = {"file": os.path.basename(path)}
    try:
        result = parse_file(path, user_id, is_admin=is_admin,
                            portfolio_id=portfolio_id, snapshot_date=snapshot_date,
                            source_hint=source_hint)
    except UndetectedFile as exc:
        out["status"] = "undetected"; out["error"] = str(exc); return out
    except ForbiddenFile as exc:
        out["status"] = "forbidden"; out["error"] = str(exc); return out

    out["file_hash"] = result.file_hash
    out["detected"] = getattr(result, "detected_key", None)
    out["score"] = getattr(result, "detected_score", None)
    out["result"] = {
        "parser": result.parser_name,
        "snapshot_date": result.snapshot_date.isoformat() if result.snapshot_date else None,
        "summary": result.summary,
        "rows_processed": result.rows_processed,
        "rows_to_write": len(result.rows),
        "warnings": result.warnings,
        "errors": result.errors,
        "duration_seconds": round(result.duration_seconds, 3),
    }

    if apply and conn is not None:
        out["apply"] = apply_ingest_result(conn, result, paramstyle=paramstyle)
        out["status"] = out["apply"]["status"]
    else:
        out["status"] = "parsed" if result.ok else "failed"
    return out
