"""
Bank Statement Parser — CSV and OFX format support.
Handles Angolan bank formats (BAI, BFA, BCI, etc.).
"""
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Optional


def parse_date(date_str: str, formats: list[str] | None = None) -> datetime:
    """Parse a date string trying multiple formats."""
    if formats is None:
        formats = [
            "%Y-%m-%d",      # 2026-05-24
            "%d/%m/%Y",      # 24/05/2026
            "%d-%m-%Y",      # 24-05-2026
            "%m/%d/%Y",      # 05/24/2026
            "%d.%m.%Y",      # 24.05.2026
            "%Y%m%d",        # 20260524
            "%d/%m/%y",      # 24/05/26
            "%d-%m-%y",      # 24-05-26
        ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")


def parse_amount(amount_str: str) -> Decimal:
    """Parse an amount string handling various formats."""
    if not amount_str:
        return Decimal("0.00")
    # Remove currency symbols, spaces, and normalize
    cleaned = amount_str.strip()
    # Handle negative in parentheses: (1,200.50) → -1200.50
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    # Remove thousands separators (commas or spaces)
    cleaned = cleaned.replace(" ", "").replace(",", "")
    # Handle Kz suffix
    cleaned = cleaned.replace("Kz", "").replace("kz", "")
    cleaned = cleaned.strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Cannot parse amount: {amount_str}")


def generate_transaction_id(date: datetime, amount: Decimal, description: str) -> str:
    """Generate a unique transaction ID from date, amount, and description."""
    import hashlib
    raw = f"{date.strftime('%Y%m%d')}_{str(amount)}_{description.strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def detect_csv_format(headers: list[str]) -> str:
    """Detect the CSV format based on column headers."""
    headers_lower = [h.lower().strip() for h in headers]
    header_set = set(headers_lower)
    
    # Check for known Angolan bank formats
    if any("data" in h for h in headers_lower) and any("valor" in h for h in headers_lower):
        if any("descricao" in h for h in headers_lower) or any("desc" in h for h in headers_lower):
            return "angolan_standard"
    
    if any("date" in h for h in headers_lower) and any("amount" in h for h in headers_lower):
        return "standard_english"
    
    if header_set & {"data", "descrição", "montante", "valor", "saldo"}:
        return "angolan_standard"
    
    if header_set & {"data_mov", "data_movimento", "descricao", "valor", "natureza"}:
        return "bai_format"
    
    if header_set & {"date", "description", "amount", "debit", "credit"}:
        return "standard_english"
    
    # Generic: if it has date-like and amount-like columns
    if any("data" in h or "date" in h for h in headers_lower):
        if any(k in h for h in headers_lower for k in ["valor", "amount", "montante", "debit", "credit"]):
            return "generic"
    
    return "unknown"


def parse_csv_statement(
    file_content: bytes,
    account_id: str,
    family_id: str,
    delimiter: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Parse a CSV bank statement and return a list of statement lines.
    
    Args:
        file_content: Raw bytes of the CSV file
        account_id: UUID of the bank account
        family_id: UUID of the family
        delimiter: Optional delimiter override (auto-detected if None)
    
    Returns:
        List of dicts with keys: bank_transaction_id, amount, date, description_raw
    """
    # Detect encoding and decode
    try:
        text = file_content.decode("utf-8")
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")
    
    # Detect delimiter
    if delimiter is None:
        first_line = text.split("\n")[0] if text else ""
        if ";" in first_line and first_line.count(";") > first_line.count(","):
            delimiter = ";"
        else:
            delimiter = ","
    
    # Parse CSV
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV file has no headers")
    
    headers = list(reader.fieldnames)
    detected_format = detect_csv_format(headers)
    
    # Map headers to standard fields
    field_map = _map_headers(headers, detected_format)
    
    lines: List[Dict[str, Any]] = []
    for row in reader:
        if not any(row.values()):  # Skip empty rows
            continue
        
        try:
            date_str = _get_field(row, field_map["date"])
            amount_str = _get_field(row, field_map["amount"])
            description = _get_field(row, field_map["description"], default="")
            
            if not date_str or not amount_str:
                continue
            
            parsed_date = parse_date(date_str)
            amount = parse_amount(amount_str)
            
            tx_id = generate_transaction_id(parsed_date, amount, description)
            
            lines.append({
                "bank_transaction_id": tx_id,
                "amount": amount,
                "date": parsed_date.date(),
                "description_raw": description,
            })
        except (ValueError, KeyError, InvalidOperation):
            # Skip unparseable rows
            continue
    
    return lines


def parse_ofx_statement(
    file_content: bytes,
    account_id: str,
    family_id: str,
) -> List[Dict[str, Any]]:
    """
    Parse an OFX file and return statement lines.
    
    Args:
        file_content: Raw bytes of the OFX file
        account_id: UUID of the bank account
        family_id: UUID of the family
    
    Returns:
        List of dicts with keys: bank_transaction_id, amount, date, description_raw
    """
    try:
        text = file_content.decode("utf-8")
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")
    
    lines: List[Dict[str, Any]] = []
    
    # Simple OFX parser — extract <STMTTRN> blocks
    import re
    
    stmt_trn_pattern = re.compile(
        r"<STMTTRN>\s*"
        r"(?:<TRNTYPE>[^<]+</TRNTYPE>\s*)?"
        r"<DTPOSTED>([^<]+)</DTPOSTED>\s*"
        r"<TRNAMT>([^<]+)</TRNAMT>\s*"
        r"(?:<FITID>([^<]+)</FITID>\s*)?"
        r"(?:<NAME>([^<]+)</NAME>\s*)?"
        r"(?:<MEMO>([^<]+)</MEMO>\s*)?"
        r"</STMTTRN>",
        re.IGNORECASE,
    )
    
    for match in stmt_trn_pattern.finditer(text):
        dt_posted = match.group(1).strip()
        trn_amt = match.group(2).strip()
        fit_id = match.group(3)
        name = match.group(4) or ""
        memo = match.group(5) or ""
        
        try:
            # Parse OFX date: 20260524 or 20260524000000
            date_str = dt_posted[:8]
            parsed_date = datetime.strptime(date_str, "%Y%m%d")
            amount = parse_amount(trn_amt)
            description = f"{name} {memo}".strip() or "Transaction"
            
            tx_id = fit_id or generate_transaction_id(parsed_date, amount, description)
            
            lines.append({
                "bank_transaction_id": tx_id,
                "amount": amount,
                "date": parsed_date.date(),
                "description_raw": description,
            })
        except (ValueError, InvalidOperation):
            continue
    
    return lines


def parse_statement(
    file_content: bytes,
    filename: str,
    account_id: str,
    family_id: str,
) -> List[Dict[str, Any]]:
    """
    Auto-detect format and parse a bank statement file.
    
    Supports: .csv, .ofx, .txt (CSV-like)
    """
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    
    if ext in ("ofx", "qfx"):
        return parse_ofx_statement(file_content, account_id, family_id)
    elif ext in ("csv", "txt", ""):
        return parse_csv_statement(file_content, account_id, family_id)
    else:
        # Try CSV as fallback
        return parse_csv_statement(file_content, account_id, family_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_headers(headers: list[str], fmt: str) -> Dict[str, list[str]]:
    """Map original headers to standard field names."""
    headers_lower = [h.lower().strip() for h in headers]
    
    date_candidates = ["date", "data", "data_mov", "data_movimento", "dtposted", "data transacao", "data_transacao"]
    amount_candidates = ["amount", "valor", "montante", "trnamt", "amount_debit", "amount_credit", "valor_eur"]
    desc_candidates = ["description", "descricao", "desc", "memo", "name", "concepto", "descricao_movimento", "movimento"]
    
    def find_index(candidates: list[str]) -> list[int]:
        """Return column indices matching any candidate."""
        indices = []
        for i, h in enumerate(headers_lower):
            if any(c in h for c in candidates):
                indices.append(i)
        return indices if indices else list(range(len(headers_lower)))
    
    date_idx = find_index(date_candidates)
    amount_idx = find_index(amount_candidates)
    desc_idx = find_index(desc_candidates)
    
    return {
        "date": date_idx,
        "amount": amount_idx,
        "description": desc_idx,
    }


def _get_field(row: Dict[str, str], candidate_indices: list[int], default: str = "") -> str:
    """Get the best-matching field from a CSV row."""
    headers = list(row.keys())
    for idx in candidate_indices:
        if idx < len(headers):
            value = row.get(headers[idx], "").strip()
            if value:
                return value
    return default
