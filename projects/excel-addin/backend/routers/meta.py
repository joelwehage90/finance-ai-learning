"""Meta endpoints — financial years and other reference data."""

from fastapi import APIRouter, Depends

from auth import get_current_provider
from providers.base import AccountingProvider

router = APIRouter(tags=["meta"])


@router.get("/financial-years")
async def get_financial_years(
    provider: AccountingProvider = Depends(get_current_provider),
):
    """List available financial years.

    Returns a simplified list with year ID, date range, and label.
    """
    years = await provider.get_financial_years()

    return [
        {
            "id": fy["Id"],
            "from_date": fy.get("FromDate"),
            "to_date": fy.get("ToDate"),
            "label": _year_label(fy),
        }
        for fy in years
    ]


def _year_label(fy: dict) -> str:
    """Create a human-readable label like '2026 (2026-01-01 – 2026-12-31)'."""
    from_date = fy.get("FromDate", "")
    to_date = fy.get("ToDate", "")
    year = from_date[:4] if from_date else "?"
    return f"{year} ({from_date} – {to_date})"
