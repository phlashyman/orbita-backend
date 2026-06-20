"""
Broker File Parser — extracts portfolio positions from broker statement files.

Supports:
    - CSV  (comma, semicolon, or tab delimited)
    - XLSX (Excel via openpyxl)
    - TXT  (plain text / TSV)

Handles Angolan broker formats (BFA, BCI, etc.) with column headers in
Portuguese and/or English.  Gracefully degrades on encoding issues and
unrecognised schemas — returns an empty list instead of raising.
"""
import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column header aliases (Portuguese + English)
# ---------------------------------------------------------------------------

# Helpers to build accent-aware alias sets

def _unaccent(s: str) -> str:
    """Replace Portuguese accented characters with ASCII equivalents."""
    return (
        s.replace("a", "a").replace("a", "a")
         .replace("e", "e").replace("e", "e")
         .replace("i", "i")
         .replace("o", "o").replace("o", "o")
         .replace("u", "u")
         .replace("c", "c")
         .replace("a", "a").replace("a", "a").replace("a", "a").replace("a", "a")
         .replace("e", "e").replace("e", "e").replace("e", "e").replace("e", "e")
         .replace("i", "i").replace("i", "i")
         .replace("o", "o").replace("o", "o").replace("o", "o").replace("o", "o")
         .replace("u", "u").replace("u", "u")
         .replace("c", "c").replace("c", "c")
    )

# -- Base alias sets (ASCII) --
#   Notes:
#   * "titulo" maps to NAME (the human-readable title), not TICKER.
#   * "cotacao" = quotation/market price → PRICE.
#   * "mercado" = market column like "BODIVA OBRIGACOES" → TYPE.
#   * "_quantidade_" produced by "-Quantidade-" (hyphen-wrapped headers).
#   * "_valor_" produced by "-Valor-" (hyphen-wrapped headers).
#   * "_valor_aoa_" produced by "-Valor (AOA)-" (hyphen-wrapped headers).

_TICKER_BASE: set[str] = {
    "ticker", "isin", "code", "codigo", "ativo", "symbol", "security",
    "security_id", "instrument", "instrumento",
    "referencia", "ref", "stock", "bond", "obrigacao",
}
_NAME_BASE: set[str] = {
    "name", "nome", "descricao", "description", "desc", "security_name",
    "denominacao", "denominacao_social", "emitente", "issuer",
    "instrument_name", "ativo_desc", "titulo_desc",
    "titulo",           # "Título" → name (human-readable title)
}
_QUANTITY_BASE: set[str] = {
    "quantity", "quantidade", "qtd", "units", "unidades", "amount",
    "nominal", "nominal_amount", "principal", "qty", "position",
    "posicao", "saldo", "saldo_nominal",
    "_quantidade_",     # produced by "-Quantidade-"
}
_PRICE_BASE: set[str] = {
    "price", "preco", "unit_price", "preco_unitario", "avg_price",
    "preco_medio", "avg", "average", "cost", "custo", "unit_cost",
    "preco_compra", "buy_price", "market_price", "preco_mercado",
    "preco_atual", "current_price", "pu", "preco_unit",
    "cotacao",          # "Cotação" → price
    "cotacao_mercado",  # market quotation
}
_VALUE_BASE: set[str] = {
    "value", "valor", "total", "total_value", "valor_total",
    "market_value", "valor_mercado", "position_value",
    "saldo_valor", "amount", "montante", "net_value", "book_value",
    "valor_contabilistico", "valor_nominal", "nominal_value",
    "_valor_",           # produced by "-Valor-"
    "_valor_aoa_",       # produced by "-Valor (AOA)-"
    "_valor_nominal_",   # produced by "-Valor nominal-"
}
_TYPE_BASE: set[str] = {
    "type", "tipo", "instrument_type", "tipo_instrumento", "asset_type",
    "tipo_ativo", "security_type", "category", "categoria",
    "asset_class", "classe", "classe_ativo",
    "mercado",           # "Mercado" like "BODIVA OBRIGACOES"
}

# -- Final alias sets include both accented and unaccented forms --
_TICKER_ALIASES: set[str] = _TICKER_BASE | {_unaccent(a) for a in _TICKER_BASE}
_NAME_ALIASES: set[str] = _NAME_BASE | {_unaccent(a) for a in _NAME_BASE}
_QUANTITY_ALIASES: set[str] = _QUANTITY_BASE | {_unaccent(a) for a in _QUANTITY_BASE}
_PRICE_ALIASES: set[str] = _PRICE_BASE | {_unaccent(a) for a in _PRICE_BASE}
_VALUE_ALIASES: set[str] = _VALUE_BASE | {_unaccent(a) for a in _VALUE_BASE}
_TYPE_ALIASES: set[str] = _TYPE_BASE | {_unaccent(a) for a in _TYPE_BASE}


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------

class BrokerPositionExtracted:
    """
    A single position extracted from a broker file.

    Attributes:
        ticker: Instrument ticker, ISIN, or internal code.
        name: Human-readable instrument name.
        quantity: Number of units held (int).
        price: Unit price (Decimal).
        value: Total position value (Decimal).
        instrument_type: Optional instrument classification.
        raw_data: The full raw row for debugging / manual mapping.
    """

    def __init__(
        self,
        ticker: Optional[str] = None,
        name: Optional[str] = None,
        quantity: Optional[int] = None,
        price: Optional[Decimal] = None,
        value: Optional[Decimal] = None,
        instrument_type: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.ticker = ticker
        self.name = name
        self.quantity = quantity
        self.price = price
        self.value = value
        self.instrument_type = instrument_type
        self.raw_data = raw_data

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict suitable for JSON storage."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "quantity": self.quantity,
            "price": str(self.price) if self.price is not None else None,
            "value": str(self.value) if self.value is not None else None,
            "instrument_type": self.instrument_type,
            "raw_data": self.raw_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrokerPositionExtracted":
        """Reconstruct from a dict (e.g. JSON deserialisation)."""
        return cls(
            ticker=data.get("ticker"),
            name=data.get("name"),
            quantity=data.get("quantity"),
            price=Decimal(data["price"]) if data.get("price") else None,
            value=Decimal(data["value"]) if data.get("value") else None,
            instrument_type=data.get("instrument_type"),
            raw_data=data.get("raw_data"),
        )

    def __repr__(self) -> str:
        return (
            f"BrokerPositionExtracted("
            f"ticker={self.ticker!r}, name={self.name!r}, "
            f"quantity={self.quantity}, price={self.price}, value={self.value})"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_file_type(filename: str) -> str:
    """
    Detect file type from filename extension.

    Returns one of: ``CSV``, ``XLSX``, ``PDF``, ``TXT``.
    Falls back to ``TXT`` for unknown extensions.

    Args:
        filename: Original uploaded filename.

    Returns:
        Upper-case file type string.
    """
    if "." not in filename:
        return "TXT"
    ext = filename.rsplit(".", 1)[-1].lower()
    type_map = {
        "csv": "CSV",
        "xlsx": "XLSX",
        "xls": "XLSX",
        "pdf": "PDF",
        "txt": "TXT",
        "tsv": "TXT",
    }
    return type_map.get(ext, "TXT")


def extract_positions(content: bytes, file_type: str) -> List[BrokerPositionExtracted]:
    """
    Main entry point — extract positions from raw file bytes.

    Dispatches to the appropriate parser based on *file_type*.
    On any error logs the exception and returns an empty list so
    the caller can mark the upload status as ``ERROR``.

    Args:
        content: Raw file bytes.
        file_type: One of ``CSV``, ``XLSX``, ``PDF``, ``TXT``.

    Returns:
        List of extracted positions (may be empty).
    """
    try:
        if file_type == "CSV":
            return parse_csv(content)
        if file_type == "XLSX":
            return parse_xlsx(content)
        if file_type == "TXT":
            return parse_txt(content)
        if file_type == "PDF":
            # PDF parsing is not yet implemented
            logger.warning("PDF parsing not yet implemented")
            return []
        logger.warning("Unknown file type: %s", file_type)
        return []
    except Exception as exc:
        logger.exception("Failed to extract positions: %s", exc)
        return []


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def parse_csv(content: bytes) -> List[BrokerPositionExtracted]:
    """
    Parse a CSV file with automatic delimiter detection.

    Supports comma, semicolon, and tab delimiters.  Tries UTF-8 first,
    falls back to latin-1 for Angolan Windows-generated files.

    Args:
        content: Raw CSV bytes.

    Returns:
        List of extracted positions.
    """
    text = _decode_text(content)
    delimiter = _detect_delimiter(text)
    return _parse_csv_text(text, delimiter)


# ---------------------------------------------------------------------------
# XLSX parser
# ---------------------------------------------------------------------------

def parse_xlsx(content: bytes) -> List[BrokerPositionExtracted]:
    """
    Parse an Excel (.xlsx) file using openpyxl.

    Reads the first worksheet and treats the first non-empty row as headers.

    Args:
        content: Raw XLSX bytes.

    Returns:
        List of extracted positions.
    """
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl is not installed; cannot parse XLSX files")
        return []

    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(content),
            data_only=True,
            read_only=True,
        )
    except Exception as exc:
        logger.error("Failed to open XLSX workbook: %s", exc)
        return []

    positions: List[BrokerPositionExtracted] = []

    # Process the first worksheet only
    try:
        sheet = workbook.active
        if sheet is None:
            logger.warning("XLSX file has no active worksheet")
            return []

        rows = list(sheet.iter_rows(values_only=True))
        if len(rows) < 2:
            logger.warning("XLSX worksheet has fewer than 2 rows")
            return []

        # Find header row — first row with at least 3 non-empty cells
        header_row_idx = None
        for idx, row in enumerate(rows):
            non_empty = sum(1 for cell in row if cell is not None and str(cell).strip())
            if non_empty >= 3:
                header_row_idx = idx
                break

        if header_row_idx is None:
            logger.warning("Could not find a header row in XLSX")
            return []

        headers = [str(cell).strip() if cell is not None else "" for cell in rows[header_row_idx]]
        col_map = _build_column_map(headers)

        if not col_map:
            logger.warning("No recognised columns in XLSX headers: %s", headers)
            return []

        for row in rows[header_row_idx + 1:]:
            # Stop at completely empty rows
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue

            pos = _extract_position_from_row(row, col_map, headers)
            if pos is not None and _position_has_data(pos):
                positions.append(pos)

    finally:
        workbook.close()

    return positions


# ---------------------------------------------------------------------------
# TXT / TSV parser
# ---------------------------------------------------------------------------

def parse_txt(content: bytes) -> List[BrokerPositionExtracted]:
    """
    Parse a plain-text or TSV file.

    Attempts tab delimiter first, falls back to comma, then semicolon.

    Args:
        content: Raw text bytes.

    Returns:
        List of extracted positions.
    """
    text = _decode_text(content)

    # Try tab first, then comma, then semicolon
    for delimiter in ("\t", ",", ";"):
        try:
            positions = _parse_csv_text(text, delimiter)
            if positions:
                return positions
        except Exception:
            continue

    # Last resort: try to parse as a simple line-based format
    return _parse_line_based(text)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decode_text(content: bytes) -> str:
    """
    Decode bytes to text.  Tries UTF-8 first, falls back to latin-1
    (common in Angolan broker exports from Windows systems).
    """
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _detect_delimiter(text: str) -> str:
    """
    Detect the most likely CSV delimiter by inspecting the first line.
    """
    lines = text.splitlines()
    if not lines:
        return ","

    first_line = lines[0]
    semicolons = first_line.count(";")
    commas = first_line.count(",")
    tabs = first_line.count("\t")

    if tabs > commas and tabs > semicolons:
        return "\t"
    if semicolons > commas:
        return ";"
    return ","


def _parse_csv_text(text: str, delimiter: str) -> List[BrokerPositionExtracted]:
    """
    Parse CSV text with a known delimiter.
    """
    positions: List[BrokerPositionExtracted] = []

    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            logger.warning("CSV has no headers")
            return []

        headers = list(reader.fieldnames)
        col_map = _build_column_map(headers)

        if not col_map:
            logger.warning("No recognised columns in headers: %s", headers)
            return []

        for row in reader:
            if not any(v and str(v).strip() for v in row.values()):
                continue  # skip empty rows

            pos = _extract_position_from_csv_row(row, col_map)
            if pos is not None and _position_has_data(pos):
                positions.append(pos)

    except Exception as exc:
        logger.error("CSV parsing failed: %s", exc)

    return positions


def _build_column_map(headers: List[str]) -> Dict[str, int]:
    """
    Build a mapping from standard field names to column indices.

    Recognises fields: ticker, name, quantity, price, value, instrument_type.
    """
    col_map: Dict[str, int] = {}
    headers_lower = [h.lower().strip().replace(" ", "_") for h in headers]

    for idx, h in enumerate(headers_lower):
        if "ticker" in col_map and "name" in col_map and "quantity" in col_map:
            break  # we have enough

        if h in _TICKER_ALIASES and "ticker" not in col_map:
            col_map["ticker"] = idx
        elif h in _NAME_ALIASES and "name" not in col_map:
            col_map["name"] = idx
        elif h in _QUANTITY_ALIASES and "quantity" not in col_map:
            col_map["quantity"] = idx
        elif h in _PRICE_ALIASES and "price" not in col_map:
            col_map["price"] = idx
        elif h in _VALUE_ALIASES and "value" not in col_map:
            col_map["value"] = idx
        elif h in _TYPE_ALIASES and "instrument_type" not in col_map:
            col_map["instrument_type"] = idx

    # If we have no ticker/name column but there are headers, try fuzzy matching
    if "ticker" not in col_map and "name" not in col_map:
        for idx, h in enumerate(headers_lower):
            if any(alias in h for alias in _TICKER_ALIASES):
                col_map["ticker"] = idx
                break
        for idx, h in enumerate(headers_lower):
            if any(alias in h for alias in _NAME_ALIASES):
                col_map["name"] = idx
                break

    return col_map


def _extract_position_from_csv_row(
    row: Dict[str, str],
    col_map: Dict[str, int],
) -> Optional[BrokerPositionExtracted]:
    """
    Extract a BrokerPositionExtracted from a CSV DictReader row.
    """
    headers = list(row.keys())
    raw_data = {k: v for k, v in row.items()}

    ticker = None
    name = None
    quantity = None
    price = None
    value = None
    instrument_type = None

    if "ticker" in col_map and col_map["ticker"] < len(headers):
        ticker = _clean_string(row.get(headers[col_map["ticker"]]))
    if "name" in col_map and col_map["name"] < len(headers):
        name = _clean_string(row.get(headers[col_map["name"]]))
    if "quantity" in col_map and col_map["quantity"] < len(headers):
        quantity = _parse_int(row.get(headers[col_map["quantity"]]))
    if "price" in col_map and col_map["price"] < len(headers):
        price = _parse_decimal(row.get(headers[col_map["price"]]))
    if "value" in col_map and col_map["value"] < len(headers):
        value = _parse_decimal(row.get(headers[col_map["value"]]))
    if "instrument_type" in col_map and col_map["instrument_type"] < len(headers):
        instrument_type = _clean_string(row.get(headers[col_map["instrument_type"]]))

    return BrokerPositionExtracted(
        ticker=ticker,
        name=name,
        quantity=quantity,
        price=price,
        value=value,
        instrument_type=instrument_type,
        raw_data=raw_data,
    )


def _extract_position_from_row(
    row: tuple,
    col_map: Dict[str, int],
    headers: List[str],
) -> Optional[BrokerPositionExtracted]:
    """
    Extract a BrokerPositionExtracted from an XLSX row tuple.
    """
    raw_data = {}
    for idx, header in enumerate(headers):
        if idx < len(row):
            raw_data[header] = str(row[idx]) if row[idx] is not None else ""
        else:
            raw_data[header] = ""

    def get_cell(field: str) -> Optional[str]:
        idx = col_map.get(field)
        if idx is None or idx >= len(row):
            return None
        val = row[idx]
        return str(val).strip() if val is not None else None

    ticker = _clean_string(get_cell("ticker"))
    name = _clean_string(get_cell("name"))
    quantity = _parse_int(get_cell("quantity"))
    price = _parse_decimal(get_cell("price"))
    value = _parse_decimal(get_cell("value"))
    instrument_type = _clean_string(get_cell("instrument_type"))

    return BrokerPositionExtracted(
        ticker=ticker,
        name=name,
        quantity=quantity,
        price=price,
        value=value,
        instrument_type=instrument_type,
        raw_data=raw_data,
    )


def _position_has_data(pos: BrokerPositionExtracted) -> bool:
    """
    Check whether a position has at least one meaningful data field.
    """
    return any([
        pos.ticker,
        pos.name,
        pos.quantity is not None,
        pos.price is not None,
        pos.value is not None,
    ])


def _parse_int(value: Optional[str]) -> Optional[int]:
    """
    Parse an integer from a string, handling thousands separators.
    """
    if value is None:
        return None
    cleaned = value.strip().replace(" ", "").replace(",", "").replace(".", "")
    # Handle cases like "1.000" (Portuguese thousands) vs "1000"
    # Simple approach: remove all non-digits except leading minus
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        # Try extracting just digits
        digits = "".join(c for c in cleaned if c.isdigit() or c == "-")
        if digits:
            try:
                return int(digits)
            except ValueError:
                pass
        return None


def _parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    """
    Parse a Decimal from a string, handling various formats.

    Handles:
        - "1,234.56" (US/UK)
        - "1.234,56" (Portuguese/European)
        - "1 234,56" (French/African)
        - "(123.45)" (accounting negative)
        - "Kz 1,234.56" (Angolan kwanza)
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None

    # Remove currency symbols
    for symbol in ("Kz", "kz", "$", "€", "£", "AOA", "USD", "EUR"):
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()

    # Handle accounting negative: (123.45) → -123.45
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]

    if not cleaned:
        return None

    # Detect format: European vs US
    # European: 1.234,56  (comma is decimal, dot is thousands)
    # US:       1,234.56  (dot is decimal, comma is thousands)

    has_comma = "," in cleaned
    has_dot = "." in cleaned

    if has_comma and has_dot:
        # Both present — determine which is decimal separator
        last_comma = cleaned.rfind(",")
        last_dot = cleaned.rfind(".")

        if last_comma > last_dot:
            # European format: 1.234,56
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # US format: 1,234.56
            cleaned = cleaned.replace(",", "")
    elif has_comma and not has_dot:
        # Could be European decimal (1,5) or US thousands (1,000)
        # Heuristic: if comma is followed by exactly 2 digits at end → decimal
        parts_after_comma = cleaned.split(",")[-1]
        if len(parts_after_comma) == 2 and parts_after_comma.isdigit():
            # European decimal
            cleaned = cleaned.replace(",", ".")
        else:
            # US thousands separator
            cleaned = cleaned.replace(",", "")
    # If only dot, assume it's the decimal separator (US/European both use dot)

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _clean_string(value: Optional[str]) -> Optional[str]:
    """
    Clean and normalise a string value.  Returns None for empty strings.
    """
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _parse_line_based(text: str) -> List[BrokerPositionExtracted]:
    """
    Fallback parser for line-based text files without clear headers.

    Attempts to split each line by whitespace and map columns heuristically.
    """
    positions: List[BrokerPositionExtracted] = []
    lines = text.splitlines()

    for line in lines:
        line = line.strip()
        if not line or line.startswith(("#", "-", "=", "*")):
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        # Heuristic: first part is ticker/code, last numeric is value,
        # second-last numeric is price/quantity
        ticker = parts[0]
        name = " ".join(parts[1:-2]) if len(parts) > 3 else None

        quantity = None
        price = None
        value = None

        # Try to parse numeric values from the end
        for part in reversed(parts):
            parsed = _parse_decimal(part)
            if parsed is not None:
                if value is None:
                    value = parsed
                elif price is None:
                    price = parsed
                elif quantity is None:
                    quantity = int(parsed) if parsed == int(parsed) else None
                    break

        if ticker or name:
            positions.append(
                BrokerPositionExtracted(
                    ticker=ticker,
                    name=name,
                    quantity=quantity,
                    price=price,
                    value=value,
                    raw_data={"line": line},
                )
            )

    return positions
