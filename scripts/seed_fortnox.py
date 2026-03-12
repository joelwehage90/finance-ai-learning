"""Seed Fortnox sandbox with anonymized SIE data.

Parses a SIE4 file and pushes accounts, cost centers, projects,
and vouchers into Fortnox via the REST API.

Usage:
    python3 scripts/seed_fortnox.py tests/fixtures/demo_2026.se
    python3 scripts/seed_fortnox.py tests/fixtures/demo_2026.se --dry-run
    python3 scripts/seed_fortnox.py tests/fixtures/demo_2026.se --skip-vouchers
"""

import argparse
import asyncio
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# Load .env from fortnox-mcp project
_ROOT = Path(__file__).resolve().parent.parent
_FORTNOX_MCP_DIR = _ROOT / "projects" / "fortnox-mcp"
_SIE_PIPELINE_DIR = _ROOT / "projects" / "sie-pipeline"
load_dotenv(_FORTNOX_MCP_DIR / ".env")

# Add import paths
sys.path.insert(0, str(_FORTNOX_MCP_DIR))
sys.path.insert(0, str(_SIE_PIPELINE_DIR))

from fortnox_client import FortnoxClient  # noqa: E402
from sie_parser import parse_sie  # noqa: E402


# --- Rate limiter ---

class RateLimiter:
    """Sliding window rate limiter for Fortnox API (25 req / 5 sec)."""

    def __init__(self, max_requests: int = 23, window_seconds: float = 5.0):
        # Use 23 instead of 25 for safety margin
        self.max_requests = max_requests
        self.window = window_seconds
        self.timestamps: list[float] = []

    async def wait(self):
        """Wait if necessary to stay within rate limits."""
        now = time.time()
        # Remove timestamps outside the window
        self.timestamps = [t for t in self.timestamps if now - t < self.window]
        if len(self.timestamps) >= self.max_requests:
            # Wait until the oldest request in window expires
            sleep_time = self.window - (now - self.timestamps[0]) + 0.1
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        self.timestamps.append(time.time())


class FortnoxSeeder:
    """Seeds a Fortnox environment with parsed SIE data."""

    def __init__(self, client: FortnoxClient, dry_run: bool = False):
        self.client = client
        self.dry_run = dry_run
        self.limiter = RateLimiter()
        self.stats = {
            "accounts_created": 0,
            "accounts_skipped": 0,
            "accounts_failed": 0,
            "costcenters_created": 0,
            "costcenters_skipped": 0,
            "projects_created": 0,
            "projects_skipped": 0,
            "voucher_series_created": 0,
            "voucher_series_skipped": 0,
            "vouchers_created": 0,
            "vouchers_failed": 0,
        }

    async def _api_post(self, path: str, body: dict) -> dict | None:
        """POST to Fortnox API with rate limiting and error handling."""
        await self.limiter.wait()
        try:
            result = await self.client._request("POST", path, json_body=body)
            return result
        except Exception as e:
            error_msg = str(e)
            # 4xx errors often mean "already exists" — we handle gracefully
            if "already exists" in error_msg.lower() or "409" in error_msg:
                return None
            raise

    async def _api_put(self, path: str, body: dict) -> dict | None:
        """PUT to Fortnox API with rate limiting."""
        await self.limiter.wait()
        try:
            result = await self.client._request("PUT", path, json_body=body)
            return result
        except Exception:
            return None

    async def _api_get(self, path: str, params: dict | None = None) -> dict | None:
        """GET from Fortnox API with rate limiting."""
        await self.limiter.wait()
        try:
            return await self.client.get(path, params=params)
        except Exception:
            return None

    # --- Financial years ---

    async def ensure_financial_years(self, parsed: dict) -> None:
        """Check that required financial years exist in Fortnox."""
        print("\n📅 Checking financial years...")

        for fy in parsed.get("financial_years", []):
            start = fy.get("start", "")
            end = fy.get("end", "")
            if len(start) == 8 and len(end) == 8:
                start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
                end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"

                result = await self._api_get(
                    "/financialyears", params={"date": start_fmt}
                )
                years = result.get("FinancialYears", []) if result else []

                if years:
                    print(f"  ✅ Year {start_fmt} to {end_fmt} exists (ID: {years[0]['Id']})")
                else:
                    print(f"  ⚠️  Year {start_fmt} to {end_fmt} NOT found")
                    if not self.dry_run:
                        try:
                            create_result = await self._api_post(
                                "/financialyears",
                                {"FinancialYear": {
                                    "FromDate": start_fmt,
                                    "ToDate": end_fmt,
                                }}
                            )
                            if create_result:
                                print(f"     Created financial year {start_fmt} to {end_fmt}")
                            else:
                                print(f"     ❌ Could not create financial year")
                        except Exception as e:
                            print(f"     ❌ Error creating financial year: {e}")

    # --- Voucher series ---

    async def ensure_voucher_series(self, parsed: dict) -> None:
        """Create voucher series that don't exist yet."""
        series_codes = set(v["series"] for v in parsed.get("vouchers", []) if v.get("series"))
        print(f"\n📋 Ensuring {len(series_codes)} voucher series exist...")

        for code in sorted(series_codes):
            if self.dry_run:
                print(f"  [dry-run] Would check/create series '{code}'")
                continue

            # Check if series exists
            result = await self._api_get(f"/voucherseries/{code}")
            if result and "VoucherSeries" in result:
                self.stats["voucher_series_skipped"] += 1
                continue

            # Create it
            try:
                await self._api_post("/voucherseries", {
                    "VoucherSeries": {
                        "Code": code,
                        "Description": f"Serie {code}",
                    }
                })
                self.stats["voucher_series_created"] += 1
                print(f"  ✅ Created series '{code}'")
            except Exception as e:
                self.stats["voucher_series_skipped"] += 1
                # Likely already exists
                pass

        created = self.stats["voucher_series_created"]
        skipped = self.stats["voucher_series_skipped"]
        print(f"  Done: {created} created, {skipped} already existed")

    # --- Accounts ---

    async def seed_accounts(self, parsed: dict) -> None:
        """Create accounts from SIE chart of accounts.

        Also activates existing but inactive accounts via PUT,
        since Fortnox rejects vouchers referencing inactive accounts.
        """
        accounts = parsed.get("accounts", {})
        print(f"\n📊 Seeding {len(accounts)} accounts (create or activate)...")
        activated = 0

        for i, (acct_num, acct_data) in enumerate(sorted(accounts.items())):
            name = acct_data.get("name", f"Konto {acct_num}")
            if not name:
                name = f"Konto {acct_num}"

            if self.dry_run:
                if i < 3:
                    print(f"  [dry-run] Would create/activate account {acct_num}: {name}")
                elif i == 3:
                    print(f"  [dry-run] ... and {len(accounts) - 3} more")
                continue

            body = {
                "Account": {
                    "Number": acct_num,
                    "Description": name[:200],
                    "Active": True,
                }
            }
            if acct_data.get("sru"):
                body["Account"]["SRU"] = acct_data["sru"]

            try:
                result = await self._api_post("/accounts", body)
                if result:
                    self.stats["accounts_created"] += 1
                else:
                    # Already exists — activate via PUT
                    await self._api_put(f"/accounts/{acct_num}", body)
                    activated += 1
                    self.stats["accounts_skipped"] += 1
            except Exception as e:
                # Already exists — try to activate via PUT
                try:
                    await self._api_put(f"/accounts/{acct_num}", body)
                    activated += 1
                except Exception:
                    self.stats["accounts_failed"] += 1
                    if self.stats["accounts_failed"] <= 5:
                        print(f"  ❌ Account {acct_num}: {e}")
                self.stats["accounts_skipped"] += 1

            # Progress
            if (i + 1) % 100 == 0:
                print(f"  ... {i + 1}/{len(accounts)} accounts processed")

        c = self.stats["accounts_created"]
        s = self.stats["accounts_skipped"]
        f = self.stats["accounts_failed"]
        print(f"  Done: {c} created, {activated} activated, {f} failed")

    # --- Cost centers ---

    async def seed_cost_centers(self, parsed: dict) -> None:
        """Create cost centers from SIE dimension 1.

        Also activates any existing but inactive cost centers,
        since Fortnox rejects vouchers referencing inactive CCs.
        """
        objects = [o for o in parsed.get("objects", []) if o["dimension_id"] == 1]
        print(f"\n🏢 Seeding {len(objects)} cost centers (create or activate)...")
        activated = 0

        for i, obj in enumerate(objects):
            code = obj["object_id"]
            name = obj.get("name", code)

            if self.dry_run:
                if i < 3:
                    print(f"  [dry-run] Would create/activate CC {code}: {name}")
                elif i == 3:
                    print(f"  [dry-run] ... and {len(objects) - 3} more")
                continue

            body = {
                "CostCenter": {
                    "Code": code,
                    "Description": name[:50],
                    "Active": True,
                }
            }

            try:
                result = await self._api_post("/costcenters", body)
                if result:
                    self.stats["costcenters_created"] += 1
                else:
                    # Already exists — activate it via PUT
                    await self._api_put(f"/costcenters/{code}", body)
                    activated += 1
                    self.stats["costcenters_skipped"] += 1
            except Exception:
                # Already exists — try to activate via PUT
                try:
                    await self._api_put(f"/costcenters/{code}", body)
                    activated += 1
                except Exception:
                    pass
                self.stats["costcenters_skipped"] += 1

        c = self.stats["costcenters_created"]
        s = self.stats["costcenters_skipped"]
        print(f"  Done: {c} created, {activated} activated, {s - activated} already active")

    # --- Projects ---

    async def seed_projects(self, parsed: dict) -> None:
        """Create projects from SIE dimension 6."""
        objects = [o for o in parsed.get("objects", []) if o["dimension_id"] == 6]
        print(f"\n📁 Seeding {len(objects)} projects...")

        for i, obj in enumerate(objects):
            proj_num = obj["object_id"]
            name = obj.get("name", proj_num)

            if self.dry_run:
                if i < 3:
                    print(f"  [dry-run] Would create project {proj_num}: {name}")
                elif i == 3:
                    print(f"  [dry-run] ... and {len(objects) - 3} more")
                continue

            try:
                result = await self._api_post("/projects", {
                    "Project": {
                        "ProjectNumber": proj_num,
                        "Description": name[:50],
                        "Status": "ONGOING",
                    }
                })
                if result:
                    self.stats["projects_created"] += 1
                else:
                    self.stats["projects_skipped"] += 1
            except Exception:
                self.stats["projects_skipped"] += 1

        c = self.stats["projects_created"]
        s = self.stats["projects_skipped"]
        print(f"  Done: {c} created, {s} skipped/existed")

    # --- Vouchers ---

    async def seed_vouchers(self, parsed: dict, strip_dimensions: bool = False,
                            force_series: str | None = None) -> None:
        """Create vouchers with their transaction rows."""
        vouchers = parsed.get("vouchers", [])
        extra = ""
        if strip_dimensions:
            extra += ", without CC/project"
        if force_series:
            extra += f", all mapped to series {force_series}"
        print(f"\n📝 Seeding {len(vouchers)} vouchers{extra}...")

        for i, ver in enumerate(vouchers):
            series = force_series or ver.get("series", "A")
            date_raw = ver.get("date", "")
            text = ver.get("text", "")
            transactions = ver.get("transactions", [])

            if not date_raw or len(date_raw) != 8:
                continue

            # Format date: YYYYMMDD -> YYYY-MM-DD
            date_fmt = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"

            # Build voucher rows
            rows = []
            for trans in transactions:
                amount = trans.get("amount", Decimal("0"))
                if amount is None:
                    continue

                row: dict = {
                    "Account": trans["account"],
                    "Debit": float(amount) if amount > 0 else 0,
                    "Credit": float(abs(amount)) if amount < 0 else 0,
                }

                # Map dimensions to CostCenter / Project
                if not strip_dimensions:
                    dims = trans.get("dimensions", {})
                    if 1 in dims:
                        row["CostCenter"] = dims[1]
                    if 6 in dims:
                        row["Project"] = dims[6]

                # Transaction text
                trans_text = trans.get("text")
                if trans_text:
                    row["TransactionInformation"] = trans_text[:100]

                rows.append(row)

            if not rows:
                continue

            if self.dry_run:
                if i < 3:
                    print(f"  [dry-run] Voucher {series}{ver.get('number', '?')} "
                          f"{date_fmt}: {len(rows)} rows")
                elif i == 3:
                    print(f"  [dry-run] ... and {len(vouchers) - 3} more")
                continue

            body = {
                "Voucher": {
                    "VoucherSeries": series,
                    "TransactionDate": date_fmt,
                    "Description": (text or f"SIE import {series}{ver.get('number', '')}")[:200],
                    "VoucherRows": rows,
                }
            }

            try:
                result = await self._api_post("/vouchers", body)
                if result:
                    self.stats["vouchers_created"] += 1
                else:
                    self.stats["vouchers_failed"] += 1
            except Exception as e:
                self.stats["vouchers_failed"] += 1
                if self.stats["vouchers_failed"] <= 10:
                    print(f"  ❌ Voucher {series}{ver.get('number', '?')} {date_fmt}: {e}")

            # Progress
            if (i + 1) % 100 == 0:
                elapsed_est = (i + 1) / 5  # ~5 req/sec
                remaining = (len(vouchers) - i - 1) / 5
                print(f"  ... {i + 1}/{len(vouchers)} vouchers "
                      f"(~{int(remaining)}s remaining)")

        c = self.stats["vouchers_created"]
        f = self.stats["vouchers_failed"]
        print(f"  Done: {c} created, {f} failed")

    # --- Main entry ---

    async def seed_all(self, parsed: dict, skip_vouchers: bool = False,
                       strip_dimensions: bool = False,
                       force_series: str | None = None) -> None:
        """Run the full seeding pipeline in correct order."""
        print("=" * 60)
        print("Fortnox Sandbox Seeder")
        print("=" * 60)

        company = parsed["metadata"].get("company_name", "Unknown")
        n_accounts = len(parsed.get("accounts", {}))
        n_vouchers = len(parsed.get("vouchers", []))
        print(f"\nSource: {company}")
        print(f"Accounts: {n_accounts}, Vouchers: {n_vouchers}")

        if self.dry_run:
            print("MODE: DRY RUN (no changes will be made)")

        start_time = time.time()

        # 1. Financial years must exist first
        await self.ensure_financial_years(parsed)

        # 2. Voucher series
        await self.ensure_voucher_series(parsed)

        # 3. Accounts (needed before vouchers)
        await self.seed_accounts(parsed)

        # 4. Cost centers (dim 1)
        await self.seed_cost_centers(parsed)

        # 5. Projects (dim 6)
        await self.seed_projects(parsed)

        # 6. Vouchers (the big one)
        if skip_vouchers:
            print("\n⏭️  Skipping vouchers (--skip-vouchers)")
        else:
            await self.seed_vouchers(parsed, strip_dimensions=strip_dimensions,
                                       force_series=force_series)

        elapsed = time.time() - start_time
        print(f"\n{'=' * 60}")
        print(f"✅ Seeding complete in {elapsed:.0f} seconds")
        print(f"\nStats:")
        for key, value in self.stats.items():
            if value > 0:
                print(f"  {key}: {value}")


def _require_env(name: str) -> str:
    """Get a required environment variable or exit."""
    value = os.environ.get(name)
    if not value:
        print(f"❌ Missing env var: {name}")
        print(f"   Set it in projects/fortnox-mcp/.env")
        sys.exit(1)
    return value


async def run(args: argparse.Namespace) -> None:
    """Main async entry point."""
    # Parse SIE file
    sie_path = Path(args.sie_file)
    if not sie_path.exists():
        print(f"❌ File not found: {sie_path}")
        sys.exit(1)

    with open(sie_path, "rb") as f:
        sie_text = f.read().decode("cp437")
    parsed = parse_sie(sie_text)
    print(f"Parsed SIE file: {sie_path.name}")

    # Create Fortnox client
    client = FortnoxClient(
        client_id=_require_env("FORTNOX_CLIENT_ID"),
        client_secret=_require_env("FORTNOX_CLIENT_SECRET"),
        tenant_id=_require_env("FORTNOX_TENANT_ID"),
    )

    try:
        seeder = FortnoxSeeder(client, dry_run=args.dry_run)
        await seeder.seed_all(
            parsed,
            skip_vouchers=args.skip_vouchers,
            strip_dimensions=args.strip_dimensions,
            force_series=args.force_series,
        )
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed Fortnox sandbox with SIE data"
    )
    parser.add_argument(
        "sie_file",
        help="Path to anonymized SIE file (e.g., tests/fixtures/demo_2026.se)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and show what would be created, without making API calls",
    )
    parser.add_argument(
        "--skip-vouchers",
        action="store_true",
        help="Skip voucher creation (only seed accounts, CC, projects)",
    )
    parser.add_argument(
        "--strip-dimensions",
        action="store_true",
        help="Remove cost center and project from voucher rows "
             "(workaround for inactive CC scope issues)",
    )
    parser.add_argument(
        "--force-series",
        default=None,
        help="Force all vouchers into this series (e.g., 'A'). "
             "Workaround for non-manual series in sandbox.",
    )
    args = parser.parse_args()

    asyncio.run(run(args))
