"""SIE-to-Supabase sync pipeline.

Fetches SIE data from Fortnox (or reads from a local file),
parses it, and loads into Supabase.

Usage:
    python sync.py                          # Sync current year, SIE type 4
    python sync.py --sie-type 2             # Only period balances (faster)
    python sync.py --year-date 2025-06-15   # Specific fiscal year
    python sync.py --dry-run                # Parse only, print summary
    python sync.py --from-file export.se    # Read local SIE file
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment from .env in the same directory as this script
_THIS_DIR = Path(__file__).resolve().parent
load_dotenv(_THIS_DIR / ".env")

from sie_parser import parse_sie  # noqa: E402
from fortnox_sie_client import FortnoxSIEClient  # noqa: E402
from supabase_loader import SupabaseLoader  # noqa: E402


async def main(args: argparse.Namespace) -> None:
    """Run the SIE sync pipeline."""
    fortnox: FortnoxSIEClient | None = None
    loader: SupabaseLoader | None = None

    try:
        # -----------------------------------------------------------
        # Step 1: Get SIE text (from file or Fortnox API)
        # -----------------------------------------------------------
        if args.from_file:
            file_path = Path(args.from_file)
            if not file_path.exists():
                print(f"ERROR: File not found: {file_path}", file=sys.stderr)
                sys.exit(1)

            with open(file_path, "rb") as f:
                sie_text = f.read().decode("cp437")
            print(f"Read SIE from file: {file_path}")

        else:
            # Fetch from Fortnox API
            fortnox = FortnoxSIEClient(
                client_id=_require_env("FORTNOX_CLIENT_ID"),
                client_secret=_require_env("FORTNOX_CLIENT_SECRET"),
                tenant_id=_require_env("FORTNOX_TENANT_ID"),
            )

            financial_year_id = None
            if args.year_date:
                financial_year_id = await fortnox.get_financial_year_id(
                    args.year_date
                )
                print(
                    f"Resolved financial year ID: {financial_year_id} "
                    f"for date {args.year_date}"
                )

            sie_text = await fortnox.get_sie(
                sie_type=args.sie_type,
                financial_year=financial_year_id,
            )
            print(f"Fetched SIE type {args.sie_type} from Fortnox")

        # -----------------------------------------------------------
        # Step 2: Parse SIE text
        # -----------------------------------------------------------
        parsed = parse_sie(sie_text)

        company = parsed["metadata"].get("company_name", "Unknown")
        sie_type = parsed["metadata"].get("sie_type", "?")
        n_accounts = len(parsed.get("accounts", {}))
        n_vouchers = len(parsed.get("vouchers", []))
        n_period_bal = len(parsed.get("period_balances", []))
        n_ib = len(parsed.get("opening_balances", []))
        n_ub = len(parsed.get("closing_balances", []))
        n_res = len(parsed.get("result_balances", []))
        n_transactions = sum(
            len(v.get("transactions", []))
            for v in parsed.get("vouchers", [])
        )

        print(f"\n--- Parsed SIE type {sie_type} for '{company}' ---")
        print(f"  Accounts:         {n_accounts}")
        print(f"  Opening balances: {n_ib}")
        print(f"  Closing balances: {n_ub}")
        print(f"  Result balances:  {n_res}")
        print(f"  Period balances:  {n_period_bal}")
        print(f"  Vouchers:         {n_vouchers}")
        print(f"  Transactions:     {n_transactions}")

        if args.dry_run:
            print("\n--- Dry run complete (no data loaded) ---")
            if args.verbose:
                print("\nFull parsed output:")
                print(json.dumps(
                    _make_serializable(parsed), indent=2, ensure_ascii=False
                ))
            return

        # -----------------------------------------------------------
        # Step 3: Load to Supabase
        # -----------------------------------------------------------
        loader = SupabaseLoader(
            url=_require_env("SUPABASE_URL"),
            key=_require_env("SUPABASE_SERVICE_KEY"),
            tenant_id=_require_env("TENANT_UUID"),
        )

        loader.update_sync_state(status="running")

        year_id = _resolve_year_id(parsed)
        print(f"\nLoading to Supabase (year_id={year_id})...")

        counts = loader.load_all(parsed, year_id)
        total = sum(
            v if isinstance(v, int) else sum(v)
            for v in counts.values()
        )

        loader.update_sync_state(status="idle", records=total)

        print(f"\n--- Load complete ---")
        for table, count in counts.items():
            print(f"  {table}: {count}")
        print(f"  TOTAL: {total}")

    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        if loader:
            try:
                loader.update_sync_state(status="error", error=str(e))
            except Exception:
                pass  # Don't mask the original error
        raise

    finally:
        if fortnox:
            await fortnox.close()


def _resolve_year_id(parsed: dict) -> int:
    """Extract year_id from parsed SIE financial years.

    Uses the current year (year_offset=0). Falls back to extracting
    the year from the start date.
    """
    for fy in parsed.get("financial_years", []):
        if fy.get("year_offset") == 0:
            start = fy.get("start", "")
            if len(start) >= 4:
                return int(start[:4])
    return 0


def _require_env(name: str) -> str:
    """Get a required environment variable or exit with error."""
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: Missing environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value


def _make_serializable(obj: object) -> object:
    """Convert Decimal and other non-serializable types for JSON output."""
    from decimal import Decimal

    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync SIE data from Fortnox to Supabase"
    )
    parser.add_argument(
        "--sie-type",
        type=int,
        default=4,
        choices=[1, 2, 3, 4],
        help="SIE type: 1=annual, 2=period, 3=object, 4=full (default: 4)",
    )
    parser.add_argument(
        "--year-date",
        help="Date within fiscal year to sync (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--from-file",
        help="Path to a local SIE file (skip Fortnox API fetch)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse only, print summary, don't load to Supabase",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full parsed output (use with --dry-run)",
    )
    args = parser.parse_args()

    asyncio.run(main(args))
