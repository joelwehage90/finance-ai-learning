# Fortnox API

## Vad det är

Fortnox exponerar ett REST API (v3) som ger programmatisk åtkomst till bokföring, fakturering, kunder, leverantörer och mer. Base URL: `https://api.fortnox.se/3/`. API:t använder JSON (XML stöds men avråds), OAuth2 för autentisering, och har 57+ resursendpoints.

## Varför det är viktigt

Fortnox API är grunden för alla integrationer — Finance AI Agent, Excel add-in, MCP-server, databassynk. Utan API-förståelse kan vi inte bygga något av det vi planerar.

## Ekonomiexempel

En controller vill automatisera månadsrapportering: hämta resultaträkning via SIE-export, jämföra mot budget i Supabase, och generera avvikelserapport med Claude. Hela flödet börjar med Fortnox API-anrop.

---

## 1. Autentisering (OAuth2)

### Flödet

```
1. Användare → apps.fortnox.se/oauth-v1/auth (login + godkänn scopes)
2. Fortnox → redirect_uri med authorization code (giltig 10 min, engångs)
3. Din app → POST apps.fortnox.se/oauth-v1/token (byt code mot tokens)
4. Fortnox → access_token (JWT, 1h) + refresh_token (45 dagar, engångs)
5. Din app → GET api.fortnox.se/3/... med Bearer {access_token}
```

### Authorization request

```
GET https://apps.fortnox.se/oauth-v1/auth
  ?client_id={Client-ID}
  &redirect_uri=https://mysite.org/activation
  &scope=companyinformation bookkeeping invoice
  &state=somestate123
  &access_type=offline
  &response_type=code
  &account_type=service
```

- `access_type=offline` — krävs för att få refresh token
- `account_type=service` — för tjänstekonton (ej kopplat till specifik användare)

### Token exchange

```bash
curl -X POST "https://apps.fortnox.se/oauth-v1/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic {Base64(ClientId:ClientSecret)}" \
  -d "code={authorization_code}" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=https://mysite.org/activation"
```

### Client Credentials (nytt dec 2025 — rekommenderas)

För servicekonton finns nu Client Credentials-flow. Kräver engångs-setup via Authorization Code Flow (med `account_type=service`), därefter kan du begära nya access tokens utan refresh tokens:

```bash
curl -X POST "https://apps.fortnox.se/oauth-v1/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic {Base64(ClientId:ClientSecret)}" \
  -H "TenantId: {TenantId}" \
  -d "grant_type=client_credentials"
```

Returnerar enbart access token (1h). Ingen refresh token. Begär ny vid behov.

**Hämta TenantId:** Decode JWT-payload från access token, eller hämta `DatabaseNumber` från `/3/companyinformation`.

### Refresh (legacy — behövs ej med Client Credentials)

```bash
curl -X POST "https://apps.fortnox.se/oauth-v1/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Authorization: Basic {Base64(ClientId:ClientSecret)}" \
  -d "grant_type=refresh_token" \
  -d "refresh_token={Refresh-Token}"
```

### Token-livslängder

| Token | Livslängd | Anmärkning |
|---|---|---|
| Authorization code | 10 min | Engångs |
| Access token (JWT) | 1 timme | Bearer-header |
| Refresh token | 45 dagar | Engångs — nytt returneras vid varje refresh |

### Kritiska gotchas

- **Refresh token är engångs** — efter användning invalideras det, nytt returneras
- **Concurrent refresh race condition** — två processer som refreshar samtidigt invaliderar varandras tokens. Använd seriell/blockande refresh-logik
- **Ingen Client Credentials-flow** — kräver alltid användarinteraktion för initial auth
- **Alla scopes ger read+write** — det finns ingen read-only-åtkomst
- **Scope-ändringar kräver ny auktorisering** — kunden måste återaktivera integrationen
- **Legacy-tokens avvecklades 30 april 2025** — alla integrationer måste använda OAuth2/JWT
- **TLS 1.2+ krävs**

---

## 2. Scopes

Alla scopes ger både läs- och skrivåtkomst. Kunden måste ha rätt Fortnox-licens (modul) för att scopet ska fungera.

| Scope | Ger åtkomst till |
|---|---|
| `bookkeeping` | Konton, verifikationer, verifikationsserier, räkenskapsår, SIE, kontoplaner |
| `invoice` | Kundfakturor, faktureraperiodiseringar, skattereduktioner, kontrakt |
| `payment` | Kundbetalningar, leverantörsbetalningar |
| `customer` | Kunder |
| `supplier` | Leverantörer |
| `supplierinvoice` | Leverantörsfakturor |
| `project` | Projekt |
| `costcenter` | Kostnadsställen |
| `currency` | Valutor |
| `companyinformation` | Företagsinformation |
| `settings` | Företagsinställningar, etiketter, låst period, fördefinierade konton |
| `article` | Artiklar/produkter |
| `order` | Order |
| `offer` | Offerter |
| `salary` | Lön |
| `archive` | Arkiv |
| `assets` | Anläggningstillgångar |
| `inbox` | Inkorg |
| `profile` | Användarprofil |
| `timereporting` | Tidrapportering |
| `noxfinansinvoice` | Nox Finans (factoring) |

---

## 3. Rate limits

| Regel | Värde |
|---|---|
| Requests per 5 sekunder | 25 (sliding window) |
| Requests per minut | 300 |
| Per | client-id + tenant-kombination |
| HTTP vid överskridande | 429 Too Many Requests |

Två tokens för samma tenant delar samma gräns. Implementera exponential backoff vid 429.

---

## 4. Request/Response-struktur

### Headers

```
Authorization: Bearer {Access-Token}
Accept: application/json
Content-Type: application/json
```

### List-response (med pagination)

```json
{
  "MetaInformation": {
    "@TotalResources": 1210,
    "@TotalPages": 13,
    "@CurrentPage": 1
  },
  "Customers": [
    { "CustomerNumber": "1", "Name": "Acme AB" }
  ]
}
```

### Single-resource response

```json
{
  "Customer": {
    "CustomerNumber": "1",
    "Name": "Acme AB",
    "Email": "info@acme.se"
  }
}
```

### Felmeddelanden (ofta på svenska)

```json
{
  "ErrorInformation": {
    "error": 1,
    "message": "Kan inte hitta kontot.",
    "code": 2000423
  }
}
```

### Pagination & filtrering

| Parameter | Beskrivning | Default | Max |
|---|---|---|---|
| `limit` | Poster per sida | 100 | 500 |
| `page` | Sidnummer | 1 | — |
| `offset` | Startposition | 0 | — |
| `lastmodified` | Ändrade efter tidpunkt | — | Format: `2026-03-10 12:30` |
| `fromdate` / `todate` | Datumintervall (fakturor, verifikationer, order, offerter) | — | `YYYY-MM-DD` |
| `filter` | Resursspecifikt filter | — | `unpaid`, `unbooked`, `cancelled` etc. |
| `sortby` / `sortorder` | Sortering | — | `ascending` / `descending` |

**OBS:** `fromdate`/`todate` fungerar bara på fakturor, verifikationer, order och offerter — inte leverantörsfakturor.

---

## 5. Endpoints — Bokföring

### 5.1 Verifikationer (Vouchers)

**Scope:** `bookkeeping` — Verifikationer är **oföränderliga** (ingen PUT/DELETE). Korrigeringar görs med nya verifikationer.

| Operation | Metod | Endpoint |
|---|---|---|
| Lista | GET | `/3/vouchers?financialyear={id}` |
| Lista per serie | GET | `/3/vouchers/sublist/{Series}` |
| Hämta en | GET | `/3/vouchers/{Series}/{Number}?financialyear={id}` |
| Skapa | POST | `/3/vouchers` |

**Skapa verifikation:**

```json
{
  "Voucher": {
    "Description": "Hyra kontor december",
    "TransactionDate": "2026-01-31",
    "VoucherSeries": "A",
    "VoucherRows": [
      { "Account": 5010, "Debit": 15000, "Credit": 0 },
      { "Account": 1930, "Debit": 0, "Credit": 15000 }
    ]
  }
}
```

**Rekommenderat arbetsflöde före skapande:**
1. Validera räkenskapsår: `GET /3/financialyears/?date={date}`
2. Validera konton: `GET /3/accounts/{number}`
3. Validera verifikationsserie: `GET /3/voucherseries/{code}?financialyeardate={date}`
4. (Valfritt) Ladda upp underlag: `POST /3/inbox?path=Inbox_v` → `POST /3/voucherfileconnections`
5. Skapa verifikationen: `POST /3/vouchers`

### 5.2 Konton (Accounts)

**Scope:** `bookkeeping`

| Operation | Metod | Endpoint |
|---|---|---|
| Lista | GET | `/3/accounts?financialyear={id}` |
| Hämta ett | GET | `/3/accounts/{Number}` |
| Skapa | POST | `/3/accounts` |
| Uppdatera | PUT | `/3/accounts/{Number}` |
| Radera | DELETE | `/3/accounts/{Number}` |
| Kontoplaner (BAS-versioner) | GET | `/3/accountcharts` |
| Fördefinierade konton | GET | `/3/predefinedaccounts` |

**Viktiga fält:** `Number`, `Description`, `Active`, `BalanceBroughtForward`, `BalanceCarriedForward`, `SRU`, `VATCode`, `CostCenter`, `Project`, `Year`

### 5.3 Räkenskapsår (Financial Years)

| Operation | Metod | Endpoint |
|---|---|---|
| Lista | GET | `/3/financialyears` |
| Hämta via ID | GET | `/3/financialyears/{Id}` |
| Hitta via datum | GET | `/3/financialyears/?date={YYYY-MM-DD}` |
| Skapa | POST | `/3/financialyears` |

**Vanligt integrationsproblem:** Glömma att skapa nytt räkenskapsår vid årsskifte.

### 5.4 SIE-export

| Operation | Metod | Endpoint |
|---|---|---|
| Exportera SIE | GET | `/3/sie/{Type}` |

| Typ | Innehåll |
|---|---|
| 1 | Årssaldon (ingående/utgående) |
| 2 | Periodsaldon |
| 3 | Saldon med objektnivå (kostnadsställen, projekt) |
| 4 | Fullständig transaktionsexport |

**OBS:** SIE-**import** finns INTE via API:t — måste göras via Fortnox UI.

### 5.5 Låst period

```
GET /3/lockedperiod
```

Visar till vilket datum bokföringen är låst — viktigt för att validera om transaktionsdatum är öppet.

---

## 6. Endpoints — Resultaträkning & Balansräkning

**Det finns inga dedikerade rapport-endpoints** (ingen `/3/reports/profitandloss`). Tre strategier:

### Strategi A: SIE-export (rekommenderas)

```
GET /3/sie/4?financialyear={id}
```

SIE Typ 4 ger fullständig transaktionsdata. Parsa SIE-filen och beräkna:
- **Kontoklass 1** (1000–1999): Tillgångar
- **Kontoklass 2** (2000–2999): Eget kapital och skulder
- **Kontoklass 3** (3000–3999): Intäkter
- **Kontoklass 4–8** (4000–8999): Kostnader

### Strategi B: Aggregera från konton/verifikationer

1. Hämta alla konton med saldon: `GET /3/accounts?financialyear={id}`
2. Hämta verifikationer för perioden: `GET /3/vouchers?financialyear={id}&fromdate=...&todate=...`
3. Summera per kontoklass

### Strategi C: Tredjepartsverktyg

Fortnox2Google, Zwapgrid m.fl. erbjuder färdig P&L/BR-extraktion.

---

## 7. Endpoints — Fakturering

### 7.1 Kundfakturor (Invoices)

**Scope:** `invoice`

| Operation | Metod | Endpoint |
|---|---|---|
| Lista | GET | `/3/invoices` |
| Hämta | GET | `/3/invoices/{DocumentNumber}` |
| Skapa | POST | `/3/invoices` |
| Uppdatera | PUT | `/3/invoices/{DocumentNumber}` |
| Bokför | PUT | `/3/invoices/{DocumentNumber}/bookkeep` |
| Makulera | PUT | `/3/invoices/{DocumentNumber}/cancel` |
| Kreditera | PUT | `/3/invoices/{DocumentNumber}/credit` |
| Skicka e-post | GET/PUT | `/3/invoices/{DocumentNumber}/email` |
| Skriv ut (PDF) | GET | `/3/invoices/{DocumentNumber}/print` |

**Filter:** `?filter=unpaid`, `?filter=unbooked`, `?filter=cancelled`, `?customername=Acme`

### 7.2 Leverantörsfakturor (Supplier Invoices)

**Scope:** `supplierinvoice`

| Operation | Metod | Endpoint |
|---|---|---|
| Lista | GET | `/3/supplierinvoices` |
| Hämta | GET | `/3/supplierinvoices/{GivenNumber}` |
| Skapa | POST | `/3/supplierinvoices` |
| Uppdatera | PUT | `/3/supplierinvoices/{GivenNumber}` |
| Bokför | PUT | `/3/supplierinvoices/{GivenNumber}/bookkeep` |

**OBS:** `fromdate`/`todate` stöds ej — använd `lastmodified` för inkrementell synk.

**Viktiga skillnader mot kundfakturor (lärt oss vid sandbox-test):**
- Rader heter `SupplierInvoiceRows` (inte `InvoiceRows`)
- Kontofältet heter `Account` (inte `AccountNumber`)
- `Description` finns inte på radnivå — använd `Comments` på fakturanivå

### 7.3 Betalningar

**Scope:** `payment`

| Resurs | Endpoint |
|---|---|
| Kundbetalningar | `/3/invoicepayments` |
| Leverantörsbetalningar | `/3/supplierinvoicepayments` |

### 7.4 Periodiseringar

| Resurs | Endpoint |
|---|---|
| Kundfakturaperiodiseringar | `/3/invoiceaccruals` |
| Leverantörsfakturaperiodiseringar | `/3/supplierinvoiceaccruals` |

### 7.5 Skattereduktioner (ROT/RUT/Grönt)

**Scope:** `invoice`

```
GET/POST/PUT/DELETE /3/taxreductions
```

`TypeOfReduction`: `ROT`, `RUT`, eller `GREEN`

---

## 8. Endpoints — Övriga resurser

| Resurs | Scope | Endpoint | CRUD |
|---|---|---|---|
| Kunder | `customer` | `/3/customers` | Alla |
| Leverantörer | `supplier` | `/3/suppliers` | Alla |
| Projekt | `project` | `/3/projects` | Alla |
| Kostnadsställen | `costcenter` | `/3/costcenters` | Alla |
| Valutor | `currency` | `/3/currencies` | Alla |
| Artiklar | `article` | `/3/articles` | Alla |
| Order | `order` | `/3/orders` | Alla |
| Offerter | `offer` | `/3/offers` | Alla |
| Företagsinformation | `companyinformation` | `/3/companyinformation` | Enbart GET |
| Företagsinställningar | `settings` | `/3/companysettings` | Enbart GET |

---

## 9. WebSocket — Realtidsnotifieringar

Fortnox använder WebSocket (inte HTTP-webhooks) för realtidshändelser.

### Anslutning

```
wss://ws.fortnox.se/topics-v1
```

En anslutning per integration (inte per kund).

### Stödda topics

Invoices, Invoice Payments, Invoice Reminders, Supplier Invoices, Customers, Orders, Offers, Articles, Projects, Vouchers, Financial Years, Currencies, Delivery Types/Terms, Terms of Payments, Warehouse Stock Balances.

### Kommandon

```json
// 1. Lägg till tenants
{ "command": "add-tenants-v1", "clientSecret": "...", "accessTokens": ["Bearer ..."] }

// 2. Lägg till topics
{ "command": "add-topics", "topics": [{ "topic": "invoices" }, { "topic": "customers", "offset": "xDy7J" }] }

// 3. Starta prenumeration
{ "command": "subscribe" }
```

### Event-format

```json
{
  "topic": "invoices",
  "offset": "xDy7J",
  "type": "invoicepayment-bookkeep-v1",
  "tenantId": 29302,
  "entityId": "3817",
  "timestamp": "2026-01-28T14:59:16.500+01:00"
}
```

### Egenskaper

- **At-least-once delivery** — deduplicera med offset
- **Minimal payload** — bara entity ID + event type, hämta detaljer via REST
- **14 dagars replay** — ange offset per topic vid återanslutning
- **Ordningsgaranti** inom varje topic

---

## 10. Bibliotek & SDK:er

### Python — `fortpyx` (rekommenderas)

```bash
pip install fortpyx
```

- Autogenererad från Fortnox OpenAPI-spec
- Pydantic 2-modeller, full typing
- Automatisk token-förnyelse med callback hooks
- Stöd för alla endpoints, paginering

### Andra Python-paket

| Paket | Status | OAuth2 |
|---|---|---|
| `pyfortnox` | Inaktivt | Delvis |
| `fortnox` | Minimalt | Okänt |

### TypeScript — `@rantalainen/fortnox-api-client`

```bash
npm i @rantalainen/fortnox-api-client
```

- Autogenererad från OpenAPI
- Full TypeScript-typning
- Inbyggd OAuth2-tokenhantering

### Andra

| Språk | Paket | Notering |
|---|---|---|
| C# | Fortnox.NET.SDK (NuGet) | Inkl. WebSocket-stöd |
| Ruby | fortnox-api gem | OAuth2 från v0.9.0 |
| Power Automate | Custom Connector (GitHub) | Swagger-fil tillgänglig |

---

## 11. Integrationsmönster

### 11.1 Databassynk (Fortnox → Supabase/PostgreSQL)

```
Fortnox API → [lastmodified + pagination] → Staging → [UPSERT] → Final Tables
                                                          |
                                                    Sync State Table
```

**Inkrementell synk:**
1. Lagra `last_sync_timestamp` per entitetstyp
2. Fråga med `?lastmodified={timestamp}&limit=500`
3. Paginera genom alla sidor
4. UPSERT i PostgreSQL med `INSERT ... ON CONFLICT DO UPDATE`
5. Uppdatera sync state

**Hantera raderingar:** Fortnox exponerar ingen soft-delete-flagga. Strategier:
- **Reconciliation:** Hämta alla ID:n periodiskt, jämför mot DB, markera saknade med `deleted_at`
- **Aldrig hard-delete lokalt** — behåll audit trail

**Throughput:** ~150 000 poster/minut med `limit=500`

**Schema-exempel:**
```sql
CREATE TABLE fortnox_sync_state (
    entity_type TEXT PRIMARY KEY,
    last_sync_timestamp TIMESTAMPTZ,
    last_full_sync TIMESTAMPTZ,
    records_synced INTEGER
);

CREATE TABLE fortnox_invoices (
    invoice_number TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 11.2 Excel Add-in

**Rekommendation: xlwings + Python-backend**

```
Excel (Office.js add-in) → xlwings Server (Python) → fortpyx → Fortnox API
```

- Python-backend anropar Fortnox via `fortpyx`, pushar data till Excel
- Custom functions kan definieras som drar Fortnox-data direkt till celler
- Fungerar med Excel på web, Windows och macOS

**Alternativ:** Office.js + TypeScript direkt, Power Automate Custom Connector, Zapier som brygga.

### 11.3 MCP-server (Fortnox → Claude)

**Ingen dedikerad Fortnox MCP-server finns ännu** — tydlig möjlighet att bygga en.

Konceptuellt:
```python
from mcp.server import Server
from fortpyx import FortnoxClient

server = Server("fortnox-mcp")

@server.tool("list_invoices")
async def list_invoices(status: str = None, from_date: str = None):
    """List invoices, optionally filtered by status and date."""
    client = FortnoxClient(...)
    return client.invoices.list(filter=status, lastmodified=from_date)
```

**Föreslagna MCP-tools:**
- `list_invoices` — med filter för status, datumintervall, kund
- `get_invoice` — fullständiga detaljer
- `list_customers` — med sök/filter
- `get_account_balances` — kontosaldon
- `export_sie` — SIE-export för rapporter
- `list_vouchers` — verifikationer per period
- `get_company_info` — grundläggande bolagsdata
- `create_voucher` — med bekräftelsesteg (human-in-the-loop)

### 11.4 Direkt från Claude Code

```python
# Ad hoc-förfrågning via Python-skript
from fortpyx import FortnoxClient
client = FortnoxClient(client_id='...', access_token='...')
invoices = client.invoices.list(limit=10)
for inv in invoices:
    print(f'{inv.DocumentNumber}: {inv.Total} kr - {inv.CustomerName}')
```

---

## 12. Kända begränsningar & quirks

| Problem | Detalj |
|---|---|
| Verifikationer oföränderliga | Ingen PUT/DELETE — korrigera med ny verifikation |
| SIE-import ej via API | Enbart export (GET). Import via UI |
| Inga rapport-endpoints | Ingen P&L/BR — beräkna från SIE eller konton/verifikationer |
| `fromdate`/`todate` begränsat | Bara fakturor, verifikationer, order, offerter |
| List-responses partiella | Sammanfattning — hämta detaljer per ID |
| Alla scopes read+write | Ingen read-only-åtkomst |
| Radering "tyst" | Raderade poster försvinner bara — ingen soft-delete-flagga |
| `API_BLANK` för att tömma fält | Sätt ett fält till strängen `API_BLANK` för att rensa det |
| Rate limit delad | Två tokens för samma tenant delar gräns |
| Sandbox kräver räkenskapsår | Måste skapas manuellt med kontoplan (t.ex. "Bas 2025") |
| Fältnamn inkonsistenta | Kundfaktura: `InvoiceRows`/`AccountNumber`. Leverantörsfaktura: `SupplierInvoiceRows`/`Account` |
| Kontoplansnamn exakt match | `BAS2024` fungerar inte — måste vara `Bas 2025` (med mellanslag) |
| Licenskrav | Kunden måste ha rätt Fortnox-modul för varje scope |
| Sandbox-limit | Max 30 testmiljöer via Developer Portal |
| Concurrent refresh-race | Serialisera token-refresh — annars invalideras tokens |

---

## Developer Portal & sandbox

1. Registrera på [fortnox.se/developer/developer-portal](https://www.fortnox.se/developer/developer-portal)
2. Fortnox lägger till developer-licens på ditt konto
3. Skapa integrationer med Client-ID + Client-Secret i portalen
4. Skapa upp till 30 testmiljöer (sandbox-bolag)
5. Testa mot sandbox precis som produktion

---

## Officiella resurser

| Resurs | URL |
|---|---|
| API-dokumentation (Swagger) | apps.fortnox.se/apidocs |
| Experimentella endpoints | apps.fortnox.se/apidocs/experimental |
| Developer Portal | fortnox.se/developer/developer-portal |
| Auktoriseringsguide | fortnox.se/developer/authorization |
| Scopes | fortnox.se/developer/guides-and-good-to-know/scopes |
| Rate limits | fortnox.se/developer/guides-and-good-to-know/rate-limits-for-fortnox-api |
| WebSockets | fortnox.se/developer/guides-and-good-to-know/websockets |
| Parametrar | fortnox.se/developer/guides-and-good-to-know/parameters |
| Felhantering | fortnox.se/developer/guides-and-good-to-know/errors |
| Best practices (verifikationer) | fortnox.se/developer/guides-and-good-to-know/best-practices/vouchers |
| Best practices (fakturor) | fortnox.se/developer/guides-and-good-to-know/best-practices/finance-invoice |
| FAQ | fortnox.se/developer/faq |
| Integrationschecklista | fortnox.se/developer/checklist |
| OpenAPI-spec | api.fortnox.se/apidocs (nedladdningsbar) |
| fortpyx (PyPI) | pypi.org/project/fortpyx |
| fortnox-api-client (npm) | npmjs.com/package/@rantalainen/fortnox-api-client |

## Vad jag fortfarande behöver förstå bättre

<!-- TODO: Testa OAuth2-flödet praktiskt med Developer Portal -->
<!-- TODO: Verifiera att fortpyx fungerar med aktuell API-version -->
<!-- TODO: Undersöka experimentella endpoints — finns rapport-endpoints där? -->
<!-- TODO: Parsa SIE4-format i Python — finns det bibliotek? -->
<!-- TODO: Webhooks vs polling — vad är mest praktiskt för olika use cases? -->

## Relaterade koncept

- **Tool Use** — Fortnox-endpoints blir tools i en agent (se concepts/tool-use.md)
- **MCP** — Fortnox MCP-server exponerar tools/resources för Claude (se instuderingsplan Modul 4)
- **Structured Outputs** — Fortnox JSON-data → Claude-analys → strukturerat svar
