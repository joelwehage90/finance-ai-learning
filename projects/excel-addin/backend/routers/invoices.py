"""Invoice endpoints — LRK (supplier) and KRK (customer) data for Excel."""

from fastapi import APIRouter, Query
from typing import Optional

from services.invoice_service import (
    fetch_supplier_invoices,
    fetch_customer_invoices,
)

router = APIRouter(tags=["invoices"])


@router.get("/lrk")
async def get_lrk(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    statuses: Optional[str] = Query(
        None,
        description="Comma-separated status filters: booked,unbooked,cancelled,"
                    "fullypaid,unpaid,unpaidoverdue,authorizationnotstarted",
    ),
):
    """Fetch supplier invoices (Leverantörsreskontra) for Excel output.

    Supports multi-status filtering by making parallel Fortnox API calls
    and deduplicating the results.
    """
    from main import fortnox_client

    status_list = statuses.split(",") if statuses else None

    return await fetch_supplier_invoices(
        client=fortnox_client,
        from_date=from_date,
        to_date=to_date,
        statuses=status_list,
    )


@router.get("/krk")
async def get_krk(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    statuses: Optional[str] = Query(
        None,
        description="Comma-separated status filters: booked,unbooked,cancelled,"
                    "fullypaid,unpaid,unpaidoverdue",
    ),
):
    """Fetch customer invoices (Kundreskontra) for Excel output.

    Same pattern as LRK but for the /invoices endpoint.
    """
    from main import fortnox_client

    status_list = statuses.split(",") if statuses else None

    return await fetch_customer_invoices(
        client=fortnox_client,
        from_date=from_date,
        to_date=to_date,
        statuses=status_list,
    )
