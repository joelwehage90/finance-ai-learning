"""Supabase loader — upserts parsed SIE data into Supabase tables.

Takes the structured dict from sie_parser.parse_sie() and loads it
into the Supabase database using the official Python client.

Design:
    - All upserts are idempotent (safe to re-run).
    - Transactions use delete + insert (BIGSERIAL PK has no natural key).
    - Amounts are converted from Decimal to float for JSON serialization.
      PostgreSQL NUMERIC(15,2) preserves full precision.

Usage:
    loader = SupabaseLoader(url, key, tenant_id)
    counts = loader.load_all(parsed_sie, year_id=2026)
    print(counts)  # {"accounts": 150, "vouchers": 42, ...}
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from supabase import create_client, Client


class SupabaseLoader:
    """Loads parsed SIE data into Supabase."""

    def __init__(self, url: str, key: str, tenant_id: str):
        """Initialize loader.

        Args:
            url: Supabase project URL (e.g. https://xxx.supabase.co).
            key: Supabase service role key (bypasses RLS).
            tenant_id: UUID of the tenant in the tenants table.
        """
        self._client: Client = create_client(url, key)
        self._tenant_id = tenant_id

    def load_all(self, parsed: dict[str, Any], year_id: int) -> dict[str, int]:
        """Load all parsed SIE data into Supabase.

        Args:
            parsed: Output from sie_parser.parse_sie().
            year_id: Financial year identifier (e.g. 2026).

        Returns:
            Dict with counts of upserted records per table.
        """
        counts: dict[str, int] = {}

        counts["financial_years"] = self._load_financial_years(
            parsed.get("financial_years", [])
        )
        counts["accounts"] = self._load_accounts(parsed.get("accounts", {}))
        counts["dimensions"] = self._load_dimensions(
            parsed.get("dimensions", {}),
            parsed.get("objects", []),
        )
        counts["period_balances"] = self._load_period_balances(
            parsed.get("period_balances", []),
            parsed.get("opening_balances", []),
            parsed.get("closing_balances", []),
            parsed.get("result_balances", []),
            year_id,
        )
        counts["vouchers"], counts["transactions"] = self._load_vouchers(
            parsed.get("vouchers", []), year_id
        )
        counts["budget"] = self._load_budget(
            parsed.get("period_budgets", []), year_id
        )

        return counts

    def update_sync_state(
        self,
        status: str = "idle",
        records: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Update the sync_state table with current sync status."""
        row = {
            "tenant_id": self._tenant_id,
            "entity_type": "sie4",
            "last_sync": _now_iso(),
            "records_synced": records,
            "status": status,
            "error_message": error,
        }
        if status == "idle":
            row["last_full_sync"] = _now_iso()

        self._client.table("sync_state").upsert(row).execute()

    # ----------------------------------------------------------------
    # Private load methods
    # ----------------------------------------------------------------

    def _load_financial_years(self, years: list[dict]) -> int:
        """Load financial year definitions."""
        rows = []
        for fy in years:
            start = fy.get("start")
            end = fy.get("end")
            if not start or not end:
                continue
            year_id = int(start[:4])
            rows.append({
                "tenant_id": self._tenant_id,
                "year_id": year_id,
                "start_date": _sie_date_to_iso(start),
                "end_date": _sie_date_to_iso(end),
            })

        if rows:
            self._client.table("financial_years").upsert(rows).execute()
        return len(rows)

    def _load_accounts(self, accounts: dict[int, dict]) -> int:
        """Load chart of accounts."""
        rows = [
            {
                "tenant_id": self._tenant_id,
                "account_number": number,
                "name": info.get("name", ""),
                "account_type": info.get("type"),
                "sru_code": info.get("sru"),
                "active": True,
            }
            for number, info in accounts.items()
        ]

        if rows:
            self._batch_upsert("accounts", rows)
        return len(rows)

    def _load_dimensions(
        self, dimensions: dict[int, dict], objects: list[dict]
    ) -> int:
        """Load dimensions and their objects."""
        rows = [
            {
                "tenant_id": self._tenant_id,
                "dimension_id": obj["dimension_id"],
                "object_id": obj["object_id"],
                "name": obj.get("name", ""),
            }
            for obj in objects
        ]

        if rows:
            self._batch_upsert("dimensions", rows)
        return len(rows)

    def _load_period_balances(
        self,
        period_balances: list[dict],
        opening_balances: list[dict],
        closing_balances: list[dict],
        result_balances: list[dict],
        year_id: int,
    ) -> int:
        """Load period balances, opening/closing balances, and results.

        All are stored in the same period_balances table with different
        balance_type values and period formats:
          - period balances: period="2026-01", balance_type="period"
          - opening balances: period="2026-IB", balance_type="opening"
          - closing balances: period="2026-UB", balance_type="closing"
          - result balances:  period="2026-RES", balance_type="result"
        """
        rows: list[dict] = []

        # Period balances from #PSALDO
        for pb in period_balances:
            dims = pb.get("dimensions", {})
            rows.append({
                "tenant_id": self._tenant_id,
                "account_number": pb["account"],
                "period": _sie_period_to_iso(pb["period"]),
                "cost_center": _extract_dimension(dims, 1),
                "project": _extract_dimension(dims, 6),
                "amount": _dec_to_float(pb["amount"]),
                "balance_type": "period",
            })

        # Opening balances from #IB
        for ib in opening_balances:
            rows.append({
                "tenant_id": self._tenant_id,
                "account_number": ib["account"],
                "period": f"{year_id}-IB",
                "cost_center": "*",
                "project": "*",
                "amount": _dec_to_float(ib["amount"]),
                "balance_type": "opening",
            })

        # Closing balances from #UB
        for ub in closing_balances:
            rows.append({
                "tenant_id": self._tenant_id,
                "account_number": ub["account"],
                "period": f"{year_id}-UB",
                "cost_center": "*",
                "project": "*",
                "amount": _dec_to_float(ub["amount"]),
                "balance_type": "closing",
            })

        # Result balances from #RES
        for res in result_balances:
            rows.append({
                "tenant_id": self._tenant_id,
                "account_number": res["account"],
                "period": f"{year_id}-RES",
                "cost_center": "*",
                "project": "*",
                "amount": _dec_to_float(res["amount"]),
                "balance_type": "result",
            })

        if rows:
            self._batch_upsert("period_balances", rows)
        return len(rows)

    def _load_vouchers(
        self, vouchers: list[dict], year_id: int
    ) -> tuple[int, int]:
        """Load vouchers and their transactions.

        Vouchers are upserted (they have a composite natural key).
        Transactions are deleted and re-inserted (they use BIGSERIAL PK
        with no natural key for matching).

        Returns:
            Tuple of (voucher_count, transaction_count).
        """
        voucher_rows: list[dict] = []
        transaction_rows: list[dict] = []

        for v in vouchers:
            v_number = v.get("number")
            if v_number is None:
                continue

            voucher_rows.append({
                "tenant_id": self._tenant_id,
                "series": v.get("series", ""),
                "number": v_number,
                "year_id": year_id,
                "date": _sie_date_to_iso(v.get("date", "")),
                "description": v.get("text"),
            })

            for t in v.get("transactions", []):
                dims = t.get("dimensions", {})
                transaction_rows.append({
                    "tenant_id": self._tenant_id,
                    "voucher_series": v.get("series", ""),
                    "voucher_number": v_number,
                    "year_id": year_id,
                    "account_number": t["account"],
                    "amount": _dec_to_float(t["amount"]),
                    "cost_center": _extract_dimension(dims, 1),
                    "project": _extract_dimension(dims, 6),
                    "transaction_info": t.get("text"),
                })

        if voucher_rows:
            self._batch_upsert("vouchers", voucher_rows)

        if transaction_rows:
            # Delete existing transactions for this tenant + year,
            # then insert fresh. Safe because SIE4 is a complete export.
            self._client.table("transactions") \
                .delete() \
                .eq("tenant_id", self._tenant_id) \
                .eq("year_id", year_id) \
                .execute()

            self._batch_insert("transactions", transaction_rows)

        return len(voucher_rows), len(transaction_rows)

    def _load_budget(self, period_budgets: list[dict], year_id: int) -> int:
        """Load period budgets from #PBUDGET."""
        rows: list[dict] = []
        for pb in period_budgets:
            dims = pb.get("dimensions", {})
            rows.append({
                "tenant_id": self._tenant_id,
                "account_number": pb["account"],
                "period": _sie_period_to_iso(pb["period"]),
                "cost_center": _extract_dimension(dims, 1),
                "amount": _dec_to_float(pb["amount"]),
            })

        if rows:
            self._batch_upsert("budget", rows)
        return len(rows)

    # ----------------------------------------------------------------
    # Batch helpers
    # ----------------------------------------------------------------

    def _batch_upsert(self, table: str, rows: list[dict], batch_size: int = 500) -> None:
        """Upsert rows in batches to avoid request size limits."""
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            self._client.table(table).upsert(chunk).execute()

    def _batch_insert(self, table: str, rows: list[dict], batch_size: int = 500) -> None:
        """Insert rows in batches to avoid request size limits."""
        for i in range(0, len(rows), batch_size):
            chunk = rows[i:i + batch_size]
            self._client.table(table).insert(chunk).execute()


# ----------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------

def _sie_date_to_iso(date_str: str) -> str:
    """Convert SIE date format to ISO date.

    Example: "20260115" -> "2026-01-15"
    """
    if not date_str or len(date_str) < 8:
        return date_str
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"


def _sie_period_to_iso(period_str: str) -> str:
    """Convert SIE period format to ISO period.

    Example: "202601" -> "2026-01"
    """
    if not period_str or len(period_str) < 6:
        return period_str
    return f"{period_str[:4]}-{period_str[4:6]}"


def _extract_dimension(dims: dict[int, str], dim_id: int) -> str:
    """Extract a dimension value, defaulting to '*' if not present."""
    return dims.get(dim_id, "*")


def _dec_to_float(val: Any) -> float:
    """Convert Decimal to float for JSON serialization."""
    if isinstance(val, Decimal):
        return float(val)
    return float(val) if val is not None else 0.0


def _now_iso() -> str:
    """Current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()
