"""Fortnox accounting provider — wraps FortnoxClient and FortnoxSIEClient.

Adapts the existing Fortnox API clients to the provider-agnostic
AccountingProvider interface. Supports both Client Credentials flow
(dev/single-tenant) and Authorization Code flow (multi-tenant via
optional access_token/refresh_token).
"""

from typing import Any, Optional

from fortnox_client import FortnoxClient, OnTokenRefresh
from fortnox_sie_client import FortnoxSIEClient
from providers.base import AccountingProvider


class FortnoxProvider(AccountingProvider):
    """Fortnox implementation of AccountingProvider."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
        on_token_refresh: Optional[OnTokenRefresh] = None,
    ):
        self._tenant_id = tenant_id

        # Both clients share the same auth parameters.
        auth_kwargs: dict[str, Any] = {}
        if access_token is not None:
            auth_kwargs["access_token"] = access_token
        if refresh_token is not None:
            auth_kwargs["refresh_token"] = refresh_token
        if on_token_refresh is not None:
            auth_kwargs["on_token_refresh"] = on_token_refresh

        self._client = FortnoxClient(
            client_id, client_secret, tenant_id, **auth_kwargs
        )
        self._sie_client = FortnoxSIEClient(
            client_id, client_secret, tenant_id, **auth_kwargs
        )

    @property
    def provider_type(self) -> str:
        return "fortnox"

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    async def get_invoices(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all pages of invoices from a Fortnox endpoint."""
        return await self._client.get_all_pages(endpoint, params=params)

    async def get_invoice_detail(
        self,
        endpoint: str,
        invoice_id: str | int,
    ) -> dict[str, Any]:
        """Fetch a single invoice with full detail fields from Fortnox."""
        data = await self._client.get(f"{endpoint}/{invoice_id}")
        # Response is e.g. {"SupplierInvoice": {...}} or {"Invoice": {...}}.
        # Return the inner object.
        data_key = next((k for k in data if k != "MetaInformation"), None)
        return data[data_key] if data_key else data

    async def get_sie_export(
        self,
        sie_type: int,
        financial_year_id: int,
    ) -> str:
        """Fetch SIE file content as decoded text from Fortnox."""
        return await self._sie_client.get_sie(
            sie_type=sie_type,
            financial_year=financial_year_id,
        )

    async def get_financial_years(self) -> list[dict[str, Any]]:
        """List available financial years from Fortnox."""
        data = await self._client.get("/financialyears")
        return data.get("FinancialYears", [])

    async def close(self) -> None:
        """Close both HTTP clients."""
        await self._client.close()
        await self._sie_client.close()
