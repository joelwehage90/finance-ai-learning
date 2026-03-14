"""Huvudbok endpoint — general ledger from SIE4 voucher data."""

from typing import Optional

from fastapi import APIRouter, Query

from utils import parse_dimensions

from services.huvudbok_service import compute_general_ledger

router = APIRouter(tags=["huvudbok"])


@router.get("/huvudbok")
async def get_huvudbok(
    financial_year_id: int = Query(..., description="Fortnox financial year ID"),
    from_account: int = Query(..., description="Start account number (e.g. 1000)"),
    to_account: int = Query(..., description="End account number (e.g. 1999)"),
    from_period: str = Query(..., description="Start period (YYYY-MM)"),
    to_period: str = Query(..., description="End period (YYYY-MM)"),
    cost_center: Optional[str] = Query(None, description="Filter by cost center"),
    project: Optional[str] = Query(None, description="Filter by project"),
    include_dimensions: Optional[str] = Query(
        None,
        description="Comma-separated dimension IDs to include as columns (e.g. 1,6)",
    ),
):
    """Compute a general ledger (Huvudbok) from SIE4 data.

    Returns all voucher transactions for accounts in the specified range
    and period, with running balance per account. Optionally includes
    dimension columns (Kostnadsställe, Projekt).
    """
    from main import sie_client

    dim_list = parse_dimensions(include_dimensions)

    return await compute_general_ledger(
        client=sie_client,
        financial_year_id=financial_year_id,
        from_account=from_account,
        to_account=to_account,
        from_period=from_period,
        to_period=to_period,
        cost_center=cost_center,
        project=project,
        include_dimensions=dim_list,
    )
