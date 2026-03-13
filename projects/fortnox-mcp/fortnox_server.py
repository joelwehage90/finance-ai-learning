"""Fortnox MCP Server — Exposes Fortnox API as tools for Claude.

Provides tools for querying invoices, customers, accounts, and
financial reports from Fortnox. Includes LRK/KRK ledgers and
RR/BR reports computed from SIE2 data.
"""

import os
import json
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastmcp import FastMCP

# Ensure imports work regardless of working directory.
# We need fortnox-mcp (this dir), sie-pipeline (SIE parsing),
# and excel-addin services (RR/BR computation).
_THIS_DIR = Path(__file__).resolve().parent
_SIE_PIPELINE_DIR = _THIS_DIR.parent / "sie-pipeline"
_EXCEL_SERVICES_DIR = _THIS_DIR.parent / "excel-addin" / "backend" / "services"
sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_SIE_PIPELINE_DIR))
sys.path.insert(0, str(_EXCEL_SERVICES_DIR))

from fortnox_client import FortnoxClient
from fortnox_sie_client import FortnoxSIEClient

# Load .env from the server's own directory
load_dotenv(_THIS_DIR / ".env")

mcp = FastMCP(
    "Fortnox",
    instructions=(
        "Fortnox accounting API integration for Swedish companies. "
        "Use these tools to query invoices, customers, accounts, "
        "company information, and financial reports from Fortnox. "
        "Includes LRK (leverantörsreskontra), KRK (kundreskontra), "
        "Resultaträkning and Balansräkning. All financial data follows "
        "the BAS account plan (Swedish standard)."
    ),
)

# Lazy-initialized clients (created on first tool call)
_client: Optional[FortnoxClient] = None
_sie_client: Optional[FortnoxSIEClient] = None


def _get_credentials() -> tuple[str, str, str]:
    """Get Fortnox credentials from environment."""
    return (
        os.environ["FORTNOX_CLIENT_ID"],
        os.environ["FORTNOX_CLIENT_SECRET"],
        os.environ["FORTNOX_TENANT_ID"],
    )


def _get_client() -> FortnoxClient:
    """Get or create the Fortnox API client."""
    global _client
    if _client is None:
        _client = FortnoxClient(*_get_credentials())
    return _client


def _get_sie_client() -> FortnoxSIEClient:
    """Get or create the Fortnox SIE client."""
    global _sie_client
    if _sie_client is None:
        _sie_client = FortnoxSIEClient(*_get_credentials())
    return _sie_client


def _format_response(data: dict | list, summary: str = "") -> str:
    """Format API response as readable JSON string for Claude."""
    output = ""
    if summary:
        output += summary + "\n\n"
    output += json.dumps(data, indent=2, ensure_ascii=False)
    return output


@mcp.tool()
async def list_invoices(
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    customer_name: Optional[str] = None,
    limit: int = 25,
) -> str:
    """List customer invoices from Fortnox.

    Args:
        status: Filter by status. Options: "unpaid", "unpaidoverdue",
            "unbooked", "cancelled", "fullypaid". Leave empty for all.
        from_date: Start date filter (YYYY-MM-DD).
        to_date: End date filter (YYYY-MM-DD).
        customer_name: Filter by customer name (partial match).
        limit: Max number of invoices to return (default 25, max 500).
    """
    client = _get_client()
    params: dict = {"limit": min(limit, 500)}

    if status:
        params["filter"] = status
    if from_date:
        params["fromdate"] = from_date
    if to_date:
        params["todate"] = to_date
    if customer_name:
        params["customername"] = customer_name

    data = await client.get("/invoices", params=params)

    invoices = data.get("Invoices", [])
    meta = data.get("MetaInformation", {})
    total = meta.get("@TotalResources", len(invoices))

    summary = f"Visar {len(invoices)} av {total} fakturor."
    return _format_response(invoices, summary)


@mcp.tool()
async def get_invoice(document_number: str) -> str:
    """Get full details for a specific invoice.

    Args:
        document_number: The invoice document number (e.g. "1001").
    """
    client = _get_client()
    data = await client.get(f"/invoices/{document_number}")
    invoice = data.get("Invoice", data)
    return _format_response(invoice)


@mcp.tool()
async def list_customers(
    search: Optional[str] = None,
    limit: int = 25,
) -> str:
    """List customers from Fortnox.

    Args:
        search: Search by customer name (partial match).
        limit: Max number of customers to return (default 25, max 500).
    """
    client = _get_client()
    params: dict = {"limit": min(limit, 500)}

    if search:
        params["name"] = search

    data = await client.get("/customers", params=params)

    customers = data.get("Customers", [])
    meta = data.get("MetaInformation", {})
    total = meta.get("@TotalResources", len(customers))

    summary = f"Visar {len(customers)} av {total} kunder."
    return _format_response(customers, summary)


@mcp.tool()
async def get_account_balances(
    financial_year_date: Optional[str] = None,
    from_account: Optional[int] = None,
    to_account: Optional[int] = None,
) -> str:
    """Get account balances from the chart of accounts.

    Returns accounts with opening and closing balances for the
    specified financial year. Uses BAS account plan.

    Args:
        financial_year_date: A date within the financial year (YYYY-MM-DD).
            Defaults to current year if not specified.
        from_account: Filter from account number (e.g. 3000 for revenue).
        to_account: Filter to account number (e.g. 3999).
    """
    client = _get_client()
    params: dict = {"limit": 500}

    if financial_year_date:
        params["financialyeardate"] = financial_year_date
    if from_account:
        params["accountnumberfrom"] = from_account
    if to_account:
        params["accountnumberto"] = to_account

    data = await client.get("/accounts", params=params)

    accounts = data.get("Accounts", [])
    meta = data.get("MetaInformation", {})
    total = meta.get("@TotalResources", len(accounts))

    summary = f"Visar {len(accounts)} av {total} konton."
    return _format_response(accounts, summary)


@mcp.tool()
async def list_supplier_invoices(
    status: Optional[str] = None,
    supplier_name: Optional[str] = None,
    last_modified: Optional[str] = None,
    limit: int = 25,
) -> str:
    """List supplier invoices (leverantörsfakturor) from Fortnox.

    Note: fromdate/todate filtering is NOT supported for supplier invoices.
    Use last_modified for incremental queries instead.

    Args:
        status: Filter by status. Options: "unpaid", "unpaidoverdue",
            "unbooked", "cancelled", "fullypaid". Leave empty for all.
        supplier_name: Filter by supplier name (partial match).
        last_modified: Only return invoices modified after this timestamp
            (format: "YYYY-MM-DD HH:MM").
        limit: Max number of invoices to return (default 25, max 500).
    """
    client = _get_client()
    params: dict = {"limit": min(limit, 500)}

    if status:
        params["filter"] = status
    if supplier_name:
        params["suppliername"] = supplier_name
    if last_modified:
        params["lastmodified"] = last_modified

    data = await client.get("/supplierinvoices", params=params)

    invoices = data.get("SupplierInvoices", [])
    meta = data.get("MetaInformation", {})
    total = meta.get("@TotalResources", len(invoices))

    summary = f"Visar {len(invoices)} av {total} leverantörsfakturor."
    return _format_response(invoices, summary)


@mcp.tool()
async def get_supplier_invoice(given_number: str) -> str:
    """Get full details for a specific supplier invoice.

    Args:
        given_number: The supplier invoice number (GivenNumber).
    """
    client = _get_client()
    data = await client.get(f"/supplierinvoices/{given_number}")
    invoice = data.get("SupplierInvoice", data)
    return _format_response(invoice)


@mcp.tool()
async def get_company_info() -> str:
    """Get company information from Fortnox.

    Returns company name, org number, address, and other basic details.
    """
    client = _get_client()
    data = await client.get("/companyinformation")
    info = data.get("CompanyInformation", data)
    return _format_response(info)


# ----------------------------------------------------------------
# Ledger tools — LRK (supplier) and KRK (customer) with all invoices
# ----------------------------------------------------------------

@mcp.tool()
async def get_lrk(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    statuses: Optional[str] = None,
) -> str:
    """Get full leverantörsreskontra (supplier invoice ledger).

    Fetches ALL supplier invoices (paginated), enriches with derived
    status, and optionally filters client-side. Returns a complete
    table suitable for analysis.

    Args:
        from_date: Start date filter (YYYY-MM-DD). Optional.
        to_date: End date filter (YYYY-MM-DD). Optional.
        statuses: Comma-separated status filters. Options:
            booked, unbooked, cancelled, fullypaid, unpaid, unpaidoverdue.
            Leave empty for all invoices.
    """
    from invoice_service import fetch_supplier_invoices

    client = _get_client()
    status_list = statuses.split(",") if statuses else None

    result = await fetch_supplier_invoices(
        client=client,
        from_date=from_date,
        to_date=to_date,
        statuses=status_list,
    )

    summary = f"Leverantörsreskontra: {result['count']} fakturor."
    if from_date or to_date:
        summary += f" Period: {from_date or '...'} – {to_date or '...'}."
    if statuses:
        summary += f" Filter: {statuses}."

    # Format as readable table for Claude.
    return _format_ledger(result["headers"], result["rows"], summary)


@mcp.tool()
async def get_krk(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    statuses: Optional[str] = None,
) -> str:
    """Get full kundreskontra (customer invoice ledger).

    Fetches ALL customer invoices (paginated), enriches with derived
    status, and optionally filters client-side. Returns a complete
    table suitable for analysis.

    Args:
        from_date: Start date filter (YYYY-MM-DD). Optional.
        to_date: End date filter (YYYY-MM-DD). Optional.
        statuses: Comma-separated status filters. Options:
            booked, unbooked, cancelled, fullypaid, unpaid, unpaidoverdue.
            Leave empty for all invoices.
    """
    from invoice_service import fetch_customer_invoices

    client = _get_client()
    status_list = statuses.split(",") if statuses else None

    result = await fetch_customer_invoices(
        client=client,
        from_date=from_date,
        to_date=to_date,
        statuses=status_list,
    )

    summary = f"Kundreskontra: {result['count']} fakturor."
    if from_date or to_date:
        summary += f" Period: {from_date or '...'} – {to_date or '...'}."
    if statuses:
        summary += f" Filter: {statuses}."

    return _format_ledger(result["headers"], result["rows"], summary)


def _format_ledger(headers: list, rows: list, summary: str) -> str:
    """Format ledger data as a readable text table for Claude."""
    output = summary + "\n\n"
    output += " | ".join(str(h) for h in headers) + "\n"
    output += "-" * 80 + "\n"
    for row in rows:
        output += " | ".join(str(v) if v is not None else "" for v in row) + "\n"
    return output


# ----------------------------------------------------------------
# Financial report tools — RR and BR from SIE2
# ----------------------------------------------------------------

@mcp.tool()
async def get_resultatrakning(
    from_period: str,
    to_period: str,
    financial_year_date: Optional[str] = None,
) -> str:
    """Get Resultaträkning (income statement) from Fortnox SIE2 data.

    Computes the income statement by summing period balances for
    accounts 3000-8999, grouped by BAS account classes.

    Args:
        from_period: Start period inclusive (YYYY-MM), e.g. "2026-01".
        to_period: End period inclusive (YYYY-MM), e.g. "2026-03".
        financial_year_date: A date within the financial year (YYYY-MM-DD).
            Defaults to first day of from_period if not specified.
    """
    from sie_report_service import compute_income_statement

    sie_client = _get_sie_client()

    # Resolve financial year ID.
    fy_date = financial_year_date or f"{from_period}-01"
    fy_id = await sie_client.get_financial_year_id(fy_date)

    result = await compute_income_statement(
        client=sie_client,
        financial_year_id=fy_id,
        from_period=from_period,
        to_period=to_period,
    )

    return _format_report(
        f"Resultaträkning {result['period']}",
        result["headers"],
        result["rows"],
        f"Resultat: {result['total']:,.2f} SEK",
    )


@mcp.tool()
async def get_balansrakning(
    period: str,
    financial_year_date: Optional[str] = None,
) -> str:
    """Get Balansräkning (balance sheet) from Fortnox SIE2 data.

    Computes the balance sheet by adding opening balances (IB) to
    accumulated period movements up to the specified period, for
    accounts 1000-2999.

    Args:
        period: Balance date period (YYYY-MM), e.g. "2026-03".
        financial_year_date: A date within the financial year (YYYY-MM-DD).
            Defaults to first day of period if not specified.
    """
    from sie_report_service import compute_balance_sheet

    sie_client = _get_sie_client()

    fy_date = financial_year_date or f"{period}-01"
    fy_id = await sie_client.get_financial_year_id(fy_date)

    result = await compute_balance_sheet(
        client=sie_client,
        financial_year_id=fy_id,
        period=period,
    )

    totals = result.get("totals", {})
    footer = (
        f"Summa tillgångar: {totals.get('assets', 0):,.2f} SEK\n"
        f"Summa EK + skulder: {totals.get('equity_and_liabilities', 0):,.2f} SEK"
    )

    return _format_report(
        f"Balansräkning per {result['period']}",
        result["headers"],
        result["rows"],
        footer,
    )


def _format_report(title: str, headers: list, rows: list, footer: str) -> str:
    """Format a financial report as readable text for Claude."""
    output = f"=== {title} ===\n\n"

    for row in rows:
        account = row[0]
        name = row[1] or ""
        amount = row[2]

        if account is None and amount is None:
            # Section header or blank row.
            if name:
                output += f"\n{name}\n"
        elif account is None and amount is not None:
            # Subtotal or total row — bold-style.
            output += f"{'':>6s} {name:<45s} {amount:>15,.2f}\n"
        else:
            # Regular account row.
            output += f"{account:>6d} {name:<45s} {amount:>15,.2f}\n"

    output += f"\n{footer}\n"
    return output


# ----------------------------------------------------------------
# Huvudbok (General Ledger) from SIE4
# ----------------------------------------------------------------

@mcp.tool()
async def get_huvudbok(
    from_account: int,
    to_account: int,
    from_period: str,
    to_period: str,
    cost_center: Optional[str] = None,
    financial_year_date: Optional[str] = None,
) -> str:
    """Get Huvudbok (general ledger) from Fortnox SIE4 data.

    Shows all voucher transactions for the selected account range
    and period, with running balance per account. Each account block
    shows opening balance, individual transactions, and closing balance.

    Args:
        from_account: Start of account range (e.g. 1000).
        to_account: End of account range (e.g. 1999).
        from_period: Start period inclusive (YYYY-MM), e.g. "2026-01".
        to_period: End period inclusive (YYYY-MM), e.g. "2026-03".
        cost_center: Optional cost center filter (dimension 1).
        financial_year_date: A date within the financial year (YYYY-MM-DD).
            Defaults to first day of from_period if not specified.
    """
    from huvudbok_service import compute_general_ledger

    sie_client = _get_sie_client()

    fy_date = financial_year_date or f"{from_period}-01"
    fy_id = await sie_client.get_financial_year_id(fy_date)

    result = await compute_general_ledger(
        client=sie_client,
        financial_year_id=fy_id,
        from_account=from_account,
        to_account=to_account,
        from_period=from_period,
        to_period=to_period,
        cost_center=cost_center,
    )

    summary = (
        f"Huvudbok konto {from_account}–{to_account}, "
        f"period {result['period']}: {result['count']} rader."
    )
    return _format_ledger(result["headers"], result["rows"], summary)


# ----------------------------------------------------------------
# Comparative reports — RR and BR with prior year
# ----------------------------------------------------------------

@mcp.tool()
async def get_resultatrakning_comparative(
    from_period: str,
    to_period: str,
    financial_year_date: Optional[str] = None,
) -> str:
    """Get comparative Resultaträkning (income statement) with prior year.

    Shows current year, prior year, change in SEK and percentage
    for each account, grouped by BAS account classes.

    Args:
        from_period: Start period inclusive (YYYY-MM), e.g. "2026-01".
        to_period: End period inclusive (YYYY-MM), e.g. "2026-03".
        financial_year_date: A date within the financial year (YYYY-MM-DD).
            Defaults to first day of from_period if not specified.
    """
    from sie_report_service import compute_income_statement_comparative

    sie_client = _get_sie_client()

    fy_date = financial_year_date or f"{from_period}-01"
    fy_id = await sie_client.get_financial_year_id(fy_date)

    result = await compute_income_statement_comparative(
        client=sie_client,
        financial_year_id=fy_id,
        from_period=from_period,
        to_period=to_period,
    )

    return _format_comparative_report(
        f"Resultaträkning (jämförelse) {result['period']}",
        result["rows"],
        f"Resultat aktuellt: {result['total']:,.2f} SEK, "
        f"föreg. år: {result['comparison_total']:,.2f} SEK",
    )


@mcp.tool()
async def get_balansrakning_comparative(
    period: str,
    financial_year_date: Optional[str] = None,
) -> str:
    """Get comparative Balansräkning (balance sheet) with prior year.

    Shows current year, prior year, change in SEK and percentage
    for each account, grouped by BR categories.

    Args:
        period: Balance date period (YYYY-MM), e.g. "2026-03".
        financial_year_date: A date within the financial year (YYYY-MM-DD).
            Defaults to first day of period if not specified.
    """
    from sie_report_service import compute_balance_sheet_comparative

    sie_client = _get_sie_client()

    fy_date = financial_year_date or f"{period}-01"
    fy_id = await sie_client.get_financial_year_id(fy_date)

    result = await compute_balance_sheet_comparative(
        client=sie_client,
        financial_year_id=fy_id,
        period=period,
    )

    totals = result.get("totals", {})
    comp = result.get("comparison_totals", {})
    footer = (
        f"Tillgångar: {totals.get('assets', 0):,.2f} SEK "
        f"(föreg. år: {comp.get('assets', 0):,.2f})\n"
        f"EK + skulder: {totals.get('equity_and_liabilities', 0):,.2f} SEK "
        f"(föreg. år: {comp.get('equity_and_liabilities', 0):,.2f})"
    )

    return _format_comparative_report(
        f"Balansräkning (jämförelse) per {result['period']}",
        result["rows"],
        footer,
    )


def _format_comparative_report(title: str, rows: list, footer: str) -> str:
    """Format a comparative report as readable text for Claude."""
    output = f"=== {title} ===\n\n"
    output += f"{'Konto':>6} {'Kontonamn':<35} {'Aktuellt':>12} {'Föreg.år':>12} {'Förändring':>12} {'%':>8}\n"
    output += "-" * 90 + "\n"

    for row in rows:
        account = row[0]
        name = row[1] or ""
        current = row[2]
        prior = row[3]
        change = row[4]
        pct = row[5]

        if account is None and current is None:
            # Section header or blank row.
            if name:
                output += f"\n{name}\n"
        elif account is None and current is not None:
            # Subtotal or total row.
            pct_str = f"{pct:.1f}%" if pct is not None else "—"
            output += (
                f"{'':>6} {name:<35} {current:>12,.2f} {prior:>12,.2f} "
                f"{change:>12,.2f} {pct_str:>8}\n"
            )
        else:
            # Regular account row.
            pct_str = f"{pct:.1f}%" if pct is not None else "—"
            cur_str = f"{current:,.2f}" if current else "0.00"
            pri_str = f"{prior:,.2f}" if prior else "0.00"
            chg_str = f"{change:,.2f}" if change else "0.00"
            output += (
                f"{account:>6d} {name:<35} {cur_str:>12} {pri_str:>12} "
                f"{chg_str:>12} {pct_str:>8}\n"
            )

    output += f"\n{footer}\n"
    return output


if __name__ == "__main__":
    mcp.run()
