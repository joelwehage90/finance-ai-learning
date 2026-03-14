"""SIE cache — avoids redundant API calls and SIE parsing.

Caches parsed SIE data by (provider_type, tenant_id, sie_type,
financial_year_id) with a short TTL. Multiple endpoints hitting the
same year within the TTL window share a single fetch+parse.

The cache key includes provider and tenant to prevent cross-tenant
data leaks in a multi-tenant deployment.
"""

import logging
import time
from typing import Any

from providers.base import AccountingProvider
from sie_parser import parse_sie

logger = logging.getLogger(__name__)

_cache: dict[tuple[str, str, int, int], tuple[float, dict[str, Any]]] = {}
_TTL = 60.0  # seconds


async def get_parsed_sie(
    provider: AccountingProvider,
    sie_type: int,
    financial_year_id: int,
) -> dict[str, Any]:
    """Fetch and parse SIE data, returning cached result if fresh.

    Args:
        provider: Accounting provider for fetching SIE data.
        sie_type: SIE type (2 for reports, 4 for vouchers).
        financial_year_id: Provider-specific financial year ID.

    Returns:
        Parsed SIE dict from sie_parser.parse_sie().
    """
    key = (provider.provider_type, provider.tenant_id, sie_type, financial_year_id)
    now = time.monotonic()

    cached = _cache.get(key)
    if cached is not None:
        ts, data = cached
        if now - ts < _TTL:
            logger.debug("SIE cache hit for key=%s", key)
            return data

    logger.debug("SIE cache miss for key=%s, fetching from provider", key)
    sie_text = await provider.get_sie_export(
        sie_type=sie_type,
        financial_year_id=financial_year_id,
    )
    data = parse_sie(sie_text)
    _cache[key] = (now, data)
    return data


def clear_cache() -> None:
    """Clear all cached SIE data. Useful for testing."""
    _cache.clear()
