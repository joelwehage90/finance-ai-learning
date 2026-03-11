"""SIE file parser for Swedish accounting data.

Parses SIE files (types 1-4) into structured Python dicts.
Handles CP437 encoding, multi-line VER blocks, quoted strings,
and dimension specifiers.

SIE (Standard Import Export) is the Swedish standard for exchanging
accounting data between systems. All major Swedish accounting software
(Fortnox, Visma, Bokio) can export SIE files.

Usage:
    from sie_parser import parse_sie

    with open("export.se", "rb") as f:
        text = f.read().decode("cp437")

    result = parse_sie(text)
    print(result["accounts"])
    print(result["vouchers"])
"""

from decimal import Decimal, InvalidOperation
from typing import Any


def parse_sie(text: str) -> dict[str, Any]:
    """Parse SIE text into structured data.

    Args:
        text: SIE file content as a Python string (already decoded).

    Returns:
        Dict with keys: metadata, financial_years, accounts, dimensions,
        objects, opening_balances, closing_balances, result_balances,
        period_balances, period_budgets, object_opening_balances,
        object_closing_balances, vouchers.
    """
    result: dict[str, Any] = {
        "metadata": {},
        "financial_years": [],
        "accounts": {},
        "dimensions": {},
        "objects": [],
        "opening_balances": [],
        "closing_balances": [],
        "result_balances": [],
        "period_balances": [],
        "period_budgets": [],
        "object_opening_balances": [],
        "object_closing_balances": [],
        "vouchers": [],
    }

    current_voucher: dict[str, Any] | None = None
    in_ver_block = False

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("//"):
            continue

        # Handle VER block boundaries
        if line == "{":
            continue
        if line == "}":
            if current_voucher is not None:
                result["vouchers"].append(current_voucher)
                current_voucher = None
            in_ver_block = False
            continue

        if not line.startswith("#"):
            continue

        tokens = _tokenize_line(line)
        if not tokens:
            continue

        tag = tokens[0].upper()

        # --- Metadata tags ---
        if tag == "#FLAGGA":
            result["metadata"]["flag"] = _safe_int(tokens, 1)
        elif tag == "#FORMAT":
            result["metadata"]["format"] = _safe_str(tokens, 1)
        elif tag == "#SIETYP":
            result["metadata"]["sie_type"] = _safe_int(tokens, 1)
        elif tag == "#PROGRAM":
            result["metadata"]["program"] = _safe_str(tokens, 1)
            result["metadata"]["program_version"] = _safe_str(tokens, 2)
        elif tag == "#GEN":
            result["metadata"]["generated"] = _safe_str(tokens, 1)
        elif tag == "#FNAMN":
            result["metadata"]["company_name"] = _safe_str(tokens, 1)
        elif tag == "#ORGNR":
            result["metadata"]["org_number"] = _safe_str(tokens, 1)
        elif tag == "#KPTYP":
            result["metadata"]["account_chart_type"] = _safe_str(tokens, 1)
        elif tag == "#VALUTA":
            result["metadata"]["currency"] = _safe_str(tokens, 1)
        elif tag == "#TAXAR":
            result["metadata"]["tax_year"] = _safe_int(tokens, 1)

        # --- Financial years ---
        elif tag == "#RAR":
            fy = {
                "year_offset": _safe_int(tokens, 1),
                "start": _safe_str(tokens, 2),
                "end": _safe_str(tokens, 3),
            }
            result["financial_years"].append(fy)

        # --- Chart of accounts ---
        elif tag == "#KONTO":
            acct_num = _safe_int(tokens, 1)
            if acct_num is not None:
                result["accounts"][acct_num] = {
                    "name": _safe_str(tokens, 2) or "",
                    "type": None,
                    "sru": None,
                }
        elif tag == "#KTYP":
            acct_num = _safe_int(tokens, 1)
            acct_type = _safe_str(tokens, 2)
            if acct_num in result["accounts"] and acct_type:
                result["accounts"][acct_num]["type"] = acct_type
        elif tag == "#SRU":
            acct_num = _safe_int(tokens, 1)
            sru_code = _safe_int(tokens, 2)
            if acct_num in result["accounts"] and sru_code is not None:
                result["accounts"][acct_num]["sru"] = sru_code

        # --- Dimensions ---
        elif tag == "#DIM":
            dim_id = _safe_int(tokens, 1)
            dim_name = _safe_str(tokens, 2) or ""
            if dim_id is not None:
                result["dimensions"][dim_id] = {"name": dim_name}
        elif tag == "#OBJEKT":
            dim_id = _safe_int(tokens, 1)
            obj_id = _safe_str(tokens, 2)
            obj_name = _safe_str(tokens, 3) or ""
            if dim_id is not None and obj_id is not None:
                result["objects"].append({
                    "dimension_id": dim_id,
                    "object_id": obj_id,
                    "name": obj_name,
                })

        # --- Balances ---
        elif tag == "#IB":
            bal = _parse_balance(tokens)
            if bal:
                result["opening_balances"].append(bal)
        elif tag == "#UB":
            bal = _parse_balance(tokens)
            if bal:
                result["closing_balances"].append(bal)
        elif tag == "#RES":
            bal = _parse_balance(tokens)
            if bal:
                result["result_balances"].append(bal)

        # --- Object balances (per cost center/project) ---
        elif tag == "#OIB":
            bal = _parse_object_balance(tokens)
            if bal:
                result["object_opening_balances"].append(bal)
        elif tag == "#OUB":
            bal = _parse_object_balance(tokens)
            if bal:
                result["object_closing_balances"].append(bal)

        # --- Period balances ---
        elif tag == "#PSALDO":
            pbal = _parse_period_balance(tokens)
            if pbal:
                result["period_balances"].append(pbal)
        elif tag == "#PBUDGET":
            pbal = _parse_period_balance(tokens)
            if pbal:
                result["period_budgets"].append(pbal)

        # --- Vouchers (SIE type 4) ---
        elif tag == "#VER":
            current_voucher = {
                "series": _safe_str(tokens, 1) or "",
                "number": _safe_int(tokens, 2),
                "date": _safe_str(tokens, 3),
                "text": _safe_str(tokens, 4),
                "transactions": [],
            }
            in_ver_block = True

        elif tag == "#TRANS" and in_ver_block and current_voucher is not None:
            trans = _parse_transaction(tokens)
            if trans:
                current_voucher["transactions"].append(trans)

    return result


# ----------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------

def _tokenize_line(line: str) -> list[str]:
    """Split a SIE line into tokens, respecting quoted strings and {}.

    Examples:
        '#KONTO 1930 "Bank Account"' -> ['#KONTO', '1930', 'Bank Account']
        '#TRANS 5010 {1 "SALJ"} 15000.00' -> ['#TRANS', '5010', '{1 "SALJ"}', '15000.00']
        '#PSALDO 0 202601 3010 {} -105000.00' -> ['#PSALDO', '0', '202601', '3010', '{}', '-105000.00']
    """
    tokens: list[str] = []
    i = 0
    n = len(line)

    while i < n:
        # Skip whitespace
        if line[i] in (" ", "\t"):
            i += 1
            continue

        # Quoted string
        if line[i] == '"':
            i += 1  # skip opening quote
            start = i
            while i < n and line[i] != '"':
                i += 1
            tokens.append(line[start:i])
            if i < n:
                i += 1  # skip closing quote
            continue

        # Curly brace group (dimension specifier)
        if line[i] == "{":
            start = i
            depth = 1
            i += 1
            while i < n and depth > 0:
                if line[i] == "{":
                    depth += 1
                elif line[i] == "}":
                    depth -= 1
                i += 1
            tokens.append(line[start:i])
            continue

        # Regular token
        start = i
        while i < n and line[i] not in (" ", "\t", '"', "{"):
            i += 1
        tokens.append(line[start:i])

    return tokens


def _parse_dimensions(dim_str: str) -> dict[int, str]:
    """Parse a dimension specifier like '{1 "SALJ"}' or '{1 "SALJ" 6 "PROJ1"}'.

    Returns:
        Dict mapping dimension_id -> object_id.
        Empty dict for '{}' or empty string.
    """
    # Strip outer braces
    inner = dim_str.strip()
    if inner.startswith("{"):
        inner = inner[1:]
    if inner.endswith("}"):
        inner = inner[:-1]
    inner = inner.strip()

    if not inner:
        return {}

    # Tokenize the inner content (handles quoted strings)
    parts = _tokenize_line(inner)

    dims: dict[int, str] = {}
    i = 0
    while i + 1 < len(parts):
        try:
            dim_id = int(parts[i])
            obj_id = parts[i + 1]
            dims[dim_id] = obj_id
            i += 2
        except (ValueError, IndexError):
            i += 1

    return dims


def _parse_balance(tokens: list[str]) -> dict[str, Any] | None:
    """Parse #IB, #UB, or #RES line.

    Format: #TAG year_offset account amount [quantity]
    Example: #IB 0 1930 340000.00
    """
    year_offset = _safe_int(tokens, 1)
    account = _safe_int(tokens, 2)
    amount = _safe_decimal(tokens, 3)

    if account is None or amount is None:
        return None

    return {
        "year_offset": year_offset or 0,
        "account": account,
        "amount": amount,
    }


def _parse_object_balance(tokens: list[str]) -> dict[str, Any] | None:
    """Parse #OIB or #OUB line.

    Format: #TAG year_offset account {dim_id "obj_id"} amount [quantity]
    Example: #OIB 0 1930 {1 "SALJ"} 170000.00
    """
    year_offset = _safe_int(tokens, 1)
    account = _safe_int(tokens, 2)
    dim_str = _safe_str(tokens, 3) or "{}"
    amount = _safe_decimal(tokens, 4)

    if account is None or amount is None:
        return None

    return {
        "year_offset": year_offset or 0,
        "account": account,
        "dimensions": _parse_dimensions(dim_str),
        "amount": amount,
    }


def _parse_period_balance(tokens: list[str]) -> dict[str, Any] | None:
    """Parse #PSALDO or #PBUDGET line.

    Format: #TAG year_offset period account {dims} amount [quantity]
    Example: #PSALDO 0 202601 3010 {} -105000.00
    """
    year_offset = _safe_int(tokens, 1)
    period = _safe_str(tokens, 2)
    account = _safe_int(tokens, 3)
    dim_str = _safe_str(tokens, 4) or "{}"
    amount = _safe_decimal(tokens, 5)

    if account is None or amount is None or period is None:
        return None

    return {
        "year_offset": year_offset or 0,
        "period": period,
        "account": account,
        "dimensions": _parse_dimensions(dim_str),
        "amount": amount,
    }


def _parse_transaction(tokens: list[str]) -> dict[str, Any] | None:
    """Parse #TRANS line inside a VER block.

    Format: #TRANS account {dims} amount [date] [text] [quantity]
    Example: #TRANS 5010 {1 "SALJ"} 15000.00 20260115 "Rent"
    """
    account = _safe_int(tokens, 1)
    dim_str = _safe_str(tokens, 2) or "{}"
    amount = _safe_decimal(tokens, 3)

    if account is None or amount is None:
        return None

    return {
        "account": account,
        "dimensions": _parse_dimensions(dim_str),
        "amount": amount,
        "date": _safe_str(tokens, 4),
        "text": _safe_str(tokens, 5),
    }


def _safe_str(tokens: list[str], index: int) -> str | None:
    """Safely get a string token, returning None if out of bounds."""
    if index < len(tokens):
        return tokens[index]
    return None


def _safe_int(tokens: list[str], index: int) -> int | None:
    """Safely get an integer token, returning None if invalid."""
    val = _safe_str(tokens, index)
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _safe_decimal(tokens: list[str], index: int) -> Decimal | None:
    """Safely get a Decimal token, returning None if invalid."""
    val = _safe_str(tokens, index)
    if val is None:
        return None
    try:
        return Decimal(val)
    except InvalidOperation:
        return None
