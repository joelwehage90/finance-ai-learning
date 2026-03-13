"""Seed Fortnox sandbox with 20 supplier invoices in March 2026.

Creates invoices with varied suppliers, amounts, accounts and statuses:
- Some booked (-> unpaid or overdue depending on due date)
- Some unbooked
- Some cancelled
- Various expense accounts and amounts

Key learnings from Fortnox API:
- The TOT row (account 2440 Leverantorsskulder) must be included
  explicitly with the correct Credit amount for the invoice to balance.
- "Credit" field on the invoice is read-only; cannot be set on create.
- Invoices must balance (debit == credit) before they can be booked.

Usage:
    .venv/bin/python3 seed_supplier_invoices.py
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent / ".env")

from fortnox_client import FortnoxClient


# 20 invoices to create -- varied suppliers, accounts, amounts, due dates
INVOICES = [
    # supplier, account, description, amount, invoice_date, due_date, action
    # action: "none" = leave unbooked, "book" = book it, "cancel" = cancel it

    # --- Office Depot (201) -- kontorsmaterial ---
    ("201", 6110, "Kontorsmaterial mars",          4_250, "2026-03-01", "2026-03-31", "book"),
    ("201", 6110, "Kopieringspapper",              1_875, "2026-03-05", "2026-04-04", "none"),
    ("201", 5460, "Tangentbord och moss",          8_500, "2026-03-10", "2026-03-25", "book"),

    # --- AWS Sweden (202) -- hosting & cloud ---
    ("202", 6230, "AWS hosting februari",         32_400, "2026-03-01", "2026-03-31", "book"),
    ("202", 6230, "AWS extra compute",            15_750, "2026-03-08", "2026-04-07", "book"),
    ("202", 6230, "AWS S3 lagring",                2_100, "2026-03-15", "2026-04-14", "none"),
    ("202", 6230, "AWS reserverade instanser",    87_600, "2026-03-01", "2026-03-15", "book"),

    # --- Advokatfirman Vinge (203) -- juridik ---
    ("203", 6530, "Juridisk radgivning Q1",       45_000, "2026-03-03", "2026-04-02", "book"),
    ("203", 6530, "Avtalsgranskning",             12_500, "2026-03-12", "2026-04-11", "none"),
    ("203", 6530, "GDPR-utredning",               28_750, "2026-03-01", "2026-03-20", "cancel"),

    # --- Telia (204) -- telefoni & data ---
    ("204", 6210, "Mobilabonnemang mars",          6_800, "2026-03-01", "2026-03-31", "book"),
    ("204", 6210, "Bredband kontor",               3_450, "2026-03-01", "2026-03-31", "book"),
    ("204", 6212, "Mobiltelefon Samsung",         11_990, "2026-03-10", "2026-04-09", "none"),
    ("204", 6210, "Extradata roaming",             1_250, "2026-03-07", "2026-03-21", "cancel"),

    # --- Fastighets AB Lokalen (205) -- hyra & fastighet ---
    ("205", 5010, "Kontorshyra mars",             42_000, "2026-03-01", "2026-03-31", "book"),
    ("205", 5010, "Parkeringsplatser",             3_600, "2026-03-01", "2026-03-31", "book"),
    ("205", 5020, "Uppvarmning mars",              8_900, "2026-03-05", "2026-04-04", "none"),
    ("205", 5050, "Lokalvard mars",                6_250, "2026-03-01", "2026-03-25", "book"),
    ("205", 5010, "Hyrestillagg garage",           5_000, "2026-03-15", "2026-04-14", "none"),
    ("205", 5090, "Reparation konferensrum",      14_300, "2026-03-12", "2026-04-11", "book"),
]


async def create_invoice(
    client: FortnoxClient,
    supplier: str,
    account: int,
    description: str,
    amount: int,
    invoice_date: str,
    due_date: str,
) -> int:
    """Create a supplier invoice and return GivenNumber.

    Includes explicit TOT row (account 2440) so the invoice balances
    and can be booked afterwards.
    """
    rows = [
        # TOT row: leverantorsskulder (credit side)
        {"Account": 2440, "Code": "TOT", "Debit": 0, "Credit": amount},
        # Expense row (debit side)
        {"Account": account, "Debit": amount, "Credit": 0,
         "TransactionInformation": description},
    ]

    body = {
        "SupplierInvoice": {
            "SupplierNumber": supplier,
            "InvoiceDate": invoice_date,
            "DueDate": due_date,
            "Comments": description,
            "Currency": "SEK",
            "SupplierInvoiceRows": rows,
        }
    }

    data = await client.post("/supplierinvoices", json_body=body)
    inv = data.get("SupplierInvoice", data)
    gn = inv.get("GivenNumber")
    total = inv.get("Total", "?")
    print(f"  Created #{gn}  {description:<40s}  {total:>10} SEK")
    return int(gn)


async def book_invoice(client: FortnoxClient, given_number: int) -> None:
    """Book a supplier invoice (changes status to booked/unpaid/overdue)."""
    await client.put(f"/supplierinvoices/{given_number}/bookkeep")
    print(f"  Booked #{given_number}")


async def cancel_invoice(client: FortnoxClient, given_number: int) -> None:
    """Cancel a supplier invoice."""
    await client.put(f"/supplierinvoices/{given_number}/cancel")
    print(f"  Cancelled #{given_number}")


async def main():
    client = FortnoxClient(
        os.environ["FORTNOX_CLIENT_ID"],
        os.environ["FORTNOX_CLIENT_SECRET"],
        os.environ["FORTNOX_TENANT_ID"],
    )

    print(f"=== Creating {len(INVOICES)} supplier invoices ===\n")

    to_book: list[int] = []
    to_cancel: list[int] = []

    for supplier, account, desc, amount, inv_date, due_date, action in INVOICES:
        gn = await create_invoice(
            client, supplier, account, desc, amount, inv_date, due_date
        )
        if action == "book":
            to_book.append(gn)
        elif action == "cancel":
            to_cancel.append(gn)

    print(f"\n=== Booking {len(to_book)} invoices ===\n")
    for gn in to_book:
        try:
            await book_invoice(client, gn)
        except Exception as e:
            print(f"  FAILED to book #{gn}: {e}")

    print(f"\n=== Cancelling {len(to_cancel)} invoices ===\n")
    for gn in to_cancel:
        try:
            await cancel_invoice(client, gn)
        except Exception as e:
            print(f"  FAILED to cancel #{gn}: {e}")

    # Summary
    print("\n=== Summary ===")
    print(f"  Created:   {len(INVOICES)}")
    print(f"  Booked:    {len(to_book)}")
    print(f"  Cancelled: {len(to_cancel)}")
    print(f"  Unbooked:  {len(INVOICES) - len(to_book) - len(to_cancel)}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
