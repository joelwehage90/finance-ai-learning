"""Fortnox SIE client — fetches SIE files from the Fortnox API.

Extends the base FortnoxClient with support for text/plain responses
(SIE files are not JSON) and financial year ID lookup.

Usage:
    client = FortnoxSIEClient(client_id, client_secret, tenant_id)
    sie_text = await client.get_sie(sie_type=4)
    await client.close()
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

# Add fortnox-mcp to import path so we can reuse the base client
_FORTNOX_MCP_DIR = Path(__file__).resolve().parent.parent / "fortnox-mcp"
sys.path.insert(0, str(_FORTNOX_MCP_DIR))

from fortnox_client import FortnoxClient  # noqa: E402


class FortnoxSIEClient(FortnoxClient):
    """Fortnox client extended with SIE file fetching.

    The base FortnoxClient only handles JSON responses. SIE endpoints
    return text/plain in CP437 encoding, so we need a separate method.
    """

    async def get_sie(
        self,
        sie_type: int = 4,
        financial_year: Optional[int] = None,
    ) -> str:
        """Fetch a SIE file from Fortnox and return decoded text.

        Args:
            sie_type: SIE type (1=annual, 2=period, 3=object, 4=full).
            financial_year: Fortnox financial year ID. If None, uses current.

        Returns:
            SIE file content as a Python string (decoded from CP437).

        Raises:
            RuntimeError: If the request fails after 3 retries.
        """
        # Auto-resolve financial year if not provided
        if financial_year is None:
            from datetime import date
            financial_year = await self.get_financial_year_id(
                date.today().isoformat()
            )
            print(f"Auto-resolved financial year ID: {financial_year}")

        await self._ensure_token()

        params: dict = {"financialyear": financial_year}

        for attempt in range(3):
            response = await self._http.request(
                "GET",
                f"/sie/{sie_type}",
                params=params,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    # Fortnox SIE endpoint rejects text/plain but returns
                    # raw SIE text (CP437) when Accept is application/json.
                    "Accept": "application/json",
                },
            )

            if response.status_code == 429:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
                continue

            if response.status_code == 401:
                self._access_token = None
                self._token_expires_at = 0
                await self._ensure_token()
                continue

            response.raise_for_status()

            # SIE files use CP437 encoding (IBM PC 8-bit extended ASCII).
            # We decode from raw bytes to avoid httpx guessing wrong.
            return response.content.decode("cp437")

        raise RuntimeError("Failed to fetch SIE from Fortnox after 3 retries")

    async def get_financial_year_id(self, date: str) -> int:
        """Look up the Fortnox financial year ID for a given date.

        Args:
            date: Date string in YYYY-MM-DD format.

        Returns:
            Financial year ID (used in Fortnox API calls).

        Raises:
            ValueError: If no financial year is found for the date.
        """
        data = await self.get("/financialyears", params={"date": date})
        years = data.get("FinancialYears", [])
        if not years:
            raise ValueError(f"No financial year found for date {date}")
        return years[0]["Id"]
