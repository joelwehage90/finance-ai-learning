# Fortnox MCP Server

MCP-server som exponerar Fortnox API som tools för Claude Code/Desktop.

## Tools

| Tool | Beskrivning |
|---|---|
| `list_invoices` | Lista kundfakturor (filter: status, datum, kund) |
| `get_invoice` | Hämta en specifik faktura med alla detaljer |
| `list_customers` | Lista kunder (sökfilter) |
| `get_account_balances` | Kontosaldon per räkenskapsår (BAS-kontoplan) |
| `get_company_info` | Företagsinformation (namn, org.nr, adress) |

## Setup

### 1. Installera dependencies

```bash
cd projects/fortnox-mcp
pip install -r requirements.txt
```

### 2. Konfigurera credentials

```bash
cp .env.example .env
```

Fyll i `FORTNOX_CLIENT_ID` och `FORTNOX_CLIENT_SECRET` från Fortnox Developer Portal.

### 3. Kör OAuth-setup (en gång)

```bash
python auth_setup.py
```

Detta öppnar en webbläsare där du loggar in på Fortnox och godkänner scopesen.
Skriptet sparar `FORTNOX_TENANT_ID` automatiskt till `.env`.

### 4. Testa servern

```bash
python fortnox_server.py
```

### 5. Anslut till Claude Code

`.mcp.json` i projektroten konfigurerar anslutningen automatiskt.
Starta Claude Code i repots rotmapp — servern ska dyka upp under `/mcp`.

Sätt environment-variablerna så Claude Code hittar dem:

```bash
export FORTNOX_CLIENT_ID=ditt_id
export FORTNOX_CLIENT_SECRET=din_secret
export FORTNOX_TENANT_ID=ditt_tenant_id
```

Alternativt: skapa en `.env` i projektroten (inte bara i fortnox-mcp-mappen).

## Autentisering

Servern använder Fortnox Client Credentials-flow (dec 2025):
- Begär ny access token automatiskt vid behov
- Ingen refresh token att hantera
- Kräver: ClientId + ClientSecret + TenantId

## Begränsningar (MVP)

- Enbart read-only — inga skrivoperationer
- Ingen WebSocket-integration (polling only)
- Rate limit: 25 req/5s — hanteras med automatisk retry
