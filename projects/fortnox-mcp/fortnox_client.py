"""Fortnox API client with Client Credentials and Authorization Code auth."""

import asyncio
import base64
import time
from typing import Any, Callable, Coroutine, Optional

import httpx

# Callback type for token refresh notifications.
# Called with (new_access_token, new_refresh_token, expires_in_seconds).
OnTokenRefresh = Callable[[str, str, int], Coroutine[Any, Any, None]]


class FortnoxClient:
    """Async client for the Fortnox REST API v3.

    Supports two authentication flows:

    1. **Client Credentials** (default) — machine-to-machine, uses
       client_id + client_secret to obtain access tokens automatically.

    2. **Authorization Code** — user-delegated, when ``access_token``
       and ``refresh_token`` are provided. On 401 or expiry, the client
       refreshes using the refresh token. Since Fortnox **rotates**
       refresh tokens on every use (45-day rolling expiry), an asyncio
       lock serialises concurrent refresh attempts, and the optional
       ``on_token_refresh`` callback is invoked so the caller can
       persist the new token pair.
    """

    BASE_URL = "https://api.fortnox.se/3"
    TOKEN_URL = "https://apps.fortnox.se/oauth-v1/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        *,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[OnTokenRefresh] = None,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._tenant_id = tenant_id
        self._access_token: Optional[str] = access_token
        self._refresh_token: Optional[str] = refresh_token
        self._on_token_refresh = on_token_refresh
        self._token_expires_at: float = 0
        self._refresh_lock = asyncio.Lock()

        # When pre-seeded tokens are provided we are in auth-code mode.
        self._auth_code_mode = access_token is not None

        self._http = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
        )

    async def _ensure_token(self) -> None:
        """Obtain or refresh an access token.

        In Client Credentials mode: requests a fresh token using the
        client secret.

        In Authorization Code mode: uses the refresh token to obtain
        a new access/refresh pair. An asyncio lock prevents concurrent
        refreshes (critical because Fortnox rotates refresh tokens).
        """
        if self._access_token and time.time() < self._token_expires_at - 60:
            return

        async with self._refresh_lock:
            # Double-check after acquiring the lock — another coroutine
            # may have refreshed while we waited.
            if self._access_token and time.time() < self._token_expires_at - 60:
                return

            credentials = base64.b64encode(
                f"{self._client_id}:{self._client_secret}".encode()
            ).decode()

            if self._auth_code_mode:
                await self._refresh_with_token(credentials)
            else:
                await self._request_client_credentials(credentials)

    async def _request_client_credentials(self, credentials: str) -> None:
        """Obtain a token via Client Credentials grant."""
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

    async def _refresh_with_token(self, credentials: str) -> None:
        """Refresh the access token using a refresh token.

        Fortnox rotates the refresh token on every use, so we must
        persist the new pair via the on_token_refresh callback.
        """
        if not self._refresh_token:
            raise RuntimeError(
                "Authorization Code mode requires a refresh token, but none is set"
            )

        response = await self._http.post(
            self.TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
        )
        response.raise_for_status()
        token_data = response.json()

        self._access_token = token_data["access_token"]
        self._refresh_token = token_data.get("refresh_token", self._refresh_token)
        expires_in = token_data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in

        # Notify caller so they can persist the rotated tokens.
        if self._on_token_refresh:
            await self._on_token_refresh(
                self._access_token,
                self._refresh_token,
                expires_in,
            )

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
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
                json=json_body,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 429:
                # Rate limited — wait and retry
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
                continue

            if response.status_code == 401:
                # Token expired — invalidate and refresh.
                # Setting expires_at to 0 forces _ensure_token to act.
                self._access_token = None
                self._token_expires_at = 0
                await self._ensure_token()
                continue

            if response.status_code >= 400:
                # Include Fortnox error details in the exception
                try:
                    error_body = response.json()
                except Exception:
                    error_body = response.text
                raise httpx.HTTPStatusError(
                    f"{response.status_code} for {path}: {error_body}",
                    request=response.request,
                    response=response,
                )
            return response.json()

        raise RuntimeError("Fortnox API request failed after 3 retries")

    async def get(
        self, path: str, params: Optional[dict] = None
    ) -> dict[str, Any]:
        """GET request to Fortnox API."""
        return await self._request("GET", path, params=params)

    async def post(
        self, path: str, json_body: dict, params: Optional[dict] = None
    ) -> dict[str, Any]:
        """POST request to Fortnox API."""
        return await self._request("POST", path, params=params, json_body=json_body)

    async def put(
        self, path: str, json_body: Optional[dict] = None, params: Optional[dict] = None
    ) -> dict[str, Any]:
        """PUT request to Fortnox API."""
        return await self._request("PUT", path, params=params, json_body=json_body)

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


