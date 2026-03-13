"""Report endpoints — Resultaträkning and Balansräkning from SIE2.

Includes both standard and comparative (vs prior year) versions.
"""

from fastapi import APIRouter, Query

from services.sie_report_service import (
    compute_income_statement,
    compute_balance_sheet,
    compute_income_statement_comparative,
    compute_balance_sheet_comparative,
)

router = APIRouter(tags=["reports"])


@router.get("/rr")
async def get_resultatrakning(
    financial_year_id: int = Query(..., description="Fortnox financial year ID"),
    from_period: str = Query(..., description="Start period (YYYY-MM)"),
    to_period: str = Query(..., description="End period (YYYY-MM)"),
):
    """Compute an income statement (Resultaträkning) from SIE2 data.

    Fetches SIE2 from Fortnox, sums period balances for accounts
    3000-8999 within the specified period range, and groups by
    account class.
    """
    from main import sie_client

    return await compute_income_statement(
        client=sie_client,
        financial_year_id=financial_year_id,
        from_period=from_period,
        to_period=to_period,
    )


@router.get("/br")
async def get_balansrakning(
    financial_year_id: int = Query(..., description="Fortnox financial year ID"),
    period: str = Query(..., description="Balance date period (YYYY-MM)"),
):
    """Compute a balance sheet (Balansräkning) from SIE2 data.

    Fetches SIE2 from Fortnox, computes IB + accumulated period
    movements up to the specified period for accounts 1000-2999.
    """
    from main import sie_client

    return await compute_balance_sheet(
        client=sie_client,
        financial_year_id=financial_year_id,
        period=period,
    )


@router.get("/rr-comparative")
async def get_resultatrakning_comparative(
    financial_year_id: int = Query(..., description="Fortnox financial year ID"),
    from_period: str = Query(..., description="Start period (YYYY-MM)"),
    to_period: str = Query(..., description="End period (YYYY-MM)"),
):
    """Comparative income statement — current year vs prior year.

    Returns columns: Konto, Kontonamn, Aktuellt, Föreg. år,
    Förändring SEK, Förändring %.
    """
    from main import sie_client

    return await compute_income_statement_comparative(
        client=sie_client,
        financial_year_id=financial_year_id,
        from_period=from_period,
        to_period=to_period,
    )


@router.get("/br-comparative")
async def get_balansrakning_comparative(
    financial_year_id: int = Query(..., description="Fortnox financial year ID"),
    period: str = Query(..., description="Balance date period (YYYY-MM)"),
):
    """Comparative balance sheet — current year vs prior year.

    Returns columns: Konto, Kontonamn, Aktuellt, Föreg. år,
    Förändring SEK, Förändring %.
    """
    from main import sie_client

    return await compute_balance_sheet_comparative(
        client=sie_client,
        financial_year_id=financial_year_id,
        period=period,
    )
