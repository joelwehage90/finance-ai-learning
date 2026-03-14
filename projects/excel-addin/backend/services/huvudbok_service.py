"""Huvudbok service — computes general ledger from SIE4 voucher data.

Fetches SIE4 from Fortnox, parses all vouchers and transactions,
and produces a general ledger with running balance per account.
"""

from collections import defaultdict
from typing import Any

from fortnox_sie_client import FortnoxSIEClient

from services.sie_cache import get_parsed_sie
from utils import DIM_HEADERS, parse_period


# Base headers (always present).
_BASE_HEADERS = [
    "Konto",
    "Kontonamn",
    "Datum",
    "Ver.serie",
    "Ver.nr",
    "Text",
]

# Amount headers (always at the end).
_AMOUNT_HEADERS = ["Debit", "Kredit", "Saldo"]

# Legacy constant for backward compatibility.
HUVUDBOK_HEADERS = _BASE_HEADERS + _AMOUNT_HEADERS


async def compute_general_ledger(
    client: FortnoxSIEClient,
    financial_year_id: int,
    from_account: int,
    to_account: int,
    from_period: str,
    to_period: str,
    cost_center: str | None = None,
    project: str | None = None,
    include_dimensions: list[int] | None = None,
) -> dict[str, Any]:
    """Compute a general ledger (Huvudbok) from SIE4 data.

    Shows all voucher transactions for selected accounts in a period,
    with running balance per account. Each account block starts with
    an opening balance row.

    Args:
        client: SIE client for fetching data from Fortnox.
        financial_year_id: Fortnox financial year ID.
        from_account: Start of account range (inclusive), e.g. 1000.
        to_account: End of account range (inclusive), e.g. 1999.
        from_period: Start period (YYYY-MM), inclusive.
        to_period: End period (YYYY-MM), inclusive.
        cost_center: Optional cost center filter (dimension 1).
        project: Optional project filter (dimension 6).
        include_dimensions: List of dimension IDs to include as output
            columns (e.g. [1, 6] for Kostnadsställe + Projekt).

    Returns:
        Dict with 'headers', 'rows', 'count', 'period'.
    """
    parsed = await get_parsed_sie(client, sie_type=4, financial_year_id=financial_year_id)

    # Convert and validate period format: "YYYY-MM" → "YYYYMM".
    from_p = parse_period(from_period)
    to_p = parse_period(to_period)

    dim_ids = include_dimensions or []

    # Build dynamic headers.
    headers = list(_BASE_HEADERS)
    for d in dim_ids:
        headers.append(DIM_HEADERS.get(d, f"Dim {d}"))
    headers.extend(_AMOUNT_HEADERS)

    # Number of None values to pad dimension columns in IB/UB rows.
    n_dim_cols = len(dim_ids)

    # Build opening balances per account (IB, year_offset=0).
    opening: dict[int, float] = defaultdict(float)
    for ib in parsed.get("opening_balances", []):
        if ib.get("year_offset", 0) != 0:
            continue
        acct = ib.get("account")
        if acct is None or not (from_account <= acct <= to_account):
            continue
        opening[acct] += float(ib["amount"])

    # Add period movements BEFORE from_period to opening balances.
    # This gives us the correct starting balance at from_period.
    for pb in parsed.get("period_balances", []):
        if pb.get("year_offset", 0) != 0:
            continue
        acct = pb.get("account")
        period = pb.get("period", "")
        if acct is None or not (from_account <= acct <= to_account):
            continue
        if period < from_p:
            opening[acct] += float(pb["amount"])

    # Collect transactions from vouchers within the period range.
    # Group by account for ordered output.
    account_transactions: dict[int, list[dict]] = defaultdict(list)
    account_names: dict[int, str] = {}

    # Build account name lookup.
    accounts = parsed.get("accounts", {})
    for acct_num, acct_info in accounts.items():
        if from_account <= acct_num <= to_account:
            account_names[acct_num] = acct_info.get("name", "")

    for voucher in parsed.get("vouchers", []):
        v_date = voucher.get("date", "") or ""
        # Convert voucher date "YYYYMMDD" to period "YYYYMM".
        v_period = v_date[:6] if len(v_date) >= 6 else ""

        if not (from_p <= v_period <= to_p):
            continue

        series = voucher.get("series", "")
        number = voucher.get("number")
        v_text = voucher.get("text", "") or ""

        for trans in voucher.get("transactions", []):
            acct = trans.get("account")
            if acct is None or not (from_account <= acct <= to_account):
                continue

            dims = trans.get("dimensions", {})

            # Cost center filter (dimension 1).
            if cost_center:
                if dims.get(1, "") != cost_center:
                    continue

            # Project filter (dimension 6).
            if project:
                if dims.get(6, "") != project:
                    continue

            amount = float(trans.get("amount", 0))
            trans_text = trans.get("text") or v_text

            # Format date as YYYY-MM-DD.
            formatted_date = v_date
            if len(v_date) == 8:
                formatted_date = f"{v_date[:4]}-{v_date[4:6]}-{v_date[6:8]}"

            # Extract dimension values for output.
            dim_values = [dims.get(d, "") for d in dim_ids]

            account_transactions[acct].append({
                "date": formatted_date,
                "series": series,
                "number": number,
                "text": trans_text,
                "amount": amount,
                "sort_key": v_date,  # For sorting by date.
                "dim_values": dim_values,
            })

            # Ensure account is in our name lookup.
            if acct not in account_names:
                account_names[acct] = accounts.get(acct, {}).get("name", "")

    # Build output rows sorted by account, then by date.
    rows: list[list[Any]] = []

    # Include all accounts in range that have either opening balance or transactions.
    all_accounts = sorted(set(opening.keys()) | set(account_transactions.keys()))

    for acct in all_accounts:
        acct_name = account_names.get(acct, "")
        ib = round(opening.get(acct, 0.0), 2)

        # Opening balance row (pad dimension columns with None).
        ib_row: list[Any] = [acct, acct_name, "", "", "", "Ingående balans"]
        ib_row.extend([None] * n_dim_cols)
        ib_row.extend([None, None, ib])
        rows.append(ib_row)

        # Sort transactions by date, then by voucher number.
        txns = sorted(
            account_transactions.get(acct, []),
            key=lambda t: (t["sort_key"], t.get("number") or 0),
        )

        running = ib
        for t in txns:
            amount = t["amount"]
            debit = round(amount, 2) if amount > 0 else None
            credit = round(abs(amount), 2) if amount < 0 else None
            running = round(running + amount, 2)

            row: list[Any] = [
                acct,
                acct_name,
                t["date"],
                t["series"],
                t["number"],
                t["text"],
            ]
            row.extend(t.get("dim_values", [None] * n_dim_cols))
            row.extend([debit, credit, running])
            rows.append(row)

        # Closing balance row.
        ub_row: list[Any] = [acct, acct_name, "", "", "", "Utgående balans"]
        ub_row.extend([None] * n_dim_cols)
        ub_row.extend([None, None, running])
        rows.append(ub_row)

        # Blank separator.
        rows.append([None] * len(headers))

    return {
        "headers": headers,
        "rows": rows,
        "count": len(rows),
        "period": f"{from_period} – {to_period}",
    }
