# -*- coding: utf-8 -*-
"""
persistence_sqlalchemy — escrita idempotente via SQLAlchemy AsyncSession.

Equivalente ao persistence_async.py mas usa sqlalchemy.text() em vez de
asyncpg directo, para ser compatível com o backend FastAPI + SQLAlchemy 2.0.

Uso no endpoint /process:

    from app.services.ingestion.persistence_sqlalchemy import apply_ingest_result
    out = await apply_ingest_result(db, result)
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .common import IngestResult


# --------------------------------------------------------------------------- #
# Schema introspection (cached per process)
# --------------------------------------------------------------------------- #
_COL_CACHE: Dict[str, Set[str]] = {}


async def _table_columns(db: AsyncSession, table: str) -> Set[str]:
    if table in _COL_CACHE:
        return _COL_CACHE[table]
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :t"
        ),
        {"t": table},
    )
    cols = {row[0] for row in result}
    if cols:
        _COL_CACHE[table] = cols
    return cols


async def _table_exists(db: AsyncSession, table: str) -> bool:
    return len(await _table_columns(db, table)) > 0


# --------------------------------------------------------------------------- #
# Type coercion — parsers emit ISO strings; PostgreSQL DATE/TIMESTAMP need
# Python date/datetime objects when using SQLAlchemy text() bindparams.
# --------------------------------------------------------------------------- #
def _coerce(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    # Try date first (shorter)
    if len(value) == 10:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    # Try datetime
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    return value


# --------------------------------------------------------------------------- #
# Import log
# --------------------------------------------------------------------------- #
async def _log_import(db: AsyncSession, result: IngestResult, *,
                      status: str, applied: int = 0) -> None:
    if not await _table_exists(db, "import_log"):
        return
    cols = await _table_columns(db, "import_log")
    row: Dict[str, Any] = {}
    mapping = {
        "parser_name": result.parser_name,
        "file_hash": result.file_hash,
        "snapshot_date": result.snapshot_date,
        "status": status,
        "rows_processed": result.rows_processed,
        "rows_applied": applied,
        "rows_skipped": result.rows_skipped,
        "warnings": json.dumps(result.warnings) if result.warnings else None,
        "errors": json.dumps(result.errors) if result.errors else None,
        "summary": result.summary or None,
        "duration_seconds": result.duration_seconds,
    }
    for k, v in mapping.items():
        if k in cols:
            row[k] = _coerce(v)

    if row:
        col_str = ", ".join(row.keys())
        ph = ", ".join(f":{k}" for k in row.keys())
        await db.execute(text(f"INSERT INTO import_log ({col_str}) VALUES ({ph})"), row)


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
async def apply_ingest_result(db: AsyncSession, result: IngestResult, *,
                              skip_if_imported: bool = True) -> Dict[str, Any]:
    """
    Apply an IngestResult to the database using SQLAlchemy AsyncSession.
    Returns {"status": "success"|"failed"|"skipped", "applied": N, "error": ...}
    """
    if result.errors:
        await _log_import(db, result, status="failed")
        return {"status": "failed", "applied": 0, "error": "; ".join(result.errors)}

    # Idempotency: skip if same file hash already imported successfully
    if skip_if_imported and result.file_hash and await _table_exists(db, "import_log"):
        check = await db.execute(
            text("SELECT COUNT(*) FROM import_log WHERE file_hash = :h AND status = 'success'"),
            {"h": result.file_hash},
        )
        if (check.scalar() or 0) > 0:
            return {"status": "skipped", "applied": 0,
                    "error": "ficheiro já importado (hash em import_log)"}

    applied = 0
    try:
        for row in result.rows:
            if not await _table_exists(db, row.table):
                result.warnings.append(f"Tabela inexistente, linha ignorada: {row.table}")
                continue

            existing = await _table_columns(db, row.table)
            values = {k: _coerce(v) for k, v in row.values.items() if k in existing}
            if not values:
                continue

            conflict = {k: values[k] for k in row.conflict_keys if k in values}

            # DELETE by conflict keys then INSERT (idempotent upsert)
            if conflict:
                where = " AND ".join(f"{k} = :ck_{k}" for k in conflict)
                await db.execute(
                    text(f"DELETE FROM {row.table} WHERE {where}"),
                    {f"ck_{k}": v for k, v in conflict.items()},
                )

            col_str = ", ".join(values.keys())
            ph = ", ".join(f":v_{k}" for k in values.keys())
            await db.execute(
                text(f"INSERT INTO {row.table} ({col_str}) VALUES ({ph})"),
                {f"v_{k}": v for k, v in values.items()},
            )
            applied += 1

        await _log_import(db, result, status="success", applied=applied)
        return {"status": "success", "applied": applied}

    except Exception as exc:
        result.errors.append(str(exc))
        return {"status": "failed", "applied": applied, "error": str(exc)}
