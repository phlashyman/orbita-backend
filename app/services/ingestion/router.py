# -*- coding: utf-8 -*-
"""
orbita_ingest.persistence
=========================
Aplica um IngestResult à base de dados de forma TRANSACCIONAL e IDEMPOTENTE.

Princípios:
  - O parser nunca escreve; devolve DBRows. Esta camada é a única que toca na DB.
  - Idempotência por linha: para cada DBRow faz DELETE pelas conflict_keys + INSERT
    (delete+insert é portável entre SQLite e MariaDB; evita sintaxe de UPSERT
    específica do dialecto).
  - Idempotência por ficheiro: antes de aplicar, verifica import_log pelo hash.
  - Tolerância a drift de schema: só insere colunas que EXISTEM na tabela
    (introspecção via PRAGMA / information_schema). Assim, se a DB ainda não tiver
    'portfolio_id' ou 'user_id', o insert não rebenta.

Suporta sqlite3 (paramstyle 'qmark', '?') e PyMySQL/mysqlclient ('format', '%s').
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .common import IngestResult


class DBAdapter:
    def __init__(self, conn, paramstyle: str = "qmark"):
        self.conn = conn
        self.ph = "?" if paramstyle == "qmark" else "%s"
        self._cols_cache: Dict[str, Set[str]] = {}

    # -- introspecção de colunas ------------------------------------------- #
    def columns(self, table: str) -> Set[str]:
        if table in self._cols_cache:
            return self._cols_cache[table]
        cur = self.conn.cursor()
        cols: Set[str] = set()
        try:  # SQLite
            cur.execute("PRAGMA table_info(%s)" % table)
            cols = {row[1] for row in cur.fetchall()}
        except Exception:
            cols = set()
        if not cols:
            try:  # MariaDB / MySQL
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s" % self.ph, (table,))
                cols = {row[0] for row in cur.fetchall()}
            except Exception:
                cols = set()
        self._cols_cache[table] = cols
        return cols

    def table_exists(self, table: str) -> bool:
        return len(self.columns(table)) > 0

    # -- operações --------------------------------------------------------- #
    def delete_where(self, table: str, keys: Dict[str, Any]):
        if not keys:
            return
        clause = " AND ".join("%s = %s" % (k, self.ph) for k in keys)
        sql = "DELETE FROM %s WHERE %s" % (table, clause)
        self.conn.cursor().execute(sql, tuple(keys.values()))

    def insert(self, table: str, values: Dict[str, Any]):
        cols = list(values.keys())
        placeholders = ", ".join([self.ph] * len(cols))
        sql = "INSERT INTO %s (%s) VALUES (%s)" % (
            table, ", ".join(cols), placeholders)
        self.conn.cursor().execute(sql, tuple(values[c] for c in cols))


def check_already_imported(adapter: DBAdapter, file_hash: str,
                           parser_name: str, user_id: Optional[int]) -> bool:
    """True se já existe um import com sucesso para este hash/parser/user."""
    if not adapter.table_exists("import_log"):
        return False
    cur = adapter.conn.cursor()
    cols = adapter.columns("import_log")
    where = ["file_hash = %s" % adapter.ph, "status = %s" % adapter.ph]
    params: List[Any] = [file_hash, "success"]
    if "parser_name" in cols:
        where.append("parser_name = %s" % adapter.ph)
        params.append(parser_name)
    if "user_id" in cols and user_id is not None:
        where.append("user_id = %s" % adapter.ph)
        params.append(user_id)
    sql = "SELECT COUNT(*) FROM import_log WHERE " + " AND ".join(where)
    cur.execute(sql, tuple(params))
    return (cur.fetchone() or [0])[0] > 0


def apply_ingest_result(conn, result: IngestResult, *,
                        paramstyle: str = "qmark",
                        skip_if_imported: bool = True) -> Dict[str, Any]:
    """
    Aplica o resultado dentro de uma transacção única.
    Devolve um dict com o estado: {status, applied, skipped, error}.
    """
    adapter = DBAdapter(conn, paramstyle)

    if result.errors:
        _log_import(adapter, result, status="failed")
        conn.commit()
        return {"status": "failed", "applied": 0, "error": "; ".join(result.errors)}

    if skip_if_imported and check_already_imported(
            adapter, result.file_hash, result.parser_name, result.user_id):
        return {"status": "skipped", "applied": 0,
                "error": "ficheiro já importado (hash em import_log)"}

    applied = 0
    try:
        for row in result.rows:
            if not adapter.table_exists(row.table):
                result.warnings.append("Tabela inexistente, linha ignorada: %s" % row.table)
                continue
            existing = adapter.columns(row.table)
            values = {k: v for k, v in row.values.items() if k in existing}
            conflict = {k: values[k] for k in row.conflict_keys
                        if k in values and k in existing}
            adapter.delete_where(row.table, conflict)
            adapter.insert(row.table, values)
            applied += 1
        _log_import(adapter, result, status="success", applied=applied)
        conn.commit()
        return {"status": "success", "applied": applied,
                "skipped": result.rows_skipped, "warnings": result.warnings}
    except Exception as exc:  # ROLLBACK total
        conn.rollback()
        try:
            result.errors.append(str(exc))
            _log_import(adapter, result, status="failed")
            conn.commit()
        except Exception:
            pass
        return {"status": "failed", "applied": 0, "error": str(exc)}


def _log_import(adapter: DBAdapter, result: IngestResult,
                status: str, applied: int = 0):
    """Escreve a auditoria em import_log (só as colunas que existirem)."""
    if not adapter.table_exists("import_log"):
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
    existing = adapter.columns("import_log")
    values = {k: v for k, v in candidate.items() if k in existing}
    if values:
        adapter.insert("import_log", values)
