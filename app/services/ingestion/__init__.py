# -*- coding: utf-8 -*-
"""
orbita_ingest - Pacote de ingestao de ficheiros broker/BODIVA para Orbita.

Parsers suportados:
  - aurea_carteira          (Carteira Aurea .xlsx)         -> portfolio_snapshots
  - aurea_destaques         (Bolsa-Destaques .xlsx)        -> market_snapshots
  - ordens_disponiveis      (Ordens_Disponiveis .xlsx)     -> order_book_snapshots
  - bodiva_resumo           (Resumo_dos_Mercados .xlsx)    -> market_snapshots
  - standard_carteira       (A Minha Carteira .pdf)        -> portfolio_snapshots
  - ficha_tecnica           (Ficha Tecnica .pdf)           -> bond_master
  - bodiva_boletim          (Boletim Diario .pdf)          -> market_snapshots + yield_curve + income_events
  - bodiva_relatorio_mensal (Relatorio Mensal .pdf)        -> bodiva_monthly_aggregates
  - bodiva_relatorio_trimestral (Relatorio Trimestral .pdf) -> bodiva_quarterly_aggregates
"""

from .common import (
    DBRow,
    IngestResult,
    ParserConfig,
    classify_isin,
    infer_class_from_aurea,
    map_typology,
    normalize_product_to_ticker,
    normalize_ticker,
    parse_iso_datetime,
    parse_pt_date,
    parse_pt_month,
    sha256_of_bytes,
    sha256_of_file,
    timestamp_from_filename,
    to_int,
    to_number,
)
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
from .service import (
    ForbiddenFile,
    UndetectedFile,
    detect_only,
    ingest_file,
    parse_file,
)

__all__ = [
    # Common
    "DBRow",
    "IngestResult",
    "ParserConfig",
    "to_number",
    "to_int",
    "parse_pt_date",
    "parse_iso_datetime",
    "parse_pt_month",
    "timestamp_from_filename",
    "map_typology",
    "infer_class_from_aurea",
    "normalize_ticker",
    "normalize_product_to_ticker",
    "classify_isin",
    "sha256_of_bytes",
    "sha256_of_file",
    # Detect
    "detect_file",
    # Parsers Excel
    "parse_aurea_carteira",
    "parse_aurea_destaques",
    "parse_bodiva_resumo",
    "parse_ordens_disponiveis",
    # Parsers PDF
    "parse_standard_carteira",
    "parse_ficha_tecnica",
    "parse_bodiva_boletim",
    "parse_bodiva_relatorio",
    # Service
    "parse_file",
    "detect_only",
    "ingest_file",
    "ForbiddenFile",
    "UndetectedFile",
]
