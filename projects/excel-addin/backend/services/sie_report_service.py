"""SIE report service — computes RR and BR from SIE2 data.

Fetches SIE2 from Fortnox, parses it with sie_parser, and computes
structured income statement (Resultaträkning) and balance sheet
(Balansräkning) reports ready for Excel output.

Also provides comparative versions that include prior-year columns
with change amounts and percentages.
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

from fortnox_sie_client import FortnoxSIEClient
from sie_parser import parse_sie


def _pct_change(current: float, prior: float) -> float | None:
    """Compute percentage change, returning None if prior is zero."""
    if prior == 0:
        return None
    return round((current - prior) / abs(prior) * 100, 1)


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


# ----------------------------------------------------------------
# Comparative report functions
# ----------------------------------------------------------------

def _sum_period_balances(
    parsed: dict,
    year_offset: int,
    from_p: str,
    to_p: str,
    acct_from: int,
    acct_to: int,
) -> dict[int, float]:
    """Sum period_balances for given year_offset and account range."""
    totals: dict[int, float] = defaultdict(float)
    for pb in parsed.get("period_balances", []):
        if pb.get("year_offset", 0) != year_offset:
            continue
        period = pb.get("period", "")
        account = pb.get("account")
        if account is None or not (acct_from <= account <= acct_to):
            continue
        if from_p <= period <= to_p:
            totals[account] += float(pb["amount"])
    return totals


def _compute_br_balances(
    parsed: dict,
    year_offset: int,
    to_p: str,
) -> dict[int, float]:
    """Compute balance sheet balances for given year_offset.

    IB (opening_balances) + accumulated period movements up to period.
    """
    balances: dict[int, float] = defaultdict(float)

    for ib in parsed.get("opening_balances", []):
        if ib.get("year_offset", 0) != year_offset:
            continue
        acct = ib.get("account")
        if acct is not None and 1000 <= acct <= 2999:
            balances[acct] += float(ib["amount"])

    for pb in parsed.get("period_balances", []):
        if pb.get("year_offset", 0) != year_offset:
            continue
        period = pb.get("period", "")
        acct = pb.get("account")
        if acct is None or not (1000 <= acct <= 2999):
            continue
        if period <= to_p:
            balances[acct] += float(pb["amount"])

    return balances


async def compute_income_statement_comparative(
    client: FortnoxSIEClient,
    financial_year_id: int,
    from_period: str,
    to_period: str,
) -> dict[str, Any]:
    """Compute comparative income statement (RR) with prior year.

    Returns rows with: Konto, Kontonamn, Aktuellt, Föreg. år,
    Förändring SEK, Förändring %.

    Args:
        client: SIE client for fetching data from Fortnox.
        financial_year_id: Fortnox financial year ID.
        from_period: Start period inclusive, format "YYYY-MM".
        to_period: End period inclusive, format "YYYY-MM".

    Returns:
        Dict with 'headers', 'rows', 'period', 'total', 'comparison_total'.
    """
    sie_text = await client.get_sie(sie_type=2, financial_year=financial_year_id)
    parsed = parse_sie(sie_text)

    from_p = from_period.replace("-", "")
    to_p = to_period.replace("-", "")

    # Current year (year_offset=0) and prior year (year_offset=-1).
    current = _sum_period_balances(parsed, 0, from_p, to_p, 3000, 8999)
    prior = _sum_period_balances(parsed, -1, from_p, to_p, 3000, 8999)

    accounts = parsed.get("accounts", {})
    all_accounts = sorted(set(current.keys()) | set(prior.keys()))

    headers = ["Konto", "Kontonamn", "Aktuellt", "Föreg. år", "Förändring SEK", "Förändring %"]
    rows: list[list[Any]] = []
    grand_current = 0.0
    grand_prior = 0.0

    for _code, range_from, range_to, group_label in RR_GROUPS:
        group_rows: list[list[Any]] = []
        grp_current = 0.0
        grp_prior = 0.0

        for acct in all_accounts:
            if not (range_from <= acct <= range_to):
                continue
            cur = round(current.get(acct, 0.0), 2)
            pri = round(prior.get(acct, 0.0), 2)
            if cur == 0 and pri == 0:
                continue
            change = round(cur - pri, 2)
            pct = _pct_change(cur, pri)
            name = accounts.get(acct, {}).get("name", "")
            group_rows.append([acct, name, cur, pri, change, pct])
            grp_current += cur
            grp_prior += pri

        if group_rows:
            rows.append([None, f"— {group_label} —", None, None, None, None])
            rows.extend(group_rows)
            grp_change = round(grp_current - grp_prior, 2)
            grp_pct = _pct_change(grp_current, grp_prior)
            rows.append([
                None, f"Summa {group_label}",
                round(grp_current, 2), round(grp_prior, 2),
                grp_change, grp_pct,
            ])
            rows.append([None, "", None, None, None, None])
            grand_current += grp_current
            grand_prior += grp_prior

    grand_change = round(grand_current - grand_prior, 2)
    grand_pct = _pct_change(grand_current, grand_prior)
    rows.append([
        None, "RESULTAT",
        round(grand_current, 2), round(grand_prior, 2),
        grand_change, grand_pct,
    ])

    return {
        "headers": headers,
        "rows": rows,
        "period": f"{from_period} – {to_period}",
        "total": round(grand_current, 2),
        "comparison_total": round(grand_prior, 2),
    }


async def compute_balance_sheet_comparative(
    client: FortnoxSIEClient,
    financial_year_id: int,
    period: str,
) -> dict[str, Any]:
    """Compute comparative balance sheet (BR) with prior year.

    Returns rows with: Konto, Kontonamn, Aktuellt, Föreg. år,
    Förändring SEK, Förändring %.

    Args:
        client: SIE client for fetching data from Fortnox.
        financial_year_id: Fortnox financial year ID.
        period: Period to show balance for, format "YYYY-MM".

    Returns:
        Dict with 'headers', 'rows', 'period', 'totals', 'comparison_totals'.
    """
    sie_text = await client.get_sie(sie_type=2, financial_year=financial_year_id)
    parsed = parse_sie(sie_text)

    to_p = period.replace("-", "")

    current = _compute_br_balances(parsed, 0, to_p)
    prior = _compute_br_balances(parsed, -1, to_p)

    accounts = parsed.get("accounts", {})
    all_accounts = sorted(set(current.keys()) | set(prior.keys()))

    headers = ["Konto", "Kontonamn", "Aktuellt", "Föreg. år", "Förändring SEK", "Förändring %"]
    rows: list[list[Any]] = []

    assets_cur = 0.0
    assets_pri = 0.0
    el_cur = 0.0
    el_pri = 0.0

    for _code, range_from, range_to, group_label in BR_GROUPS:
        group_rows: list[list[Any]] = []
        grp_cur = 0.0
        grp_pri = 0.0

        for acct in all_accounts:
            if not (range_from <= acct <= range_to):
                continue
            cur = round(current.get(acct, 0.0), 2)
            pri = round(prior.get(acct, 0.0), 2)
            if cur == 0 and pri == 0:
                continue
            change = round(cur - pri, 2)
            pct = _pct_change(cur, pri)
            name = accounts.get(acct, {}).get("name", "")
            group_rows.append([acct, name, cur, pri, change, pct])
            grp_cur += cur
            grp_pri += pri

        if group_rows:
            rows.append([None, f"— {group_label} —", None, None, None, None])
            rows.extend(group_rows)
            grp_change = round(grp_cur - grp_pri, 2)
            grp_pct = _pct_change(grp_cur, grp_pri)
            rows.append([
                None, f"Summa {group_label}",
                round(grp_cur, 2), round(grp_pri, 2),
                grp_change, grp_pct,
            ])
            rows.append([None, "", None, None, None, None])

            if range_from < 2000:
                assets_cur += grp_cur
                assets_pri += grp_pri
            else:
                el_cur += grp_cur
                el_pri += grp_pri

    a_change = round(assets_cur - assets_pri, 2)
    a_pct = _pct_change(assets_cur, assets_pri)
    e_change = round(el_cur - el_pri, 2)
    e_pct = _pct_change(el_cur, el_pri)

    rows.append([None, "SUMMA TILLGÅNGAR",
                 round(assets_cur, 2), round(assets_pri, 2), a_change, a_pct])
    rows.append([None, "SUMMA EGET KAPITAL OCH SKULDER",
                 round(el_cur, 2), round(el_pri, 2), e_change, e_pct])

    return {
        "headers": headers,
        "rows": rows,
        "period": period,
        "totals": {
            "assets": round(assets_cur, 2),
            "equity_and_liabilities": round(el_cur, 2),
        },
        "comparison_totals": {
            "assets": round(assets_pri, 2),
            "equity_and_liabilities": round(el_pri, 2),
        },
    }


# ----------------------------------------------------------------
# Flat / data-table report functions (for pivot tables etc.)
# ----------------------------------------------------------------

# Map dimension IDs to Swedish header names.
_DIM_HEADERS: dict[int, str] = {
    1: "Kostnadsställe",
    6: "Projekt",
}


def _sum_period_balances_with_dims(
    parsed: dict,
    year_offset: int,
    from_p: str,
    to_p: str,
    acct_from: int,
    acct_to: int,
    dim_ids: list[int],
) -> dict[tuple, float]:
    """Sum period_balances grouped by (account, dim_1, dim_6, ...).

    Returns dict mapping (account, dim_val_1, dim_val_2, ...) -> amount.
    """
    totals: dict[tuple, float] = defaultdict(float)
    for pb in parsed.get("period_balances", []):
        if pb.get("year_offset", 0) != year_offset:
            continue
        period = pb.get("period", "")
        account = pb.get("account")
        if account is None or not (acct_from <= account <= acct_to):
            continue
        if not (from_p <= period <= to_p):
            continue
        dims = pb.get("dimensions", {})
        key = (account,) + tuple(dims.get(d, "") for d in dim_ids)
        totals[key] += float(pb["amount"])
    return totals


def _compute_br_balances_with_dims(
    parsed: dict,
    year_offset: int,
    to_p: str,
    dim_ids: list[int],
) -> dict[tuple, float]:
    """Compute balance sheet balances grouped by (account, dims...).

    IB + accumulated period movements up to period.
    Uses object_opening_balances for dimension-aware IB when available.
    """
    balances: dict[tuple, float] = defaultdict(float)

    # Opening balances — use #OIB (object IB) if dims requested,
    # fall back to #IB (aggregate) for entries without dimensions.
    if dim_ids:
        for oib in parsed.get("object_opening_balances", []):
            if oib.get("year_offset", 0) != year_offset:
                continue
            acct = oib.get("account")
            if acct is None or not (1000 <= acct <= 2999):
                continue
            dims = oib.get("dimensions", {})
            key = (acct,) + tuple(dims.get(d, "") for d in dim_ids)
            balances[key] += float(oib["amount"])
    else:
        for ib in parsed.get("opening_balances", []):
            if ib.get("year_offset", 0) != year_offset:
                continue
            acct = ib.get("account")
            if acct is None or not (1000 <= acct <= 2999):
                continue
            key = (acct,)
            balances[key] += float(ib["amount"])

    # Period movements.
    for pb in parsed.get("period_balances", []):
        if pb.get("year_offset", 0) != year_offset:
            continue
        period = pb.get("period", "")
        acct = pb.get("account")
        if acct is None or not (1000 <= acct <= 2999):
            continue
        if period <= to_p:
            dims = pb.get("dimensions", {})
            key = (acct,) + tuple(dims.get(d, "") for d in dim_ids)
            balances[key] += float(pb["amount"])

    return balances


async def compute_income_statement_flat(
    client: FortnoxSIEClient,
    financial_year_id: int,
    from_period: str,
    to_period: str,
    include_dimensions: list[int] | None = None,
    include_prior_year: bool = False,
) -> dict[str, Any]:
    """Compute a flat income statement (RR) suitable for pivot tables.

    Returns one row per (account, dimension_combo) with no subtotals,
    group headers, or separator rows.

    Args:
        client: SIE client for fetching data from Fortnox.
        financial_year_id: Fortnox financial year ID.
        from_period: Start period inclusive, format "YYYY-MM".
        to_period: End period inclusive, format "YYYY-MM".
        include_dimensions: List of dimension IDs to include as columns
            (e.g. [1, 6] for Kostnadsställe + Projekt).
        include_prior_year: If True, add prior-year comparison columns.

    Returns:
        Dict with 'headers', 'rows', 'count', 'period'.
    """
    sie_text = await client.get_sie(sie_type=2, financial_year=financial_year_id)
    parsed = parse_sie(sie_text)

    from_p = from_period.replace("-", "")
    to_p = to_period.replace("-", "")
    dim_ids = include_dimensions or []

    # Sum current year.
    current = _sum_period_balances_with_dims(
        parsed, 0, from_p, to_p, 3000, 8999, dim_ids,
    )

    # Sum prior year if requested.
    prior: dict[tuple, float] = {}
    if include_prior_year:
        prior = _sum_period_balances_with_dims(
            parsed, -1, from_p, to_p, 3000, 8999, dim_ids,
        )

    accounts = parsed.get("accounts", {})

    # Build headers.
    headers: list[str] = ["Konto", "Kontonamn"]
    for d in dim_ids:
        headers.append(_DIM_HEADERS.get(d, f"Dim {d}"))
    headers.append("Belopp")
    if include_prior_year:
        headers.extend(["Föreg. år", "Förändring SEK", "Förändring %"])

    # Collect all unique keys from current + prior.
    all_keys = sorted(set(current.keys()) | set(prior.keys()))

    rows: list[list[Any]] = []
    for key in all_keys:
        acct = key[0]
        cur = round(current.get(key, 0.0), 2)
        pri = round(prior.get(key, 0.0), 2) if include_prior_year else 0.0
        if cur == 0 and pri == 0:
            continue

        acct_name = accounts.get(acct, {}).get("name", "")
        row: list[Any] = [acct, acct_name]

        # Dimension values.
        for i in range(len(dim_ids)):
            row.append(key[1 + i] if 1 + i < len(key) else "")

        row.append(cur)

        if include_prior_year:
            change = round(cur - pri, 2)
            pct = _pct_change(cur, pri)
            row.extend([pri, change, pct])

        rows.append(row)

    return {
        "headers": headers,
        "rows": rows,
        "count": len(rows),
        "period": f"{from_period} – {to_period}",
    }


async def compute_balance_sheet_flat(
    client: FortnoxSIEClient,
    financial_year_id: int,
    period: str,
    include_dimensions: list[int] | None = None,
    include_prior_year: bool = False,
) -> dict[str, Any]:
    """Compute a flat balance sheet (BR) suitable for pivot tables.

    Returns one row per (account, dimension_combo) with no subtotals,
    group headers, or separator rows.

    Args:
        client: SIE client for fetching data from Fortnox.
        financial_year_id: Fortnox financial year ID.
        period: Period to show balance for, format "YYYY-MM".
        include_dimensions: List of dimension IDs to include as columns.
        include_prior_year: If True, add prior-year comparison columns.

    Returns:
        Dict with 'headers', 'rows', 'count', 'period'.
    """
    sie_text = await client.get_sie(sie_type=2, financial_year=financial_year_id)
    parsed = parse_sie(sie_text)

    to_p = period.replace("-", "")
    dim_ids = include_dimensions or []

    current = _compute_br_balances_with_dims(parsed, 0, to_p, dim_ids)
    prior: dict[tuple, float] = {}
    if include_prior_year:
        prior = _compute_br_balances_with_dims(parsed, -1, to_p, dim_ids)

    accounts = parsed.get("accounts", {})

    # Build headers.
    headers: list[str] = ["Konto", "Kontonamn"]
    for d in dim_ids:
        headers.append(_DIM_HEADERS.get(d, f"Dim {d}"))
    headers.append("Saldo")
    if include_prior_year:
        headers.extend(["Föreg. år", "Förändring SEK", "Förändring %"])

    all_keys = sorted(set(current.keys()) | set(prior.keys()))

    rows: list[list[Any]] = []
    for key in all_keys:
        acct = key[0]
        cur = round(current.get(key, 0.0), 2)
        pri = round(prior.get(key, 0.0), 2) if include_prior_year else 0.0
        if cur == 0 and pri == 0:
            continue

        acct_name = accounts.get(acct, {}).get("name", "")
        row: list[Any] = [acct, acct_name]

        for i in range(len(dim_ids)):
            row.append(key[1 + i] if 1 + i < len(key) else "")

        row.append(cur)

        if include_prior_year:
            change = round(cur - pri, 2)
            pct = _pct_change(cur, pri)
            row.extend([pri, change, pct])

        rows.append(row)

    return {
        "headers": headers,
        "rows": rows,
        "count": len(rows),
        "period": period,
    }
