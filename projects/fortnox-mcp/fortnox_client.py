"""Fortnox API client with Client Credentials authentication."""

import base64
import time
from typing import Any, Optional

import httpx


class FortnoxClient:
    """Async client for the Fortnox REST API v3.

    Uses Client Credentials flow (introduced Dec 2025) for authentication.
    Automatically requests new access tokens when needed.
    """

    BASE_URL = "https://api.fortnox.se/3"
    TOKEN_URL = "https://apps.fortnox.se/oauth-v1/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_id = tenant_id
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._http = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
        )

    async def _ensure_token(self) -> None:
        """Request a new access token if current one is missing or expired."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return

        credentials = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()

        response = await self._http.post(
            self.TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
                "TenantId": str(self._tenant_id),
            },
            data={"grant_type": "client_credentials"},
        )
        response.raise_for_status()
        token_data = response.json()

        self._access_token = token_data["access_token"]
        self._token_expires_at = time.time() + token_data.get("expires_in", 3600)

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Fortnox API.

        Handles token refresh and rate limit retries automatically.
        """
        await self._ensure_token()

        for attempt in range(3):
            response = await self._http.request(
                method,
                path,
                params=params,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 429:
                # Rate limited — wait and retry
                wait_time = 2 ** attempt
                await _async_sleep(wait_time)
                continue

            if response.status_code == 401:
                # Token expired — refresh and retry
                self._access_token = None
                self._token_expires_at = 0
                await self._ensure_token()
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError("Fortnox API request failed after 3 retries")

    async def get(
        self, path: str, params: Optional[dict] = None
    ) -> dict[str, Any]:
        """GET request to Fortnox API."""
        return await self._request("GET", path, params=params)

    async def get_all_pages(
        self, path: str, params: Optional[dict] = None
    ) -> list[dict[str, Any]]:
        """GET all pages of a paginated endpoint.

        Returns a flat list of all items across all pages.
        """
        params = dict(params or {})
        params.setdefault("limit", 500)
        params["page"] = 1

        all_items: list[dict[str, Any]] = []

        while True:
            data = await self.get(path, params=params)

            meta = data.get("MetaInformation", {})
            total_pages = meta.get("@TotalPages", 1)

            # Find the data key (first key that isn't MetaInformation)
            data_key = next(
                (k for k in data if k != "MetaInformation"), None
            )
            if data_key and isinstance(data[data_key], list):
                all_items.extend(data[data_key])

            if params["page"] >= total_pages:
                break
            params["page"] += 1

        return all_items

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()


async def _async_sleep(seconds: float) -> None:
    """Async sleep helper."""
    import asyncio
    await asyncio.sleep(seconds)
