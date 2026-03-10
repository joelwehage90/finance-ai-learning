"""Fortnox MCP Server — Exposes Fortnox API as tools for Claude."""

import os
import json
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastmcp import FastMCP

# Ensure imports work regardless of working directory
_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR))

from fortnox_client import FortnoxClient

# Load .env from the server's own directory
load_dotenv(_THIS_DIR / ".env")

mcp = FastMCP(
    "Fortnox",
    instructions=(
        "Fortnox accounting API integration for Swedish companies. "
        "Use these tools to query invoices, customers, accounts and "
        "company information from Fortnox. All financial data follows "
        "the BAS account plan (Swedish standard)."
    ),
)

# Lazy-initialized client (created on first tool call)
_client: Optional[FortnoxClient] = None


def _get_client() -> FortnoxClient:
    """Get or create the Fortnox API client."""
    global _client
    if _client is None:
        client_id = os.environ["FORTNOX_CLIENT_ID"]
        client_secret = os.environ["FORTNOX_CLIENT_SECRET"]
        tenant_id = os.environ["FORTNOX_TENANT_ID"]
        _client = FortnoxClient(client_id, client_secret, tenant_id)
    return _client


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


if __name__ == "__main__":
    mcp.run()
