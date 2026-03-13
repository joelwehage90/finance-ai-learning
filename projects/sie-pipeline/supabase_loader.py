"""Supabase loader — syncs parsed SIE data into Supabase tables.

Takes the structured dict from sie_parser.parse_sie() and loads it
into the Supabase database using the official Python client.

Design:
    - Supabase mirrors Fortnox: year-scoped tables use delete + insert
      so that deletions in Fortnox are reflected automatically.
    - Year-scoped (delete + insert): vouchers, transactions,
      period_balances, budget.
    - Global (upsert): accounts, dimensions, financial_years.
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

    def __init__(
        self,
        url: str,
        key: str,
        tenant_id: str,
        source_system: str | None = None,
    ):
        """Initialize loader.

        Args:
            url: Supabase project URL (e.g. https://xxx.supabase.co).
            key: Supabase service role key (bypasses RLS).
            tenant_id: Tenant identifier (e.g. "1803399_fortnox").
            source_system: Source system name (e.g. "fortnox", "visma").
                Used to tag dimension_types so different systems can
                coexist in the same database.
        """
        self._client: Client = create_client(url, key)
        self._tenant_id = tenant_id
        self._source_system = source_system

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
        counts["dimension_types"] = self._load_dimension_types(
            parsed.get("dimensions", {})
        )
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
        """Load chart of accounts and deactivate removed accounts."""
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

        # Deactivate accounts that no longer appear in the SIE file.
        loaded_numbers = set(accounts.keys())
        deactivated = self._deactivate_missing_accounts(loaded_numbers)
        if deactivated > 0:
            print(f"  Deactivated {deactivated} accounts no longer in SIE")

        return len(rows)

    def _deactivate_missing_accounts(self, loaded_numbers: set[int]) -> int:
        """Mark accounts as inactive if they are not in the SIE file.

        Only sets active=False — rows are never deleted. This is safe
        for historical data and can be used as a filter in future UIs.
        """
        # Fetch all currently active accounts for this tenant.
        response = (
            self._client.table("accounts")
            .select("account_number")
            .eq("tenant_id", self._tenant_id)
            .eq("active", True)
            .execute()
        )

        existing_active = {row["account_number"] for row in response.data}
        missing = existing_active - loaded_numbers

        if not missing:
            return 0

        # Deactivate in batches.
        missing_list = list(missing)
        for i in range(0, len(missing_list), 500):
            chunk = missing_list[i : i + 500]
            (
                self._client.table("accounts")
                .update({"active": False})
                .eq("tenant_id", self._tenant_id)
                .in_("account_number", chunk)
                .execute()
            )

        return len(missing)

    def _load_dimension_types(self, dimensions: dict[int, dict]) -> int:
        """Load dimension type definitions from SIE #DIM tags.

        Maps dimension_id to a human-readable name (e.g. 1 -> "Kostnadsställe").
        The source_system column tracks where the definition came from,
        enabling multi-system coexistence.
        """
        rows = [
            {
                "tenant_id": self._tenant_id,
                "dimension_id": dim_id,
                "name": info.get("name", ""),
                "source_system": self._source_system,
            }
            for dim_id, info in dimensions.items()
        ]

        if rows:
            self._batch_upsert("dimension_types", rows)
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

        Uses a full-replace strategy scoped by year_id, consistent with
        vouchers/transactions. All balance types are stored in the same
        table with different balance_type values and period formats:
          - period balances: period="2026-01", balance_type="period"
          - opening balances: period="2026-IB", balance_type="opening"
          - closing balances: period="2026-UB", balance_type="closing"
          - result balances:  period="2026-RES", balance_type="result"
        """
        rows: list[dict] = []

        # Period balances from #PSALDO (only current year, year_offset=0)
        for pb in period_balances:
            if pb.get("year_offset", 0) != 0:
                continue
            dims = pb.get("dimensions", {})
            rows.append({
                "tenant_id": self._tenant_id,
                "year_id": year_id,
                "account_number": pb["account"],
                "period": _sie_period_to_iso(pb["period"]),
                "cost_center": _extract_dimension(dims, 1),
                "project": _extract_dimension(dims, 6),
                "amount": _dec_to_float(pb["amount"]),
                "balance_type": "period",
            })

        # Opening balances from #IB (only current year, year_offset=0)
        for ib in opening_balances:
            if ib.get("year_offset", 0) != 0:
                continue
            rows.append({
                "tenant_id": self._tenant_id,
                "year_id": year_id,
                "account_number": ib["account"],
                "period": f"{year_id}-IB",
                "cost_center": "*",
                "project": "*",
                "amount": _dec_to_float(ib["amount"]),
                "balance_type": "opening",
            })

        # Closing balances from #UB (only current year, year_offset=0)
        for ub in closing_balances:
            if ub.get("year_offset", 0) != 0:
                continue
            rows.append({
                "tenant_id": self._tenant_id,
                "year_id": year_id,
                "account_number": ub["account"],
                "period": f"{year_id}-UB",
                "cost_center": "*",
                "project": "*",
                "amount": _dec_to_float(ub["amount"]),
                "balance_type": "closing",
            })

        # Result balances from #RES (only current year, year_offset=0)
        for res in result_balances:
            if res.get("year_offset", 0) != 0:
                continue
            rows.append({
                "tenant_id": self._tenant_id,
                "year_id": year_id,
                "account_number": res["account"],
                "period": f"{year_id}-RES",
                "cost_center": "*",
                "project": "*",
                "amount": _dec_to_float(res["amount"]),
                "balance_type": "result",
            })

        # Full replace for this year — mirrors Fortnox exactly.
        self._client.table("period_balances") \
            .delete() \
            .eq("tenant_id", self._tenant_id) \
            .eq("year_id", year_id) \
            .execute()

        if rows:
            self._batch_insert("period_balances", rows)
        return len(rows)

    def _load_vouchers(
        self, vouchers: list[dict], year_id: int
    ) -> tuple[int, int]:
        """Load vouchers and their transactions.

        Uses a full-replace strategy: delete all existing vouchers and
        transactions for the fiscal year, then insert fresh from the
        SIE4 snapshot. This ensures Supabase mirrors Fortnox exactly,
        including voucher deletions.

        Delete order matters due to FK: transactions → vouchers.

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

        # SIE4 is a complete snapshot of the fiscal year, so we do a
        # full replace: delete existing data then insert fresh.
        # Order matters: transactions first (FK → vouchers).
        self._client.table("transactions") \
            .delete() \
            .eq("tenant_id", self._tenant_id) \
            .eq("year_id", year_id) \
            .execute()

        self._client.table("vouchers") \
            .delete() \
            .eq("tenant_id", self._tenant_id) \
            .eq("year_id", year_id) \
            .execute()

        if voucher_rows:
            self._batch_insert("vouchers", voucher_rows)

        if transaction_rows:
            self._batch_insert("transactions", transaction_rows)

        return len(voucher_rows), len(transaction_rows)

    def _load_budget(self, period_budgets: list[dict], year_id: int) -> int:
        """Load period budgets from #PBUDGET.

        Full replace scoped by year_id — mirrors Fortnox exactly.
        """
        rows: list[dict] = []
        for pb in period_budgets:
            dims = pb.get("dimensions", {})
            rows.append({
                "tenant_id": self._tenant_id,
                "year_id": year_id,
                "account_number": pb["account"],
                "period": _sie_period_to_iso(pb["period"]),
                "cost_center": _extract_dimension(dims, 1),
                "amount": _dec_to_float(pb["amount"]),
            })

        # Full replace for this year.
        self._client.table("budget") \
            .delete() \
            .eq("tenant_id", self._tenant_id) \
            .eq("year_id", year_id) \
            .execute()

        if rows:
            self._batch_insert("budget", rows)
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
