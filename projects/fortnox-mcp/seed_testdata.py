"""Seed Fortnox sandbox with test data for development.

Creates a realistic set of customers, suppliers, and invoices
for a small Swedish consulting company. Run once against your sandbox.

Prerequisites:
    - Financial years must exist (the script creates them if missing)
    - .env must be configured with valid credentials

Usage:
    python seed_testdata.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fortnox_client import FortnoxClient


async def safe_post(client: FortnoxClient, path: str, body: dict, label: str) -> bool:
    """POST to Fortnox API with error handling. Returns True on success."""
    try:
        await client._ensure_token()
        response = await client._http.request(
            "POST", path, json=body,
            headers={
                "Authorization": f"Bearer {client._access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        if response.status_code in (200, 201):
            print(f"  OK: {label}")
            return True
        else:
            error = response.json().get("ErrorInformation", {})
            msg = error.get("message", response.text[:200])
            print(f"  SKIP: {label} - {msg}")
            return False
    except Exception as e:
        print(f"  FAIL: {label} - {e}")
        return False


async def seed():
    client = FortnoxClient(
        client_id=os.environ["FORTNOX_CLIENT_ID"],
        client_secret=os.environ["FORTNOX_CLIENT_SECRET"],
        tenant_id=os.environ["FORTNOX_TENANT_ID"],
    )

    try:
        # --- Ensure financial years exist ---
        print("Kontrollerar rakenskapsaar...")
        fy_data = await client.get("/financialyears")
        existing_years = [fy["FromDate"][:4] for fy in fy_data.get("FinancialYears", [])]

        if "2025" not in existing_years:
            await safe_post(client, "/financialyears", {
                "FinancialYear": {
                    "FromDate": "2025-01-01", "ToDate": "2025-12-31",
                    "AccountingMethod": "ACCRUAL", "AccountChartType": "Bas 2025",
                }
            }, "Rakenskapsaar 2025")

        if "2026" not in existing_years:
            await safe_post(client, "/financialyears", {
                "FinancialYear": {
                    "FromDate": "2026-01-01", "ToDate": "2026-12-31",
                    "AccountingMethod": "ACCRUAL",
                }
            }, "Rakenskapsaar 2026")

        # --- Customers ---
        # Using 3001 (Forsaljning inom Sverige, 25% moms) as revenue account
        customers = [
            {"CustomerNumber": "101", "Name": "Nordstrom Konsult AB", "City": "Stockholm", "OrganisationNumber": "556789-0123"},
            {"CustomerNumber": "102", "Name": "Bergqvist och Partners", "City": "Goteborg", "OrganisationNumber": "556456-7890"},
            {"CustomerNumber": "103", "Name": "Solberga Fastigheter AB", "City": "Malmo", "OrganisationNumber": "559012-3456"},
            {"CustomerNumber": "104", "Name": "Eriksson Bygg och Montage", "City": "Uppsala", "OrganisationNumber": "556234-5678"},
            {"CustomerNumber": "105", "Name": "Lindgren Digital AB", "City": "Linkoping", "OrganisationNumber": "559876-5432"},
        ]

        print("\nSkapar kunder...")
        for c in customers:
            await safe_post(client, "/customers", {"Customer": c}, c["Name"])

        # --- Suppliers ---
        suppliers = [
            {"SupplierNumber": "201", "Name": "Office Depot Sverige", "City": "Stockholm"},
            {"SupplierNumber": "202", "Name": "AWS Sweden AB", "City": "Stockholm"},
            {"SupplierNumber": "203", "Name": "Advokatfirman Vinge", "City": "Goteborg"},
            {"SupplierNumber": "204", "Name": "Telia Company AB", "City": "Stockholm"},
            {"SupplierNumber": "205", "Name": "Fastighets AB Lokalen", "City": "Malmo"},
        ]

        print("\nSkapar leverantorer...")
        for s in suppliers:
            await safe_post(client, "/suppliers", {"Supplier": s}, s["Name"])

        # --- Customer invoices ---
        # Account 3001 = Forsaljning inom Sverige 25% moms
        invoices = [
            {
                "CustomerNumber": "101",
                "InvoiceDate": "2026-01-15",
                "DueDate": "2026-02-14",
                "InvoiceRows": [
                    {"AccountNumber": 3001, "Description": "Managementkonsulting jan 2026", "DeliveredQuantity": 40, "Price": 1500},
                ],
            },
            {
                "CustomerNumber": "102",
                "InvoiceDate": "2026-02-01",
                "DueDate": "2026-03-03",
                "InvoiceRows": [
                    {"AccountNumber": 3001, "Description": "CFO-tjanster feb 2026", "DeliveredQuantity": 60, "Price": 1400},
                    {"AccountNumber": 3001, "Description": "Arsredovisning 2025", "DeliveredQuantity": 1, "Price": 25000},
                ],
            },
            {
                "CustomerNumber": "103",
                "InvoiceDate": "2026-02-15",
                "DueDate": "2026-03-17",
                "InvoiceRows": [
                    {"AccountNumber": 3001, "Description": "Ekonomianalys Q4 2025", "DeliveredQuantity": 1, "Price": 45000},
                ],
            },
            {
                "CustomerNumber": "104",
                "InvoiceDate": "2026-03-01",
                "DueDate": "2026-03-31",
                "InvoiceRows": [
                    {"AccountNumber": 3001, "Description": "Lopande bokforing mars 2026", "DeliveredQuantity": 20, "Price": 1200},
                ],
            },
            {
                "CustomerNumber": "105",
                "InvoiceDate": "2026-03-05",
                "DueDate": "2026-04-04",
                "InvoiceRows": [
                    {"AccountNumber": 3001, "Description": "Budget och prognos 2026", "DeliveredQuantity": 1, "Price": 35000},
                    {"AccountNumber": 3001, "Description": "Likviditetsplanering", "DeliveredQuantity": 8, "Price": 1500},
                ],
            },
        ]

        print("\nSkapar kundfakturor...")
        for inv in invoices:
            label = f"Kund {inv['CustomerNumber']}: {inv['InvoiceRows'][0]['Description']}"
            await safe_post(client, "/invoices", {"Invoice": inv}, label)

        # --- Supplier invoices ---
        # Account 6310 = Foretagsforsakringar, 5010 = Lokalhyra,
        # 5420 = Programvaror, 6212 = Mobiltelefon, 6530 = Redovisningstjanster
        # SupplierInvoiceRows use "Account" (not "AccountNumber")
        # and don't have "Description" — use "Comments" on the invoice instead
        supplier_invoices = [
            {
                "SupplierNumber": "205", "InvoiceDate": "2026-01-01",
                "DueDate": "2026-01-30", "GivenNumber": "51001",
                "Comments": "Kontorshyra jan 2026",
                "SupplierInvoiceRows": [{"Account": 5010, "Price": 18000, "Quantity": 1}],
            },
            {
                "SupplierNumber": "201", "InvoiceDate": "2026-01-15",
                "DueDate": "2026-02-14", "GivenNumber": "51002",
                "Comments": "Kontorsmaterial Q1",
                "SupplierInvoiceRows": [{"Account": 5460, "Price": 4500, "Quantity": 1}],
            },
            {
                "SupplierNumber": "202", "InvoiceDate": "2026-02-01",
                "DueDate": "2026-03-03", "GivenNumber": "51003",
                "Comments": "AWS hosting feb 2026",
                "SupplierInvoiceRows": [{"Account": 5420, "Price": 8900, "Quantity": 1}],
            },
            {
                "SupplierNumber": "204", "InvoiceDate": "2026-02-15",
                "DueDate": "2026-03-17", "GivenNumber": "51004",
                "Comments": "Mobilabonnemang feb-mar",
                "SupplierInvoiceRows": [{"Account": 6212, "Price": 2400, "Quantity": 1}],
            },
            {
                "SupplierNumber": "203", "InvoiceDate": "2026-03-01",
                "DueDate": "2026-03-31", "GivenNumber": "51005",
                "Comments": "Juridisk radgivning avtal",
                "SupplierInvoiceRows": [{"Account": 6530, "Price": 35000, "Quantity": 1}],
            },
        ]

        print("\nSkapar leverantorsfakturor...")
        for inv in supplier_invoices:
            label = f"Lev.faktura {inv['GivenNumber']}: {inv['Comments']}"
            await safe_post(client, "/supplierinvoices", {"SupplierInvoice": inv}, label)

        print("\nKlart!")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(seed())
