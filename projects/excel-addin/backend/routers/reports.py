"""Report endpoints — Resultaträkning and Balansräkning from SIE2.

Includes standard, comparative (vs prior year), and flat (for pivot)
versions.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth import get_current_provider
from providers.base import AccountingProvider
from utils import parse_dimensions

from services.sie_report_service import (
    compute_income_statement,
    compute_balance_sheet,
    compute_income_statement_comparative,
    compute_balance_sheet_comparative,
    compute_income_statement_flat,
    compute_balance_sheet_flat,
)

router = APIRouter(tags=["reports"])


@router.get("/rr")
async def get_resultatrakning(
    financial_year_id: int = Query(..., description="Financial year ID"),
    from_period: str = Query(..., description="Start period (YYYY-MM)"),
    to_period: str = Query(..., description="End period (YYYY-MM)"),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Compute an income statement (Resultaträkning) from SIE2 data."""
    return await compute_income_statement(
        provider=provider,
        financial_year_id=financial_year_id,
        from_period=from_period,
        to_period=to_period,
    )


@router.get("/br")
async def get_balansrakning(
    financial_year_id: int = Query(..., description="Financial year ID"),
    period: str = Query(..., description="Balance date period (YYYY-MM)"),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Compute a balance sheet (Balansräkning) from SIE2 data."""
    return await compute_balance_sheet(
        provider=provider,
        financial_year_id=financial_year_id,
        period=period,
    )


@router.get("/rr-comparative")
async def get_resultatrakning_comparative(
    financial_year_id: int = Query(..., description="Financial year ID"),
    from_period: str = Query(..., description="Start period (YYYY-MM)"),
    to_period: str = Query(..., description="End period (YYYY-MM)"),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Comparative income statement — current year vs prior year."""
    return await compute_income_statement_comparative(
        provider=provider,
        financial_year_id=financial_year_id,
        from_period=from_period,
        to_period=to_period,
    )


@router.get("/br-comparative")
async def get_balansrakning_comparative(
    financial_year_id: int = Query(..., description="Financial year ID"),
    period: str = Query(..., description="Balance date period (YYYY-MM)"),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Comparative balance sheet — current year vs prior year."""
    return await compute_balance_sheet_comparative(
        provider=provider,
        financial_year_id=financial_year_id,
        period=period,
    )


# ----------------------------------------------------------------
# Flat / data-table endpoints (for pivot tables)
# ----------------------------------------------------------------


@router.get("/rr-flat")
async def get_resultatrakning_flat(
    financial_year_id: int = Query(..., description="Financial year ID"),
    from_period: str = Query(..., description="Start period (YYYY-MM)"),
    to_period: str = Query(..., description="End period (YYYY-MM)"),
    dimensions: Optional[str] = Query(
        None, description="Comma-separated dimension IDs to include (e.g. 1,6)"
    ),
    include_prior_year: bool = Query(False, description="Include prior year columns"),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Flat income statement — one row per account/dimension combo."""
    dim_list = parse_dimensions(dimensions)

    return await compute_income_statement_flat(
        provider=provider,
        financial_year_id=financial_year_id,
        from_period=from_period,
        to_period=to_period,
        include_dimensions=dim_list,
        include_prior_year=include_prior_year,
    )


@router.get("/br-flat")
async def get_balansrakning_flat(
    financial_year_id: int = Query(..., description="Financial year ID"),
    period: str = Query(..., description="Balance date period (YYYY-MM)"),
    dimensions: Optional[str] = Query(
        None, description="Comma-separated dimension IDs to include (e.g. 1,6)"
    ),
    include_prior_year: bool = Query(False, description="Include prior year columns"),
    provider: AccountingProvider = Depends(get_current_provider),
):
    """Flat balance sheet — one row per account/dimension combo."""
    dim_list = parse_dimensions(dimensions)

    return await compute_balance_sheet_flat(
        provider=provider,
        financial_year_id=financial_year_id,
        period=period,
        include_dimensions=dim_list,
        include_prior_year=include_prior_year,
    )
