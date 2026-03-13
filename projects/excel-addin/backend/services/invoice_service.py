"""Invoice service — fetches and filters supplier/customer invoices.

Fetches all invoices from Fortnox (with optional date range), then
applies client-side status filtering. This avoids the Fortnox API
limitation where the 'filter' parameter is not always available
(e.g. in sandbox environments).

Status is derived from boolean/numeric fields on each invoice:
    - booked:     Booked == True
    - unbooked:   Booked == False
    - cancelled:  Cancel == True (supplier) / Cancelled == True (customer)
    - fullypaid:  Balance == 0 and not cancelled
    - unpaid:     Balance != 0 and not cancelled
    - unpaidoverdue: Balance != 0 and DueDate < today
"""

from datetime import date
from typing import Any

from fortnox_client import FortnoxClient


# ----------------------------------------------------------------
# Supplier invoices (LRK)
# ----------------------------------------------------------------

SUPPLIER_STATUS_OPTIONS = [
    "booked", "unbooked", "cancelled", "fullypaid", "unpaid", "unpaidoverdue",
]

# Columns to include in the LRK output (order matters for Excel).
LRK_COLUMNS = [
    ("GivenNumber", "Nr"),
    ("SupplierNumber", "Leverantörsnr"),
    ("SupplierName", "Leverantör"),
    ("InvoiceNumber", "Fakturanr"),
    ("InvoiceDate", "Fakturadatum"),
    ("DueDate", "Förfallodatum"),
    ("Total", "Belopp"),
    ("Balance", "Saldo"),
    ("Currency", "Valuta"),
    ("_status", "Status"),
    ("CostCenter", "Kostnadsställe"),
    ("Project", "Projekt"),
]


def _supplier_status(inv: dict) -> str:
    """Derive a human-readable status from supplier invoice fields."""
    if inv.get("Cancel"):
        return "Makulerad"
    if not inv.get("Booked"):
        return "Ej bokförd"
    balance = inv.get("Balance", 0) or 0
    if balance == 0:
        return "Betald"
    due = inv.get("DueDate", "")
    if due and due < date.today().isoformat():
        return "Förfallen"
    return "Obetald"


def _matches_supplier_filter(inv: dict, statuses: set[str]) -> bool:
    """Check if a supplier invoice matches any of the requested statuses."""
    if not statuses:
        return True

    booked = inv.get("Booked", False)
    cancelled = inv.get("Cancel", False)
    balance = inv.get("Balance", 0) or 0
    due = inv.get("DueDate", "")
    today = date.today().isoformat()

    for s in statuses:
        if s == "booked" and booked:
            return True
        if s == "unbooked" and not booked:
            return True
        if s == "cancelled" and cancelled:
            return True
        if s == "fullypaid" and balance == 0 and not cancelled:
            return True
        if s == "unpaid" and balance != 0 and not cancelled:
            return True
        if s == "unpaidoverdue" and balance != 0 and due and due < today:
            return True

    return False


async def fetch_supplier_invoices(
    client: FortnoxClient,
    from_date: str | None = None,
    to_date: str | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch supplier invoices with optional status filtering.

    Args:
        client: Fortnox API client.
        from_date: Start date (YYYY-MM-DD). Optional.
        to_date: End date (YYYY-MM-DD). Optional.
        statuses: List of status filters to include. If empty/None, fetches all.

    Returns:
        Dict with 'headers', 'rows', and 'count'.
    """
    params: dict[str, Any] = {}
    if from_date:
        params["fromdate"] = from_date
    if to_date:
        params["todate"] = to_date

    raw_invoices = await client.get_all_pages("/supplierinvoices", params=params)

    # Enrich with derived status field.
    for inv in raw_invoices:
        inv["_status"] = _supplier_status(inv)

    # Apply client-side status filter.
    status_set = set(statuses) if statuses else set()
    filtered = [
        inv for inv in raw_invoices
        if _matches_supplier_filter(inv, status_set)
    ]

    # Sort by invoice date descending.
    filtered.sort(key=lambda x: x.get("InvoiceDate", ""), reverse=True)

    # Map to output format.
    headers = [label for _, label in LRK_COLUMNS]
    rows = [
        [inv.get(key) for key, _ in LRK_COLUMNS]
        for inv in filtered
    ]

    return {"headers": headers, "rows": rows, "count": len(rows)}


# ----------------------------------------------------------------
# Customer invoices (KRK)
# ----------------------------------------------------------------

CUSTOMER_STATUS_OPTIONS = [
    "booked", "unbooked", "cancelled", "fullypaid", "unpaid", "unpaidoverdue",
]

# Columns to include in the KRK output.
KRK_COLUMNS = [
    ("DocumentNumber", "Dokumentnr"),
    ("CustomerNumber", "Kundnr"),
    ("CustomerName", "Kund"),
    ("InvoiceDate", "Fakturadatum"),
    ("DueDate", "Förfallodatum"),
    ("Total", "Belopp"),
    ("Balance", "Saldo"),
    ("Currency", "Valuta"),
    ("_status", "Status"),
    ("Sent", "Skickad"),
    ("CostCenter", "Kostnadsställe"),
    ("Project", "Projekt"),
]


def _customer_status(inv: dict) -> str:
    """Derive a human-readable status from customer invoice fields."""
    if inv.get("Cancelled"):
        return "Makulerad"
    if not inv.get("Booked"):
        return "Ej bokförd"
    balance = inv.get("Balance", 0) or 0
    if balance == 0:
        return "Betald"
    due = inv.get("DueDate", "")
    if due and due < date.today().isoformat():
        return "Förfallen"
    return "Obetald"


def _matches_customer_filter(inv: dict, statuses: set[str]) -> bool:
    """Check if a customer invoice matches any of the requested statuses."""
    if not statuses:
        return True

    booked = inv.get("Booked", False)
    cancelled = inv.get("Cancelled", False)
    balance = inv.get("Balance", 0) or 0
    due = inv.get("DueDate", "")
    today = date.today().isoformat()

    for s in statuses:
        if s == "booked" and booked:
            return True
        if s == "unbooked" and not booked:
            return True
        if s == "cancelled" and cancelled:
            return True
        if s == "fullypaid" and balance == 0 and not cancelled:
            return True
        if s == "unpaid" and balance != 0 and not cancelled:
            return True
        if s == "unpaidoverdue" and balance != 0 and due and due < today:
            return True

    return False


async def fetch_customer_invoices(
    client: FortnoxClient,
    from_date: str | None = None,
    to_date: str | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch customer invoices with optional status filtering.

    Same pattern as fetch_supplier_invoices but for the /invoices endpoint.
    """
    params: dict[str, Any] = {}
    if from_date:
        params["fromdate"] = from_date
    if to_date:
        params["todate"] = to_date

    raw_invoices = await client.get_all_pages("/invoices", params=params)

    for inv in raw_invoices:
        inv["_status"] = _customer_status(inv)

    status_set = set(statuses) if statuses else set()
    filtered = [
        inv for inv in raw_invoices
        if _matches_customer_filter(inv, status_set)
    ]

    filtered.sort(key=lambda x: x.get("InvoiceDate", ""), reverse=True)

    headers = [label for _, label in KRK_COLUMNS]
    rows = [
        [inv.get(key) for key, _ in KRK_COLUMNS]
        for inv in filtered
    ]

    return {"headers": headers, "rows": rows, "count": len(rows)}
