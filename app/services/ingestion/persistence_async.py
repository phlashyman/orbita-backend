# -*- coding: utf-8 -*-
"""
persistence_async - escrita IDEMPOTENTE e TRANSACCIONAL com asyncpg (PostgreSQL)
================================================================================
A persistence.py original é SÍNCRONA (cursor(), placeholders '?'/'%s') e serve
sqlite3 / psycopg2. O teu backend usa asyncpg, que é ASSÍNCRONO e usa placeholders
numerados ($1, $2, ...). Este módulo é o equivalente nativo para asyncpg.

Mantém os mesmos princípios:
  - Idempotência por ficheiro: verifica o hash em import_log antes de aplicar.
  - Idempotência por linha: DELETE pelas conflict_keys + INSERT (sem UPSERT).
  - Atomicidade: tudo dentro de `async with conn.transaction():` (ROLLBACK no erro).
  - Tolerância a drift de schema: só insere colunas que EXISTEM (information_schema).

Uso típico no endpoint /process (FastAPI + asyncpg):

    from service import parse_file, ForbiddenFile, UndetectedFile
    from persistence_async import apply_ingest_result_async

    result = parse_file(tmp_path, user_id=user["id"], is_admin=user["is_admin"],
                        portfolio_id=portfolio_id, snapshot_date=snapshot_date)
    async with pool.acquire() as conn:          # pool asyncpg
        out = await apply_ingest_result_async(conn, result)
    return out

(parse_file é síncrono e não toca na DB; só o apply é assíncrono.)
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

from .common import IngestResult


# --------------------------------------------------------------------------- #
# Introspecção de colunas + tipos (cache por processo)
# --------------------------------------------------------------------------- #
_TYPES_CACHE: Dict[str, Dict[str, str]] = {}


async def table_coltypes(conn, table: str) -> Dict[str, str]:
    """{coluna: data_type} via information_schema (em minúsculas, como o PG guarda)."""
    if table in _TYPES_CACHE:
        return _TYPES_CACHE[table]
    rows = await conn.fetch(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = $1",
        table,
    )
    types = {r["column_name"]: r["data_type"] for r in rows}
    _TYPES_CACHE[table] = types
    return types


async def table_columns(conn, table: str) -> Set[str]:
    return set((await table_coltypes(conn, table)).keys())


async def table_exists(conn, table: str) -> bool:
    return len(await table_coltypes(conn, table)) > 0


def _coerce(value: Any, data_type: Optional[str]) -> Any:
    """
    asyncpg é estrito: para DATE/TIMESTAMP exige date/datetime, não strings ISO.
    Os parsers emitem datas como strings .isoformat() -> converter aqui.
    """
    if value is None or data_type is None or not isinstance(value, str):
        return value
    dt = data_type.lower()
    try:
        if dt == "date":
            return date.fromisoformat(value[:10])
        if dt.startswith("timestamp"):
            return datetime.fromisoformat(value)
    except ValueError:
        return value
    return value


# --------------------------------------------------------------------------- #
# Idempotência por ficheiro
# --------------------------------------------------------------------------- #
async def check_already_imported(conn, file_hash: str, parser_name: str,
                                 user_id: Optional[int]) -> bool:
    if not await table_exists(conn, "import_log"):
        return False
    cols = await table_columns(conn, "import_log")
    where = ["file_hash = $1", "status = $2"]
    params: List[Any] = [file_hash, "success"]
    if "parser_name" in cols:
        params.append(parser_name)
        where.append("parser_name = $%d" % len(params))
    if "user_id" in cols and user_id is not None:
        params.append(user_id)
        where.append("user_id = $%d" % len(params))
    sql = "SELECT COUNT(*) AS n FROM import_log WHERE " + " AND ".join(where)
    row = await conn.fetchrow(sql, *params)
    return (row["n"] if row else 0) > 0


# --------------------------------------------------------------------------- #
# Operações elementares
# --------------------------------------------------------------------------- #
async def _delete_where(conn, table: str, keys: Dict[str, Any]):
    if not keys:
        return
    types = await table_coltypes(conn, table)
    cols = list(keys.keys())
    clause = " AND ".join("%s = $%d" % (c, i + 1) for i, c in enumerate(cols))
    args = [_coerce(keys[c], types.get(c)) for c in cols]
    await conn.execute("DELETE FROM %s WHERE %s" % (table, clause), *args)


async def _insert(conn, table: str, values: Dict[str, Any]):
    types = await table_coltypes(conn, table)
    cols = list(values.keys())
    placeholders = ", ".join("$%d" % (i + 1) for i in range(len(cols)))
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (table, ", ".join(cols), placeholders)
    args = [_coerce(values[c], types.get(c)) for c in cols]
    await conn.execute(sql, *args)


# --------------------------------------------------------------------------- #
# Aplicar um IngestResult
# --------------------------------------------------------------------------- #
async def apply_ingest_result_async(conn, result: IngestResult, *,
                                    skip_if_imported: bool = True) -> Dict[str, Any]:
    """
    `conn` é uma ligação asyncpg (asyncpg.Connection). Com um Pool, fazer antes:
        async with pool.acquire() as conn: await apply_ingest_result_async(conn, result)
    """
    if result.errors:
        await _log_import(conn, result, status="failed")
        return {"status": "failed", "applied": 0, "error": "; ".join(result.errors)}

    if skip_if_imported and await check_already_imported(
            conn, result.file_hash, result.parser_name, result.user_id):
        return {"status": "skipped", "applied": 0,
                "error": "ficheiro já importado (hash em import_log)"}

    applied = 0
    try:
        async with conn.transaction():
            for row in result.rows:
                if not await table_exists(conn, row.table):
                    result.warnings.append("Tabela inexistente, linha ignorada: %s" % row.table)
                    continue
                existing = await table_columns(conn, row.table)
                values = {k: v for k, v in row.values.items() if k in existing}
                conflict = {k: values[k] for k in row.conflict_keys
                            if k in values and k in existing}
                await _delete_where(conn, row.table, conflict)
                await _insert(conn, row.table, values)
                applied += 1
            await _log_import(conn, result, status="success", applied=applied)
        return {"status": "success", "applied": applied,
                "skipped": result.rows_skipped, "warnings": result.warnings}
    except Exception as exc:  # a transacção já fez ROLLBACK
        result.errors.append(str(exc))
        try:
            await _log_import(conn, result, status="failed")
        except Exception:
            pass
        return {"status": "failed", "applied": 0, "error": str(exc)}


async def _log_import(conn, result: IngestResult, status: str, applied: int = 0):
    if not await table_exists(conn, "import_log"):
        return
    candidate = {
        "user_id": result.user_id,
        "parser_name": result.parser_name,
        "file_hash": result.file_hash,
        "snapshot_date": result.snapshot_date.isoformat() if result.snapshot_date else None,
        "status": status,
        "rows_processed": result.rows_processed,
        "rows_applied": applied,
        "rows_skipped": result.rows_skipped,
        "warnings": json.dumps(result.warnings, ensure_ascii=False) if result.warnings else None,
        "errors": json.dumps(result.errors, ensure_ascii=False) if result.errors else None,
        "summary": result.summary,
        "duration_seconds": result.duration_seconds,
        "imported_at": datetime.now().isoformat(timespec="seconds"),
    }
    existing = await table_columns(conn, "import_log")
    values = {k: v for k, v in candidate.items() if k in existing}
    if values:
        await _insert(conn, "import_log", values)
