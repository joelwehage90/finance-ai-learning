"""Huvudbok endpoint — general ledger from SIE4 voucher data."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth import get_current_provider
from providers.base import AccountingProvider
from utils import parse_dimensions

from services.huvudbok_service import compute_general_ledger

router = APIRouter(tags=["huvudbok"])


@router.get("/huvudbok")
async def get_huvudbok(
    financial_year_id: int = Query(..., description="Financial year ID"),
    from_account: int = Query(..., description="Start account number (e.g. 1000)"),
    to_account: int = Query(..., description="End account number (e.g. 1999)"),
    from_period: str = Query(..., description="Start period (YYYY-MM)", pattern=r"^\d{4}-\d{2}$"),
    to_period: str = Query(..., description="End period (YYYY-MM)", pattern=r"^\d{4}-\d{2}$"),
    cost_center: Optional[str] = Query(None, description="Filter by cost center"),
    project: Optional[str] = Query(None, description="Filter by project"),
    include_dimensions: Optional[str] = Query(
        None,
        description="Comma-separated dimension IDs to include as columns (e.g. 1,6)",
    ),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Compute a general ledger (Huvudbok) from SIE4 data."""
    dim_list = parse_dimensions(include_dimensions)

    return await compute_general_ledger(
        provider=provider,
        financial_year_id=financial_year_id,
        from_account=from_account,
        to_account=to_account,
        from_period=from_period,
        to_period=to_period,
        cost_center=cost_center,
        project=project,
        include_dimensions=dim_list,
    )
