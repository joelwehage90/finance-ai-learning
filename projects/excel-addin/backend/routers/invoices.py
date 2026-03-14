"""Invoice endpoints — LRK (supplier) and KRK (customer) data for Excel."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth import get_current_provider
from providers.base import AccountingProvider
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
    columns: Optional[str] = Query(
        None,
        description="Comma-separated column labels to include (e.g. Nr,Leverantör,Belopp)",
    ),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Fetch supplier invoices (Leverantörsreskontra) for Excel output."""
    status_list = statuses.split(",") if statuses else None
    col_list = columns.split(",") if columns else None

    return await fetch_supplier_invoices(
        provider=provider,
        from_date=from_date,
        to_date=to_date,
        statuses=status_list,
        selected_columns=col_list,
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
    columns: Optional[str] = Query(
        None,
        description="Comma-separated column labels to include (e.g. Dokumentnr,Kund,Belopp)",
    ),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Fetch customer invoices (Kundreskontra) for Excel output."""
    status_list = statuses.split(",") if statuses else None
    col_list = columns.split(",") if columns else None

    return await fetch_customer_invoices(
        provider=provider,
        from_date=from_date,
        to_date=to_date,
        statuses=status_list,
        selected_columns=col_list,
    )
