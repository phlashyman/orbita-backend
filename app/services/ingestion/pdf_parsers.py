# -*- coding: utf-8 -*-
"""
orbita_ingest.pdf_parsers
=========================
Parsers para os ficheiros PDF:
  - standard_carteira          (A Minha Carteira.pdf)         -> portfolio_snapshots
  - pdf_ficha_tecnica          (Ficha Técnica Acções/Títulos) -> bond_master
  - bodiva_boletim_oficial     (Boletim Diário .pdf)          -> market_snapshots + 4 tabelas
  - bodiva_relatorio_mensal    (Relatório Mensal .pdf)        -> bodiva_monthly_aggregates
  - bodiva_relatorio_trimestral(Relatório Trimestral .pdf)    -> agregados trimestrais

Biblioteca: pdfplumber (texto + extract_tables). PyPDF2/pypdf NÃO é adequado
para tabelas - usa-se só como fallback de contagem de páginas.

Os parsers de PDF são os mais sensíveis ao layout. Estão escritos de forma
DEFENSIVA: cada secção corre em try/except e acumula avisos em vez de rebentar
o upload. Validar contra os ficheiros reais antes de confiar nos agregados.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, List, Optional

import pdfplumber

from .common import (
    DBRow, IngestResult, classify_isin, map_typology,
    normalize_product_to_ticker, normalize_ticker,
    parse_pt_date, parse_pt_month, to_int, to_number,
)

# regexes partilhados
_ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
_TICKER_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{4,8})\b")
_DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")
_PT_FULL_DATE = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.IGNORECASE)
_NUM_TOKEN_RE = re.compile(r"^[\d.,]+$")


def _all_text(pdf) -> str:
    parts = []
    for p in pdf.pages:
        parts.append(p.extract_text() or "")
    return "\n".join(parts)


def _grab(text: str, *patterns: str) -> Optional[str]:
    """Procura o 1.º grupo de captura que casar com qualquer um dos padrões."""
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


# =========================================================================== #
# 1. STANDARD CARTEIRA  ->  portfolio_snapshots (FUND)
# =========================================================================== #
# O PDF "A Minha Carteira" é gerado com colunas (PRODUTO, QUANTIDADE, PREÇO,
# VALOR ACTUAL, GANHOS NÃO REALIZADOS) mas a extração de texto do pdfplumber
# devolve as linhas fora de ordem (a célula de VALOR ACTUAL/GANHOS de uma
# linha aparece, por vezes, antes da linha do PRODUTO). Por isso recorremos a
# extract_words() + clustering por posição vertical (top) e horizontal (x0)
# para reconstruir cada linha da tabela.
_STD_COL_RANGES = {
    "quantidade": (250, 305),
    "preco": (305, 400),
    "valor_actual": (400, 465),
    "ganhos": (465, 1000),
}
_STD_ROW_TOLERANCE = 16  # px - palavras com 'top' dentro desta janela pertencem à mesma linha


def _cluster_rows(words: List[dict]) -> List[List[dict]]:
    """Agrupa palavras em 'linhas' por proximidade vertical (coordenada top)."""
    rows: List[List[dict]] = []
    cluster: List[dict] = []
    cluster_top: Optional[float] = None
    for w in sorted(words, key=lambda w: w["top"]):
        if cluster_top is None or (w["top"] - cluster_top) <= _STD_ROW_TOLERANCE:
            cluster.append(w)
            if cluster_top is None:
                cluster_top = w["top"]
        else:
            rows.append(cluster)
            cluster = [w]
            cluster_top = w["top"]
    if cluster:
        rows.append(cluster)
    return rows


def _first_number_in_range(row: List[dict], lo: float, hi: float) -> Optional[float]:
    for w in row:
        if lo <= w["x0"] < hi and _NUM_TOKEN_RE.match(w["text"]):
            return to_number(w["text"])
    return None


def parse_standard_carteira(
    path: str,
    file_hash: str,
    user_id: Optional[int],
    portfolio_id: Optional[int] = None,
    snapshot_date: Optional[date] = None,
) -> IngestResult:
    started = datetime.now()
    res = IngestResult("standard_carteira", file_hash, snapshot_date or date.today(), user_id)
    if snapshot_date is None:
        res.warnings.append("PDF sem data fiável; usado date.today().")
    sdate = (snapshot_date or date.today()).isoformat()

    holdings = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for row in _cluster_rows(page.extract_words()):
                produto_words = sorted(
                    (w for w in row if w["x0"] < _STD_COL_RANGES["quantidade"][0]),
                    key=lambda w: w["x0"],
                )
                if not produto_words:
                    continue
                product = " ".join(w["text"] for w in produto_words)
                if "STANDARD" not in product.upper():
                    continue

                q = _first_number_in_range(row, *_STD_COL_RANGES["quantidade"])
                price = _first_number_in_range(row, *_STD_COL_RANGES["preco"])
                cur_value = _first_number_in_range(row, *_STD_COL_RANGES["valor_actual"])
                gain = _first_number_in_range(row, *_STD_COL_RANGES["ganhos"])

                ticker = normalize_product_to_ticker(product)
                acq = (cur_value - gain) if (cur_value is not None and gain is not None) else None
                gain_pct = (round(100.0 * gain / acq, 4)) if (gain is not None and acq) else None
                holdings.append({
                    "user_id": user_id, "portfolio_id": portfolio_id,
                    "broker": "STANDARD_GESTAO_ACTIVOS", "ticker": ticker,
                    "title": product.strip(), "market": "STANDARD",
                    "instrument_class": "FUND", "snapshot_date": sdate,
                    "quantity_total": q, "quantity_available": q,
                    "par_value_unit": None, "quote_price": price,
                    "currency": "AOA", "current_value": cur_value,
                    "acquisition_value": acq, "current_value_aoa": cur_value,
                    "unrealized_pnl": gain, "unrealized_pnl_pct": gain_pct,
                    "daily_variation_aoa": None,
                    "daily_variation_pct": None, "weight_pct": None,
                })

    total = sum((h["current_value_aoa"] or 0.0) for h in holdings)
    rows: List[DBRow] = []
    for h in holdings:
        if total > 0 and h["current_value_aoa"] is not None:
            h["weight_pct"] = round(100.0 * h["current_value_aoa"] / total, 4)
        rows.append(DBRow("portfolio_snapshots", h,
                          conflict_keys=["broker", "ticker", "snapshot_date"]))
        rows.append(DBRow("bond_master",
                          {"ticker": h["ticker"], "title": h["title"],
                           "instrument_class": "FUND", "currency": "AOA",
                           "data_source": "standard_carteira"},
                          conflict_keys=["ticker"]))

    res.rows = rows
    res.rows_processed = len(holdings)
    res.summary = "%d UPs Standard, total %.0f AOA" % (len(holdings), total)
    if not holdings:
        res.errors.append("Nenhuma UP extraída (regex Standard não casou - verificar layout).")
    res.duration_seconds = (datetime.now() - started).total_seconds()
    return res


# =========================================================================== #
# 2. FICHA TÉCNICA (Acções / Títulos Públicos)  ->  bond_master
# =========================================================================== #
def parse_ficha_tecnica(path: str, file_hash: str, user_id: Optional[int] = None) -> IngestResult:
    started = datetime.now()
    res = IngestResult("pdf_ficha_tecnica", file_hash, date.today(), user_id)

    with pdfplumber.open(path) as pdf:
        text = _all_text(pdf)
    up = text.upper()

    isin = _grab(text, r"ISIN[:\s]+([A-Z]{2}[A-Z0-9]{9}\d)") or (
        _ISIN_RE.search(text).group(1) if _ISIN_RE.search(text) else None)
    ticker = _grab(text,
                   r"C[óo]digo de Negocia[çc][ãa]o[:\s]+([A-Z0-9]{4,12})",
                   r"C[óo]digo[:\s]+([A-Z0-9]{4,12})")
    if not ticker and isin:
        ticker = isin            # fallback
    ticker = normalize_ticker(ticker)

    # decidir tipo: acção vs título público
    is_equity = ("ACÇÃO" in up or "ACÇÕES" in up or "ACÇAO" in up
                 or "AÇÃO" in up or "AÇÕES" in up or "SHARE" in up)
    is_treasury = ("OBRIGA" in up or "BILHETE" in up or "TESOURO" in up
                   or "OT-" in up or "CUPÃO" in up or "CUPAO" in up
                   or classify_isin(isin) == "BOND_GOV")

    if is_equity and not is_treasury:
        instrument_class = "EQUITY"
    elif is_treasury:
        # refinar com a tipologia textual, se existir
        typ = _grab(text, r"Tipologia[:\s]+([A-Za-z\-]+)")
        instrument_class = map_typology(typ) if typ else "BOND_GOV"
    else:
        instrument_class = map_typology(_grab(text, r"Tipologia[:\s]+([A-Za-z\-]+)") or "")

    issuer = _grab(text, r"Emitente[:\s]+([^\n]+)")
    currency = (_grab(text, r"Moeda[:\s]+([A-Z]{3})") or "AOA").upper()
    par_value = to_number(_grab(text, r"Valor Nominal[^:]*[:\s]+([\d.,]+)"))
    coupon = to_number(_grab(text, r"(?:Taxa de )?Cup[ãa]o[:\s]+([\d.,]+)"))
    freq_txt = _grab(text, r"Frequ[êe]ncia[:\s]+([A-Za-zçãéê]+)")
    issue_date = parse_pt_date(_grab(text, r"Data de Emiss[ãa]o[:\s]+(\d{2}/\d{2}/\d{4})"))
    maturity = parse_pt_date(_grab(text, r"Data de (?:Vencimento|Maturidade)[:\s]+(\d{2}/\d{2}/\d{4})"))
    admission = parse_pt_date(_grab(text, r"Data de Admiss[ãa]o[:\s]+(\d{2}/\d{2}/\d{4})"))
    qty_issued = to_int(_grab(text, r"Quantidade[^:]*[:\s]+([\d.,\s]+)"))

    freq_map = {"anual": 1, "semestral": 2, "trimestral": 4, "mensal": 12}
    freq_n = freq_map.get((freq_txt or "").strip().lower()) if freq_txt else None

    if not ticker and not isin:
        res.errors.append("Ficha técnica sem ISIN nem código de negociação legíveis.")
        res.duration_seconds = (datetime.now() - started).total_seconds()
        return res

    rec = {
        "ticker": ticker or isin, "isin": isin, "title": issuer or ticker,
        "issuer": issuer, "instrument_class": instrument_class,
        "currency": currency, "par_value": par_value, "coupon_rate": coupon,
        "frequency": freq_txt, "frequency_n": freq_n,
        "issue_date": issue_date.isoformat() if issue_date else None,
        "maturity_date": maturity.isoformat() if maturity else None,
        "admission_date": admission.isoformat() if admission else None,
        "qty_issued": qty_issued, "bodiva_admitted": 1,
        "data_source": "ficha_tecnica",
    }
    res.rows = [DBRow("bond_master", rec, conflict_keys=["ticker"])]
    res.rows_processed = 1
    kind = "acção" if instrument_class == "EQUITY" else "título público"
    res.summary = "Ficha técnica (%s): %s / %s" % (kind, rec["ticker"], isin or "-")
    res.duration_seconds = (datetime.now() - started).total_seconds()
    return res


# =========================================================================== #
# 3. BOLETIM DIÁRIO BODIVA  ->  market_snapshots + agregados
# =========================================================================== #
# linha de negócio de obrigação: TICKER TIPOLOGIA DD/MM/AAAA DD/MM/AAAA <resto>
_TRADE_LINE = re.compile(
    r"^([A-Z0-9]{6,10})\s+(OT-\w+|BT|OP|U[PB])\s+"
    r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.+)$"
)
# curva de rendimentos: 3M 13,84% 13,79% ...
_CURVE_LINE = re.compile(
    r"^(\d+\s*[MYAD]|\d+\s*(?:mes|meses|ano|anos))\s+([\d.,]+)%\s+([\d.,]+)%", re.IGNORECASE)
# evento de rendimento: Nº Emitente Instrumento Moeda CodNeg ISIN Tipo
_INCOME_LINE = re.compile(
    r"^\s*\d+\s+([A-Za-z]+)\s+([A-Za-z\-]+)\s+([A-Z]{3})\s+([A-Z0-9]{6,10})\s+"
    r"([A-Z]{2}[A-Z0-9]{9}\d)\s+(.+)$")


def _cell(v: Any) -> str:
    """Normalise a table cell to a stripped string."""
    return str(v).strip() if v is not None else ""


def _is_header(row: List[Any], keywords: List[str]) -> bool:
    """Return True if any keyword appears in any cell of this row."""
    joined = " ".join(_cell(c) for c in row).lower()
    return any(k.lower() in joined for k in keywords)


def parse_bodiva_boletim(path: str, file_hash: str, user_id: Optional[int] = None) -> IngestResult:
    """Parse Boletim Diário BODIVA using table extraction (not text regex).

    The PDF stores all trading/event data inside PDF tables, not as plain text
    lines.  We iterate every page, extract tables, identify them by their header
    row and collect:
      - OTC transmissions  → market_snapshots  (price = valor unitário)
      - Leilão (auction)   → bond_master + market_snapshots (primary market)
      - Income events      → income_events (coupons, amortisations …)
    """
    started = datetime.now()
    res = IngestResult("bodiva_boletim_oficial", file_hash, None, user_id)
    rows: List[DBRow] = []

    with pdfplumber.open(path) as pdf:
        text = _all_text(pdf)
        all_pages_tables = [page.extract_tables() for page in pdf.pages]

    # --- date & boletim number from text ---
    snapshot_date = None
    m = _PT_FULL_DATE.search(text)
    if m:
        d, mon, y = m.groups()
        mn = parse_pt_month(mon)
        if mn:
            snapshot_date = date(int(y), mn, int(d))
    if snapshot_date is None:
        fm = re.search(r"boletimdiario(\d{4})(\d{2})(\d{2})", path, re.IGNORECASE)
        if fm:
            y, mo, d = fm.groups()
            snapshot_date = date(int(y), int(mo), int(d))
    if snapshot_date is None:
        snapshot_date = date.today()
        res.warnings.append("Data do boletim não detectada; usado date.today().")
    res.snapshot_date = snapshot_date
    sdate = snapshot_date.isoformat()

    boletim_n = _grab(text, r"Boletim\s+de\s+Mercado\s+N[^\s]\s*([\d\s]+)")

    n_otc = 0
    n_auction = 0
    n_income = 0

    for page_tables in all_pages_tables:
        for table in page_tables:
            if not table or len(table) < 2:
                continue
            header = table[0]

            # ── OTC transmissions: Código de VM | Quantidade | Valor Unitário | Data
            if _is_header(header, ["Código de VM", "Valor Unitário"]):
                for row in table[1:]:
                    if len(row) < 3:
                        continue
                    ticker = normalize_ticker(_cell(row[0]))
                    qty = to_number(_cell(row[1]))
                    price = to_number(_cell(row[2]))
                    raw_date = _cell(row[3]) if len(row) > 3 else sdate
                    tx_date = raw_date if re.match(r"\d{2}/\d{2}/\d{4}", raw_date) else sdate
                    if not ticker or ticker.upper() in ("", "CÓDIGO DE VM"):
                        continue
                    if price is None and qty is None:
                        continue
                    rows.append(DBRow("market_snapshots", {
                        "ticker": ticker, "snapshot_date": sdate,
                        "snapshot_time": "23:59:59", "source": "bodiva_boletim_otc",
                        "instrument_class": None, "price": price,
                        "currency": "AOA", "var_daily_pct": None,
                        "best_bid": None, "best_ask": None,
                        "n_trades_day": None, "volume_qty": qty,
                        "volume_aoa": None, "volume_trades": None,
                        "tx_date": tx_date,
                    }, conflict_keys=["ticker", "snapshot_date", "snapshot_time", "source"]))
                    n_otc += 1

            # ── Income events: Nº | Emitente | Instrumento | Moeda | Código | ISIN | Tipo
            elif _is_header(header, ["Tipo de Evento", "ISIN", "Emitente"]):
                for row in table[1:]:
                    if len(row) < 6:
                        continue
                    # columns: Nº, Emitente, Instrumento, Moeda, CódNeg, ISIN, TipoEvento
                    cells = [_cell(c) for c in row]
                    # find ISIN column (matches AO... pattern)
                    isin = next((c for c in cells if re.match(r"[A-Z]{2}[A-Z0-9]{9}\d$", c)), None)
                    cod = next((c for c in cells if re.match(r"[A-Z0-9]{6,10}$", c) and c != isin and c not in ("AOA", "USD", "EUR", "UGD")), None)
                    moeda = next((c for c in cells if c in ("AOA", "USD", "EUR", "GBP")), None)
                    evt = cells[-1] if cells else None
                    emitente = cells[1] if len(cells) > 1 else None
                    if not cod and not isin:
                        continue
                    rows.append(DBRow("income_events", {
                        "snapshot_date": sdate,
                        "ticker": normalize_ticker(cod) if cod else None,
                        "isin": isin, "issuer": emitente, "currency": moeda,
                        "event_type": evt,
                    }, conflict_keys=["snapshot_date", "ticker", "event_type"]))
                    n_income += 1

            # ── Auction / Leilão: instrument | tenor | maturity | coupon | yield | price | offered | accepted
            elif _is_header(header, ["Prazo", "Taxa de Juro", "Montante"]):
                for row in table[1:]:
                    cells = [_cell(c) for c in row]
                    if not any(cells):
                        continue
                    instr_type = cells[0] if cells else None
                    if not instr_type or instr_type.lower() in ("total", ""):
                        continue
                    coupon = to_number(cells[3]) if len(cells) > 3 else None
                    yield_val = to_number(cells[4]) if len(cells) > 4 else None
                    price = to_number(cells[5]) if len(cells) > 5 else None
                    rows.append(DBRow("market_snapshots", {
                        "ticker": instr_type, "snapshot_date": sdate,
                        "snapshot_time": "23:59:59", "source": "bodiva_leilao",
                        "instrument_class": map_typology(instr_type),
                        "price": price, "currency": "AOA",
                        "var_daily_pct": None, "best_bid": None, "best_ask": None,
                        "n_trades_day": None, "volume_qty": None,
                        "volume_aoa": None, "volume_trades": None,
                    }, conflict_keys=["ticker", "snapshot_date", "snapshot_time", "source"]))
                    n_auction += 1

    res.rows = rows
    res.rows_processed = n_otc + n_auction + n_income
    res.summary = (
        "Boletim %s @ %s — %d transmissões OTC, %d leilões, %d eventos de rendimento"
        % (boletim_n or "?", snapshot_date.strftime("%d/%m/%Y"), n_otc, n_auction, n_income)
    )
    if res.rows_processed == 0:
        res.warnings.append("Nenhum dado extraído — sessão sem transacções ou layout não reconhecido.")
    res.duration_seconds = (datetime.now() - started).total_seconds()
    return res


# =========================================================================== #
# 4/5. RELATÓRIO MENSAL / TRIMESTRAL  (best-effort, validar com ficheiro real)
# =========================================================================== #
def parse_bodiva_relatorio(path: str, file_hash: str, user_id: Optional[int] = None,
                           periodicity: str = "mensal") -> IngestResult:
    started = datetime.now()
    name = "bodiva_relatorio_%s" % periodicity
    res = IngestResult(name, file_hash, None, user_id)
    rows: List[DBRow] = []

    with pdfplumber.open(path) as pdf:
        text = _all_text(pdf)
        tables = []
        for p in pdf.pages:
            try:
                tables.extend(p.extract_tables() or [])
            except Exception:
                continue

    year = None
    month = None
    quarter = None
    fm = re.search(r"relatoriomensal(\d{4})(\d{2})", path, re.IGNORECASE)
    if fm:
        year, month = int(fm.group(1)), int(fm.group(2))
    pm = _PT_FULL_DATE.search(text)
    if pm and year is None:
        year = int(pm.group(3))
        month = parse_pt_month(pm.group(2))
    qm = re.search(r"([IVX]+)\s*Trimestre", text)
    if qm:
        quarter = {"I": 1, "II": 2, "III": 3, "IV": 4}.get(qm.group(1).upper())
    ym = re.search(r"(\d{4})", path)
    if year is None and ym:
        year = int(ym.group(1))
    res.snapshot_date = date(year or date.today().year,
                             month or (quarter * 3 if quarter else 1) or 1, 1)

    target_table = "bodiva_monthly_aggregates" if periodicity == "mensal" else "bodiva_quarterly_aggregates"
    # captura genérica: cada linha de tabela com um ticker + números agregados
    for tbl in tables:
        for raw in tbl:
            if not raw:
                continue
            cells = [(c or "").strip() for c in raw]
            tm = _TICKER_RE.match(cells[0]) if cells else None
            if not tm:
                continue
            nums = [to_number(c) for c in cells[1:] if to_number(c) is not None]
            if not nums:
                continue
            rows.append(DBRow(target_table, {
                "year": year, "month": month, "quarter": quarter,
                "ticker": normalize_ticker(cells[0]),
                "montante": nums[0] if len(nums) > 0 else None,
                "volume": nums[1] if len(nums) > 1 else None,
                "trades": to_int(nums[2]) if len(nums) > 2 else None,
                "raw_json": str(cells),
            }, conflict_keys=["year", "month", "quarter", "ticker"]))

    res.rows = rows
    res.rows_processed = len(rows)
    res.summary = "Relatório %s %s - %d linhas agregadas (VALIDAR mapeamento)" % (
        periodicity, year or "?", len(rows))
    res.warnings.append(
        "Captura genérica de tabelas: confirmar colunas/ordem contra o PDF real "
        "antes de usar os agregados em produção.")
    res.duration_seconds = (datetime.now() - started).total_seconds()
    return res
