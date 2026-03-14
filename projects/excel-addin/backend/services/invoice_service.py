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

from providers.base import AccountingProvider


# ----------------------------------------------------------------
# Shared helpers (parameterised on cancelled_key)
# ----------------------------------------------------------------

def _derive_status(inv: dict, cancelled_key: str = "Cancel") -> str:
    """Derive a human-readable status from invoice fields.

    Args:
        inv: Raw invoice dict from Fortnox.
        cancelled_key: Field name for the cancelled flag
            ("Cancel" for supplier, "Cancelled" for customer).
    """
    if inv.get(cancelled_key):
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


def _matches_filter(
    inv: dict, statuses: set[str], cancelled_key: str = "Cancel",
) -> bool:
    """Check if an invoice matches any of the requested statuses.

    Args:
        inv: Raw invoice dict from Fortnox.
        statuses: Set of status strings to match. Empty = match all.
        cancelled_key: Field name for the cancelled flag.
    """
    if not statuses:
        return True

    booked = inv.get("Booked", False)
    cancelled = inv.get(cancelled_key, False)
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


async def _fetch_invoices(
    provider: AccountingProvider,
    endpoint: str,
    columns: list[tuple[str, str]],
    cancelled_key: str,
    from_date: str | None = None,
    to_date: str | None = None,
    statuses: list[str] | None = None,
    selected_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch and filter invoices from a Fortnox endpoint.

    Args:
        provider: Accounting provider for fetching invoices.
        endpoint: API path (e.g. "/supplierinvoices" or "/invoices").
        columns: Ordered list of (api_key, swedish_label) tuples.
        cancelled_key: Field name for the cancelled flag.
        from_date: Start date (YYYY-MM-DD). Optional.
        to_date: End date (YYYY-MM-DD). Optional.
        statuses: List of status filters to include. If empty/None, all.
        selected_columns: Which column labels to include. If None, all.

    Returns:
        Dict with 'headers', 'rows', and 'count'.
    """
    params: dict[str, Any] = {}
    if from_date:
        params["fromdate"] = from_date
    if to_date:
        params["todate"] = to_date

    raw_invoices = await provider.get_invoices(endpoint, params=params)

    # Enrich with derived status field.
    for inv in raw_invoices:
        inv["_status"] = _derive_status(inv, cancelled_key)

    # Apply client-side status filter.
    status_set = set(statuses) if statuses else set()
    filtered = [
        inv for inv in raw_invoices
        if _matches_filter(inv, status_set, cancelled_key)
    ]

    # Sort by invoice date descending.
    filtered.sort(key=lambda x: x.get("InvoiceDate", ""), reverse=True)

    # Filter columns if requested, otherwise include all.
    cols = columns
    if selected_columns:
        col_set = set(selected_columns)
        cols = [(key, label) for key, label in columns if label in col_set]

    # Map to output format.
    headers = [label for _, label in cols]
    rows = [
        [inv.get(key) for key, _ in cols]
        for inv in filtered
    ]

    return {"headers": headers, "rows": rows, "count": len(rows)}


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


async def fetch_supplier_invoices(
    provider: AccountingProvider,
    from_date: str | None = None,
    to_date: str | None = None,
    statuses: list[str] | None = None,
    selected_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch supplier invoices with optional status filtering."""
    return await _fetch_invoices(
        provider, "/supplierinvoices", LRK_COLUMNS, "Cancel",
        from_date, to_date, statuses, selected_columns,
    )


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


async def fetch_customer_invoices(
    provider: AccountingProvider,
    from_date: str | None = None,
    to_date: str | None = None,
    statuses: list[str] | None = None,
    selected_columns: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch customer invoices with optional status filtering."""
    return await _fetch_invoices(
        provider, "/invoices", KRK_COLUMNS, "Cancelled",
        from_date, to_date, statuses, selected_columns,
    )
