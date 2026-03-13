"""SIE report service — computes RR and BR from SIE2 data.

Fetches SIE2 from Fortnox, parses it with sie_parser, and computes
structured income statement (Resultaträkning) and balance sheet
(Balansräkning) reports ready for Excel output.
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from fortnox_sie_client import FortnoxSIEClient
from sie_parser import parse_sie


# ----------------------------------------------------------------
# Account class definitions (BAS-kontoplan)
# ----------------------------------------------------------------

# Income statement account groups (konto 3000-8999).
RR_GROUPS = [
    ("30-37", 3000, 3799, "Nettoomsättning"),
    ("38-39", 3800, 3999, "Övriga rörelseintäkter"),
    ("40-49", 4000, 4999, "Råvaror och förnödenheter"),
    ("50-69", 5000, 6999, "Övriga externa kostnader"),
    ("70-76", 7000, 7699, "Personalkostnader"),
    ("77-79", 7700, 7999, "Av-/nedskrivningar"),
    ("80-84", 8000, 8499, "Finansiella intäkter"),
    ("85-89", 8500, 8999, "Finansiella kostnader"),
]

# Balance sheet account groups (konto 1000-2999).
BR_GROUPS = [
    ("10-13", 1000, 1399, "Immateriella anläggningstillgångar"),
    ("14-18", 1400, 1899, "Materiella anläggningstillgångar"),
    ("19", 1900, 1999, "Kassa och bank"),
    ("20", 2000, 2099, "Eget kapital"),
    ("21-22", 2100, 2299, "Obeskattade reserver"),
    ("23-29", 2300, 2999, "Skulder"),
]


async def compute_income_statement(
    client: FortnoxSIEClient,
    financial_year_id: int,
    from_period: str,
    to_period: str,
) -> dict[str, Any]:
    """Compute an income statement (Resultaträkning) from SIE2 data.

    Args:
        client: SIE client for fetching data from Fortnox.
        financial_year_id: Fortnox financial year ID.
        from_period: Start period inclusive, format "YYYY-MM".
        to_period: End period inclusive, format "YYYY-MM".

    Returns:
        Dict with 'headers', 'rows' (including subtotals), 'period', 'total'.
    """
    sie_text = await client.get_sie(sie_type=2, financial_year=financial_year_id)
    parsed = parse_sie(sie_text)

    # Convert period format for comparison: "YYYY-MM" → "YYYYMM".
    from_p = from_period.replace("-", "")
    to_p = to_period.replace("-", "")

    # Sum period_balances per account within the period range.
    account_totals: dict[int, float] = defaultdict(float)
    for pb in parsed.get("period_balances", []):
        if pb.get("year_offset", 0) != 0:
            continue
        period = pb.get("period", "")
        account = pb.get("account")
        if account is None:
            continue
        if not (3000 <= account <= 8999):
            continue
        if from_p <= period <= to_p:
            account_totals[account] += float(pb["amount"])

    # Build account name lookup.
    accounts = parsed.get("accounts", {})

    # Group by RR categories.
    headers = ["Konto", "Kontonamn", "Belopp"]
    rows: list[list[Any]] = []
    grand_total = 0.0

    for group_code, range_from, range_to, group_label in RR_GROUPS:
        group_rows: list[list[Any]] = []
        group_sum = 0.0

        for acct_num in sorted(account_totals.keys()):
            if range_from <= acct_num <= range_to:
                amount = round(account_totals[acct_num], 2)
                if amount == 0:
                    continue
                acct_name = accounts.get(acct_num, {}).get("name", "")
                group_rows.append([acct_num, acct_name, amount])
                group_sum += amount

        if group_rows:
            # Add group header.
            rows.append([None, f"— {group_label} —", None])
            rows.extend(group_rows)
            rows.append([None, f"Summa {group_label}", round(group_sum, 2)])
            rows.append([None, "", None])  # Blank separator row.
            grand_total += group_sum

    # Final result row.
    rows.append([None, "RESULTAT", round(grand_total, 2)])

    return {
        "headers": headers,
        "rows": rows,
        "period": f"{from_period} – {to_period}",
        "total": round(grand_total, 2),
    }


async def compute_balance_sheet(
    client: FortnoxSIEClient,
    financial_year_id: int,
    period: str,
) -> dict[str, Any]:
    """Compute a balance sheet (Balansräkning) from SIE2 data.

    Balance = Opening balance (IB) + accumulated period movements
    up to and including the specified period.

    Args:
        client: SIE client for fetching data from Fortnox.
        financial_year_id: Fortnox financial year ID.
        period: Period to show balance for, format "YYYY-MM".

    Returns:
        Dict with 'headers', 'rows' (including subtotals), 'period', 'totals'.
    """
    sie_text = await client.get_sie(sie_type=2, financial_year=financial_year_id)
    parsed = parse_sie(sie_text)

    to_p = period.replace("-", "")

    # Start with opening balances (IB) for balance sheet accounts.
    account_balances: dict[int, float] = defaultdict(float)
    for ib in parsed.get("opening_balances", []):
        if ib.get("year_offset", 0) != 0:
            continue
        account = ib.get("account")
        if account is None:
            continue
        if 1000 <= account <= 2999:
            account_balances[account] += float(ib["amount"])

    # Add period movements up to the selected period.
    for pb in parsed.get("period_balances", []):
        if pb.get("year_offset", 0) != 0:
            continue
        period_str = pb.get("period", "")
        account = pb.get("account")
        if account is None:
            continue
        if not (1000 <= account <= 2999):
            continue
        if period_str <= to_p:
            account_balances[account] += float(pb["amount"])

    # Build account name lookup.
    accounts = parsed.get("accounts", {})

    # Group by BR categories.
    headers = ["Konto", "Kontonamn", "Saldo"]
    rows: list[list[Any]] = []

    assets_total = 0.0  # Tillgångar (1xxx)
    equity_liabilities_total = 0.0  # EK + skulder (2xxx)

    for group_code, range_from, range_to, group_label in BR_GROUPS:
        group_rows: list[list[Any]] = []
        group_sum = 0.0

        for acct_num in sorted(account_balances.keys()):
            if range_from <= acct_num <= range_to:
                balance = round(account_balances[acct_num], 2)
                if balance == 0:
                    continue
                acct_name = accounts.get(acct_num, {}).get("name", "")
                group_rows.append([acct_num, acct_name, balance])
                group_sum += balance

        if group_rows:
            rows.append([None, f"— {group_label} —", None])
            rows.extend(group_rows)
            rows.append([None, f"Summa {group_label}", round(group_sum, 2)])
            rows.append([None, "", None])

            if range_from < 2000:
                assets_total += group_sum
            else:
                equity_liabilities_total += group_sum

    # Summary rows.
    rows.append([None, "SUMMA TILLGÅNGAR", round(assets_total, 2)])
    rows.append([None, "SUMMA EGET KAPITAL OCH SKULDER", round(equity_liabilities_total, 2)])

    return {
        "headers": headers,
        "rows": rows,
        "period": period,
        "totals": {
            "assets": round(assets_total, 2),
            "equity_and_liabilities": round(equity_liabilities_total, 2),
        },
    }
