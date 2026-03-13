"""Meta endpoints — financial years and other reference data."""

from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/financial-years")
async def get_financial_years():
    """List available financial years from Fortnox.

    Returns a simplified list with year ID, date range, and label.
    """
    from main import fortnox_client

    data = await fortnox_client.get("/financialyears")
    years = data.get("FinancialYears", [])

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
