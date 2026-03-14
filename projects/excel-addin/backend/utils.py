"""Shared utilities for the Excel add-in backend."""

import re


# Dimension ID to Swedish header name (BAS standard).
DIM_HEADERS: dict[int, str] = {
    1: "Kostnadsställe",
    6: "Projekt",
}


def parse_period(value: str) -> str:
    """Validate YYYY-MM period format and return YYYYMM for comparison.

    Raises:
        ValueError: If value does not match YYYY-MM format.
    """
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
        raise ValueError(f"Invalid period format: {value!r}, expected YYYY-MM")
    return value.replace("-", "")


def parse_dimensions(value: str | None) -> list[int] | None:
    """Parse comma-separated dimension IDs.

    Args:
        value: Comma-separated string like "1,6", or None.

    Returns:
        List of integer dimension IDs, or None if input is empty.

    Raises:
        ValueError: If any value is not a valid integer.
    """
    if not value:
        return None
    try:
        return [int(d.strip()) for d in value.split(",")]
    except ValueError:
        raise ValueError(
            f"Invalid dimensions: {value!r}, expected comma-separated integers"
        )
