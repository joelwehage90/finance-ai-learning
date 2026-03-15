"""Abstract accounting provider — interface for all accounting systems.

Services call these methods without knowing which accounting system
is being used (Fortnox, Visma, etc.). Each concrete provider wraps
its own API client internally.
"""

from abc import ABC, abstractmethod
from typing import Any


class AccountingProvider(ABC):
    """Abstract interface for accounting system providers."""

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """Unique identifier for this provider type (e.g. 'fortnox', 'visma')."""
        ...

    @property
    @abstractmethod
    def tenant_id(self) -> str:
        """The tenant/company ID for this connection."""
        ...

    @abstractmethod
    async def get_invoices(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all pages of invoices from the given endpoint.

        Args:
            endpoint: API-specific path (e.g. "/supplierinvoices").
            params: Query parameters (date filters, etc.).

        Returns:
            Flat list of invoice dicts.
        """
        ...

    @abstractmethod
    async def get_invoice_detail(
        self,
        endpoint: str,
        invoice_id: str | int,
    ) -> dict[str, Any]:
        """Fetch a single invoice with all detail fields.

        The list endpoint omits fields like Comments, OurReference,
        YourReference, etc.  This method fetches the full object.

        Args:
            endpoint: API-specific path (e.g. "/supplierinvoices").
            invoice_id: Primary key (GivenNumber or DocumentNumber).

        Returns:
            Full invoice dict with all fields.
        """
        ...

    @abstractmethod
    async def get_sie_export(
        self,
        sie_type: int,
        financial_year_id: int,
    ) -> str:
        """Fetch SIE file content as decoded text.

        Args:
            sie_type: SIE type (2 for reports, 4 for vouchers).
            financial_year_id: Provider-specific financial year ID.

        Returns:
            SIE file content as a Python string.
        """
        ...

    @abstractmethod
    async def get_financial_years(self) -> list[dict[str, Any]]:
        """List available financial years.

        Returns:
            List of dicts with at least 'Id', 'FromDate', 'ToDate'.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up HTTP connections."""
        ...
