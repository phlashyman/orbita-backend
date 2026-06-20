# -*- coding: utf-8 -*-
"""
orbita_ingest.common
====================
Utilitários partilhados por todos os parsers do pipeline de ingestão Órbita.

Princípios (não-negociáveis, herdados do PROJECT_MASTER §8.1):
  - Idempotência: o mesmo ficheiro N vezes => mesmo estado final na DB.
  - Atomicidade: cada upload corre numa transacção; falha => ROLLBACK total.
  - Vigência temporal: snapshot_date vem SEMPRE do conteúdo/nome do ficheiro,
    nunca do momento do upload.
  - Tolerância: parsers toleram encoding, separadores decimais e espaços extra,
    mas são estritos em tickers e montantes.

Compatível com Python 3.9+ (sem sintaxe 3.10+).
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# 1. Conversão numérica tolerante (PT-PT e EN)
# --------------------------------------------------------------------------- #
_NULL_TOKENS = {"", "NA", "N/A", "N.A.", "-", "-", "-", "NULL", "NONE"}


def to_number(value: Any) -> Optional[float]:
    """
    Converte para float tolerando os formatos que aparecem nos ficheiros BODIVA:
        "262.349,56"        -> 262349.56   (PT: ponto=milhar, vírgula=decimal)
        "1 984 060 938,92"  -> 1984060938.92 (espaço=milhar)
        "4,241780"          -> 4.24178      (vírgula decimal pura)
        "103.99" / 104000.0 -> 103.99 / 104000.0 (ponto decimal / número Excel)
        "NA" / "" / None    -> None
        "16,75%" / "104000 AOA" -> 16.75 / 104000.0
    Regra do separador: se '.' e ',' coexistem assume-se formato PT
    (ponto=milhar, vírgula=decimal). Se só houver ',', a vírgula é decimal.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s.upper() in _NULL_TOKENS:
        return None
    # remover ruído de moeda/percentagem e espaços de milhar (incl. NBSP)
    s = s.replace("AOA", "").replace("Kz", "").replace("%", "")
    s = s.replace("\xa0", "").replace(" ", "").strip()
    if s.upper() in _NULL_TOKENS:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")      # PT: 262.349,56
    elif "," in s:
        s = s.replace(",", ".")                        # vírgula decimal
    try:
        return float(s)
    except ValueError:
        return None


def to_int(value: Any) -> Optional[int]:
    n = to_number(value)
    return int(round(n)) if n is not None else None


# --------------------------------------------------------------------------- #
# 2. Datas
# --------------------------------------------------------------------------- #
_PT_MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def parse_pt_month(name: str) -> Optional[int]:
    return _PT_MONTHS.get((name or "").strip().lower())


def parse_pt_date(value: Any) -> Optional[date]:
    """Aceita DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, objectos date/datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if s.upper() in _NULL_TOKENS:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    """
    Aceita timestamps ISO mesmo mal formados, ex.: '2026-05-14T10:38:4'
    (segundos com 1 dígito). Devolve datetime ou None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    s = str(value).strip()
    if s.upper() in _NULL_TOKENS:
        return None
    m = re.match(
        r"(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?", s
    )
    if m:
        y, mo, d, h, mi, sec = m.groups()
        return datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec or 0))
    only_date = parse_pt_date(s)
    return datetime(only_date.year, only_date.month, only_date.day) if only_date else None


# regex partilhado: 14-05-2026_10-37-21  (Resumo_dos_Mercados / Ordens_Disponiveis)
_FNAME_TS = re.compile(r"(\d{2})-(\d{2})-(\d{4})_(\d{2})-(\d{2})-(\d{2})")


def timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Extrai datetime do nome do ficheiro (formato DD-MM-YYYY_HH-MM-SS)."""
    m = _FNAME_TS.search(os.path.basename(filename or ""))
    if not m:
        return None
    d, mo, y, h, mi, sec = m.groups()
    return datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec))


# --------------------------------------------------------------------------- #
# 3. Classificação de instrumentos (typology -> instrument_class)
# --------------------------------------------------------------------------- #
def map_typology(typology: Optional[str]) -> str:
    """Mapeia a 'Tipologia do Título' BODIVA para a instrument_class interna."""
    t = (typology or "").strip().upper()
    if not t:
        return "UNKNOWN"
    if "ACÇ" in t or "ACC" in t or "AÇ" in t or "ACÕ" in t or t.startswith("ACT"):
        return "EQUITY"
    if t in ("OT-NR", "OT-TX", "OT-ME", "OT-TV") or t.startswith("OT"):
        return "BOND_GOV"
    if t == "BT" or "BILHETE" in t:
        return "TBILL"
    if "PRIVAD" in t or t == "OP" or "CORPOR" in t:
        return "BOND_CORP"
    if "PARTICIP" in t or t == "UP" or "FEIVMA" in t or "FUND" in t:
        return "UP"
    if "OBRIG" in t:
        return "BOND_GOV"  # default conservador; refinar com o emitente
    return "UNKNOWN"


def infer_class_from_aurea(market: Optional[str], title: Optional[str]) -> str:
    """
    Carteira Aurea: infere a classe a partir das colunas 'Mercado' e 'Título'.
      "BODIVA AÇÕES"        -> EQUITY
      "BODIVA OBRIGAÇÕES" + título "UGD"/"OT" -> BOND_GOV
      "BODIVA OBRIGAÇÕES" + título corporativo (BAI/OD/...) -> BOND_CORP
    """
    m = (market or "").strip().upper()
    t = (title or "").strip().upper()
    if "AÇ" in m or "ACÇ" in m or "ACC" in m:
        return "EQUITY"
    if "OBRIG" in m or "BODIVA" in m:
        if t.startswith("UGD") or "OTNR" in t or "OT-NR" in t or t.startswith("OT") or t.startswith("OJ") or t.startswith("OI") or t.startswith("OL") or t.startswith("ON") or t.startswith("OO"):
            return "BOND_GOV"
        # emitentes corporativos conhecidos
        if t.startswith("OD") or t.startswith("BAI") or "CORP" in t:
            return "BOND_CORP"
        return "BOND_GOV"
    if "FEIVMA" in t or "STANDARD" in t:
        return "UP"
    return "UNKNOWN"


def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_product_to_ticker(product: str) -> str:
    """Standard FEIVMA: 'STANDARD TESOURARIA FEIVMA' -> 'STDR_TES_FEIVMA'."""
    mapping = {
        "STANDARD TESOURARIA FEIVMA": "STDR_TES_FEIVMA",
        "STANDARD OBRIGAÇÕES FEIVMA": "STDR_OBR_FEIVMA",
        "STANDARD OBRIGACOES FEIVMA": "STDR_OBR_FEIVMA",
        "STANDARD VALOR-FEIVMA": "STDR_VAL_FEIVMA",
        "STANDARD VALOR FEIVMA": "STDR_VAL_FEIVMA",
    }
    key = (product or "").strip().upper()
    return mapping.get(key, key.replace(" ", "_").replace("-", "_"))


# --------------------------------------------------------------------------- #
# 4. ISIN -> tipo de ficha técnica (acção vs título público)
# --------------------------------------------------------------------------- #
def classify_isin(isin: str) -> str:
    """
    Heurística para fichas técnicas. ISIN angolano: 'AO' + 9 chars + dígito.
      AOUGDOIF25A1 -> emitente UGD (Unidade de Gestão da Dívida) => BOND_GOV
      AOBDVAAAAA05 -> emitente corporativo/acção                 => EQUITY/CORP
    NB: confirmar a estrutura exacta do ISIN na ficha técnica; é heurística.
    """
    i = (isin or "").strip().upper()
    if not i.startswith("AO") or len(i) < 6:
        return "UNKNOWN"
    issuer = i[2:5]               # mnemónica do emitente
    if issuer == "UGD":
        return "BOND_GOV"
    return "EQUITY_OR_CORP"


# --------------------------------------------------------------------------- #
# 5. Hash de ficheiro (idempotência)
# --------------------------------------------------------------------------- #
def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# 6. Estruturas de dados normalizadas (saída dos parsers)
# --------------------------------------------------------------------------- #
@dataclass
class DBRow:
    """
    Uma operação a aplicar à DB. O parser NUNCA escreve directamente:
    devolve DBRows e a camada de persistência aplica-as numa transacção.
        table        : nome da tabela alvo
        values       : dict coluna -> valor
        conflict_keys: colunas que formam a chave natural (para upsert idempotente)
    """
    table: str
    values: Dict[str, Any]
    conflict_keys: List[str] = field(default_factory=list)


@dataclass
class IngestResult:
    """Resultado padronizado de qualquer parser (PROJECT_MASTER §8.2.3)."""
    parser_name: str
    file_hash: str
    snapshot_date: Optional[date]
    user_id: Optional[int]

    rows: List[DBRow] = field(default_factory=list)

    summary: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    rows_processed: int = 0
    rows_skipped: int = 0
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ParserConfig:
    """Limiares de tolerância por parser (PROJECT_MASTER §8.9.2)."""
    name: str
    max_row_errors_pct: float = 5.0
    require_at_least_n_rows: int = 1
