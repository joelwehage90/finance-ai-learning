# Kodgenomgång — Fortnox MCP Server

Denna genomgång går igenom varje fil i projektet, funktion för funktion, och förklarar **vad koden gör** och **varför den gör det**. Målet är att du ska kunna läsa koden själv efteråt och förstå allt.

---

## Filöversikt

```
fortnox-mcp/
├── fortnox_server.py   ← MCP-servern — exponerar tools för Claude
├── fortnox_client.py   ← API-klient — pratar med Fortnox REST API
├── auth_setup.py       ← Engångsscript — OAuth-setup för att få TenantId
├── requirements.txt    ← Python-dependencies
└── .env                ← Credentials (gitignore:ad)
```

**Läsordning:** `fortnox_client.py` → `fortnox_server.py` → `auth_setup.py`. Klienten är grunden, servern bygger ovanpå, och auth-scriptet är en separat engångsprocess.

---

## 1. fortnox_client.py — API-klienten

Den här filen är en Python-klass som hanterar all kommunikation med Fortnox API. Den vet inget om MCP — den är en generell HTTP-klient med autentisering och felhantering.

### Importer och setup

```python
import base64          # För att koda credentials (ClientId:Secret → Base64)
import time            # För att kolla om token har gått ut
from typing import Any, Optional   # Type hints
import httpx           # Async HTTP-bibliotek (modernare alternativ till requests)
```

**Varför httpx istället för requests?** Vår MCP-server är asynkron (async/await), och `requests` stödjer bara synkrona anrop. `httpx` kan göra båda.

### Klassen FortnoxClient

```python
class FortnoxClient:
    BASE_URL = "https://api.fortnox.se/3"
    TOKEN_URL = "https://apps.fortnox.se/oauth-v1/token"
```

Två URL:er — en för data (API) och en för att hämta tokens (OAuth). All Fortnox-data lever under `/3` (API version 3).

### `__init__` — Skapande av klienten

```python
def __init__(self, client_id, client_secret, tenant_id):
    self._client_id = client_id
    self._client_secret = client_secret
    self._tenant_id = tenant_id
    self._access_token = None           # Ingen token ännu
    self._token_expires_at = 0          # Tvingar token-hämtning vid första anrop
    self._http = httpx.AsyncClient(     # Skapar en persistent HTTP-klient
        base_url=self.BASE_URL,
        timeout=30.0,
    )
```

**Nyckelinsikt:** Klienten sparar credentials men hämtar inte token direkt. Tokenen hämtas "lazy" — först när ett faktiskt API-anrop görs. Det kallas **lazy initialization** och är bra praxis eftersom:
- Klienten kan skapas utan nätverksanrop
- Om inget verktyg anropas slösas ingen token

`_http` är en persistent HTTP-klient som återanvänds för alla anrop (effektivare än att skapa ny varje gång — connection pooling).

### `_ensure_token` — Automatisk token-hantering

```python
async def _ensure_token(self):
    # Om vi har en giltig token, gör inget
    if self._access_token and time.time() < self._token_expires_at - 60:
        return

    # Base64-koda ClientId:ClientSecret
    credentials = base64.b64encode(
        f"{self._client_id}:{self._client_secret}".encode()
    ).decode()

    # Begär ny token via Client Credentials flow
    response = await self._http.post(
        self.TOKEN_URL,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {credentials}",
            "TenantId": str(self._tenant_id),
        },
        data={"grant_type": "client_credentials"},
    )
    response.raise_for_status()
    token_data = response.json()

    self._access_token = token_data["access_token"]
    self._token_expires_at = time.time() + token_data.get("expires_in", 3600)
```

**Steg-för-steg:**

1. **Kollar om befintlig token duger** — `time.time() < expires_at - 60` innebär "har mer än 60 sekunder kvar". Marginal på 60 sekunder undviker att token löper ut mitt i ett anrop.

2. **Base64-kodar credentials** — Fortnox kräver att `ClientId:ClientSecret` skickas som Base64 i Authorization-headern. Det är standard för HTTP Basic Auth.

3. **Gör POST till token-endpoint** — `grant_type=client_credentials` talar om att vi vill ha en ny token utan användarinteraktion. `TenantId` i headern anger vilket Fortnox-bolag vi vill komma åt.

4. **Sparar token och utgångstid** — `expires_in` är vanligtvis 3600 (1 timme).

**Controllerrelevans:** Den här mekanismen är varför du aldrig behöver tänka på inloggning — servern förnyar sin egen token automatiskt. Om du frågar Claude klockan 14:00 och sedan klockan 15:30 hämtas en ny token sömlöst.

### `_request` — Kärnan med retry-logik

```python
async def _request(self, method, path, params=None):
    await self._ensure_token()

    for attempt in range(3):   # Max 3 försök
        response = await self._http.request(
            method, path,
            params=params,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json",
            },
        )

        if response.status_code == 429:     # Rate limited
            wait_time = 2 ** attempt         # 1s, 2s, 4s
            await _async_sleep(wait_time)
            continue

        if response.status_code == 401:     # Token expired
            self._access_token = None
            self._token_expires_at = 0
            await self._ensure_token()
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError("Fortnox API request failed after 3 retries")
```

**Tre scenarion hanteras:**

1. **Allt OK (2xx)** — returnera JSON-data direkt.

2. **Rate limit (429)** — Fortnox tillåter 25 requests per 5 sekunder. Vid överträdelse väntar vi med **exponential backoff**: 1 sekund, sedan 2, sedan 4. Varje retry dubblar väntetiden — en standardteknik som undviker att överbelasta API:t.

3. **Token utgått (401)** — Nollställer token och hämtar en ny. Sedan försöker den igen.

**Varför 3 retries?** Ett balanserat val. Färre och du missar tillfälliga problem. Fler och du väntar för länge vid riktiga fel.

### `get` och `get_all_pages` — Publika metoder

```python
async def get(self, path, params=None):
    return await self._request("GET", path, params=params)

async def get_all_pages(self, path, params=None):
    # ... hämtar alla sidor av paginerade resultat
```

`get` är ett enkelt GET-anrop. `get_all_pages` hanterar **pagination** — när Fortnox har fler resultat än vad som ryms på en sida (max 500 per sida). Den loopar genom alla sidor och samlar ihop resultatet till en platt lista.

**Detalj värd att notera:** `get_all_pages` hittar data-nyckeln automatiskt genom att ta den första nyckeln som inte är `MetaInformation`. Det gör den generisk — den fungerar oavsett om svaret innehåller `Invoices`, `Customers` eller `Accounts`.

---

## 2. fortnox_server.py — MCP-servern

Den här filen gör två saker: den skapar en MCP-server och definierar de tools som Claude kan använda. Det är "bryggan" mellan AI-världen och Fortnox-världen.

### Importer och konfiguration

```python
from dotenv import load_dotenv    # Läser .env-filen
from fastmcp import FastMCP       # MCP-ramverket

_THIS_DIR = Path(__file__).resolve().parent    # Mappen där denna fil ligger
sys.path.insert(0, str(_THIS_DIR))             # Gör att vi kan importera fortnox_client
load_dotenv(_THIS_DIR / ".env")                # Laddar credentials från .env
```

**Varför `sys.path.insert`?** MCP-servern kan startas från vilken mapp som helst (via `.mcp.json`). Utan denna rad hittar Python inte `fortnox_client.py` om arbetsmappen är en annan.

**Varför `_THIS_DIR / ".env"` istället för bara `.env`?** Samma anledning — `.env` relativt till serverfilen, inte relativt till var du råkar stå i terminalen.

### Skapa MCP-servern

```python
mcp = FastMCP(
    "Fortnox",
    instructions=(
        "Fortnox accounting API integration for Swedish companies. "
        "Use these tools to query invoices, customers, accounts and "
        "company information from Fortnox. All financial data follows "
        "the BAS account plan (Swedish standard)."
    ),
)
```

`FastMCP` är ramverket som hanterar MCP-protokollet åt oss. Vi ger det:
- **Namn** — "Fortnox" (syns i Claude Code under `/mcp`)
- **Instructions** — beskrivning som hjälper Claude förstå vad servern gör

`instructions` är viktigt. Det är en **system prompt för verktygen** — Claude läser detta för att förstå kontexten. "BAS account plan" hjälper Claude ge relevanta svar om svenska konton.

### Lazy client

```python
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = FortnoxClient(
            os.environ["FORTNOX_CLIENT_ID"],
            os.environ["FORTNOX_CLIENT_SECRET"],
            os.environ["FORTNOX_TENANT_ID"],
        )
    return _client
```

**Singleton-mönster** — en enda FortnoxClient skapas vid behov och återanvänds. Anledningen:
- Undviker att skapa ny klient (och ny HTTP-connection pool) för varje tool-anrop
- Token delas mellan alla anrop
- `os.environ[...]` kraschar tydligt med `KeyError` om credentials saknas

### Tools — Verktygen som Claude kan använda

Varje tool definieras med `@mcp.tool()` och blir automatiskt tillgänglig för Claude.

#### `list_invoices`

```python
@mcp.tool()
async def list_invoices(
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    customer_name: Optional[str] = None,
    limit: int = 25,
) -> str:
    """List customer invoices from Fortnox.

    Args:
        status: Filter by status. Options: "unpaid", "unpaidoverdue", ...
        from_date: Start date filter (YYYY-MM-DD).
        ...
    """
```

**Tre saker händer här som är värda att förstå:**

1. **`@mcp.tool()`** — en **decorator** som registrerar funktionen som ett MCP-verktyg. FastMCP läser funktionens namn, parametrar och docstring och genererar automatiskt tool-definitionen som skickas till Claude.

2. **Type hints (`Optional[str]`, `int`)** — inte bara dokumentation! FastMCP använder dem för att generera JSON-schema som talar om för Claude vilka parametrar som finns och vilka typer de har.

3. **Docstringen** — Claude läser denna bokstavligen för att förstå vad verktyget gör. En bra docstring = Claude använder verktyget rätt. "Options: unpaid, unpaidoverdue..." hjälper Claude veta exakt vilka värden som är giltiga.

**Resten av funktionen:**

```python
    client = _get_client()
    params = {"limit": min(limit, 500)}     # Kappa limit till Fortnox max

    if status:
        params["filter"] = status           # Fortnox API-parameter heter "filter"
    if from_date:
        params["fromdate"] = from_date      # Fortnox vill ha "fromdate" utan underscore

    data = await client.get("/invoices", params=params)

    invoices = data.get("Invoices", [])
    meta = data.get("MetaInformation", {})
    total = meta.get("@TotalResources", len(invoices))

    summary = f"Visar {len(invoices)} av {total} fakturor."
    return _format_response(invoices, summary)
```

**Observation:** Parametrarna till funktionen (`from_date`) har Python-stil med underscore, men de mappas till Fortnox API-stil utan underscore (`fromdate`). Denna translation gör det lättare för Claude att använda — Claude förstår `from_date` bättre.

**Returvärdet** är en **sträng**, inte JSON. Varför? MCP-tools returnerar text som Claude kan läsa. `_format_response` lägger till en sammanfattning ("Visar 7 av 42 fakturor") följt av pretty-printed JSON. Sammanfattningen hjälper Claude snabbt förstå datamängden utan att parsa all JSON.

#### Övriga tools

De andra tools:en (`get_invoice`, `list_customers`, `get_account_balances`, `list_supplier_invoices`, `get_supplier_invoice`, `get_company_info`) följer exakt samma mönster:

1. Hämta klient
2. Bygg parametrar (mappa Python-namn → Fortnox API-namn)
3. Gör API-anrop
4. Extrahera data från response (Fortnox wrappar alltid i en yttrenyckel)
5. Returnera formaterad sträng

#### Startpunkten

```python
if __name__ == "__main__":
    mcp.run()
```

`mcp.run()` startar MCP-servern i stdio-läge — den lyssnar på stdin och svarar på stdout. Claude Code startar denna process och kommunicerar med den.

---

## 3. auth_setup.py — OAuth-setup (engångs)

Den här filen körs **en enda gång** för att godkänna din integration med Fortnox och hämta TenantId. Den behövs inte under daglig användning.

### Flödet i stora drag

```
1. Öppnar webbläsare → Fortnox login
2. Du loggar in och godkänner scopes
3. Fortnox skickar tillbaka en code till localhost:8080
4. Scriptet byter code mot access token
5. Extraherar TenantId från JWT-token
6. Sparar TenantId i .env
```

### Lokal HTTP-server

```python
class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            # ... skickar tillbaka "Auktorisering klar!" till webbläsaren
```

Scriptet startar en tillfällig webserver på port 8080. Varför? OAuth-flödet fungerar så:
1. Du skickas till Fortnox
2. Fortnox skickar tillbaka dig till `http://localhost:8080/callback?code=abc123`
3. Den tillfälliga servern fångar `code`-parametern

**`server.handle_request()`** — hanterar exakt ett request och stänger sedan. Elegant — ingen server som ligger och kör.

### JWT-dekodning

```python
def decode_jwt_payload(token):
    payload_b64 = token.split(".")[1]     # JWT = header.payload.signature
    # Add padding, base64 decode, parse JSON
```

En JWT (JSON Web Token) består av tre delar separerade av punkter. Payload-delen (mitten) innehåller data som `tenantId`. Scriptet dekoderar den utan verifiering — vi behöver bara läsa TenantId, inte verifiera tokenens äkthet.

### Varför behövs detta bara en gång?

Efter att du kört scriptet har du `FORTNOX_TENANT_ID` i `.env`. Med Client Credentials flow (som `fortnox_client.py` använder) kan servern sedan hämta nya access tokens för alltid — utan webbläsare, utan användarinteraktion. TenantId ändras aldrig för ett givet bolag.

---

## 4. requirements.txt

```
fastmcp       # MCP-ramverket — hanterar protokollet
httpx          # Async HTTP-klient — pratar med Fortnox API
python-dotenv  # Läser .env-filer — credentials
```

Tre beroenden, alla med tydligt syfte. Minimalt — bra praxis.

---

## 5. .env (din, gitignore:ad)

```
FORTNOX_CLIENT_ID=ditt_id
FORTNOX_CLIENT_SECRET=din_secret
FORTNOX_TENANT_ID=ditt_tenant_id
```

Separerar credentials från kod. Tre värden:
- **CLIENT_ID** + **CLIENT_SECRET** — identifierar din integration (från Developer Portal)
- **TENANT_ID** — identifierar vilket Fortnox-bolag du vill komma åt

---

## Sammanfattning — Hur filerna samverkar

```
Claude Code
    │
    │ startar vid uppstart (läser .mcp.json)
    ▼
fortnox_server.py
    │
    │ skapar vid behov (lazy)
    ▼
fortnox_client.py
    │
    │ autentiserar (Client Credentials) och anropar
    ▼
Fortnox API (api.fortnox.se/3)
```

```
auth_setup.py ─── körs separat, en gång ──→ sparar TenantId till .env
```

---

## Designmönster att lägga märke till

| Mönster | Var | Varför |
|---|---|---|
| **Lazy initialization** | `_get_client()`, `_ensure_token()` | Skapa inget förrän det behövs |
| **Singleton** | `_client` global variabel | En klient, delad token |
| **Exponential backoff** | `_request()` retry-loop | Snällt mot API:t vid rate limits |
| **Separation of concerns** | Client vs Server | Klienten vet inget om MCP, servern vet inget om HTTP |
| **Convention over configuration** | FastMCP decorator | Funktionsnamn = toolnamn, type hints = schema |
