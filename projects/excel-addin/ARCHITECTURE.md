# Bokföring → Excel — Arkitektur och testguide

> Senast uppdaterad: 2026-03-14

## Innehåll

1. [Översikt](#översikt)
2. [Mappstruktur](#mappstruktur)
3. [Hur allt hänger ihop](#hur-allt-hänger-ihop)
4. [OAuth-flödet steg för steg](#oauth-flödet-steg-för-steg)
5. [DEV_MODE — lokal utveckling utan OAuth](#dev_mode--lokal-utveckling-utan-oauth)
6. [Provider-abstraktion — stöd för flera bokföringssystem](#provider-abstraktion--stöd-för-flera-bokföringssystem)
7. [Token-kryptering och refresh](#token-kryptering-och-refresh)
8. [Databasschema](#databasschema)
9. [Vad frontend gör](#vad-frontend-gör)
10. [Livscykel: från knapptryck till Excel-ark](#livscykel-från-knapptryck-till-excel-ark)
11. [Praktisk testguide](#praktisk-testguide)
12. [Miljövariabler](#miljövariabler)
13. [Att lägga till ett nytt bokföringssystem](#att-lägga-till-ett-nytt-bokföringssystem)
14. [Commit-historik (senaste arbetet)](#commit-historik)

---

## Översikt

Excel-addin:en låter en användare i Excel hämta bokföringsdata (resultaträkning,
balansräkning, huvudbok, fakturor) direkt från sitt bokföringssystem. I dagsläget
stöds Fortnox, men arkitekturen är byggd för att enkelt lägga till fler (Visma,
Björn Lundén, etc.).

```
┌──────────────────┐     HTTPS      ┌──────────────────┐     HTTPS      ┌─────────┐
│  Excel Taskpane  │ ─────────────→ │  FastAPI Backend  │ ─────────────→ │ Fortnox │
│  (React + TS)    │ ← JSON ─────── │  (Python 3.12)   │ ← JSON/SIE ── │   API   │
└──────────────────┘                └──────────────────┘                └─────────┘
                                           │
                                    ┌──────┴──────┐
                                    │ PostgreSQL  │
                                    │ (tenants,   │
                                    │  tokens,    │
                                    │  sessions)  │
                                    └─────────────┘
```

**Nyckelprinciper:**

- OAuth-tokens lagras aldrig i frontend — bara krypterat i databasen
- Frontend får en JWT-sessionstoken (24h) och skickar med den på varje request
- `DEV_MODE=true` (default) kopplar förbi all OAuth — du använder Fortnox
  Client Credentials direkt från `.env`
- Provider-abstraktionen gör att endpoints inte vet om det är Fortnox eller Visma

---

## Mappstruktur

```
excel-addin/
├── backend/
│   ├── main.py                 # FastAPI-app, startup, CORS, dev_mode override
│   ├── auth.py                 # JWT-skapande, get_current_provider dependency
│   ├── config.py               # Pydantic Settings (alla env-variabler)
│   ├── crypto.py               # AES-256-GCM kryptering/dekryptering
│   ├── db.py                   # SQLAlchemy async engine + session
│   ├── models.py               # ORM: Tenant, OAuthToken, UserSession
│   ├── providers/
│   │   ├── base.py             # AccountingProvider (abstrakt klass)
│   │   └── fortnox.py          # FortnoxProvider (wrappar FortnoxClient)
│   ├── routers/
│   │   ├── auth.py             # /api/auth/* (config, callback, logout)
│   │   ├── reports.py          # /api/rr, /api/br, jämförande rapporter
│   │   ├── invoices.py         # /api/lrk, /api/krk
│   │   ├── huvudbok.py         # /api/huvudbok
│   │   └── meta.py             # /api/financial-years
│   ├── services/
│   │   ├── sie_report_service.py  # Parsning av SIE-data till rapporter
│   │   ├── invoice_service.py     # Fakturahantering
│   │   └── sie_cache.py           # Cache per tenant + SIE-typ
│   ├── migrations/
│   │   └── versions/
│   │       └── b289bc45b1c1_initial_auth_schema.py
│   ├── alembic.ini
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── auth/
│   │   │   ├── AuthContext.tsx    # React context: token, login(), logout()
│   │   │   ├── dialog.ts         # Hämtar OAuth-config, redirectar till Fortnox
│   │   │   ├── dialog.html
│   │   │   ├── callback.ts       # Tar emot code, skickar till taskpane
│   │   │   └── callback.html
│   │   ├── taskpane/
│   │   │   └── components/
│   │   │       ├── App.tsx           # Root: AuthProvider → Login eller Export
│   │   │       ├── LoginScreen.tsx   # "Logga in med Fortnox"-knapp
│   │   │       ├── ExportPanel.tsx   # Rapportval, filter, export till ark
│   │   │       ├── ExcelWriter.ts    # Skriver headers + rader till Excel
│   │   │       └── dataTypeConfig.ts # Kolumndefinitioner per rapporttyp
│   │   └── utils/
│   │       └── api.ts            # fetch-wrapper med JWT, alla API-funktioner
│   ├── webpack.config.js         # Entry points: taskpane, dialog, callback
│   ├── manifest.prod.xml         # Office manifest (produktion)
│   └── vercel.json               # Hosting-config för frontend
│
├── docker-compose.yml            # Backend + PostgreSQL
└── ARCHITECTURE.md               # ← denna fil
```

---

## Hur allt hänger ihop

### Två driftlägen

| | DEV_MODE (lokalt) | Produktion |
|---|---|---|
| **OAuth** | Kopplas förbi helt | Fullständigt OAuth-flöde |
| **Fortnox-auth** | Client Credentials från `.env` | Authorization Code via dialog |
| **Databas** | Behövs inte | PostgreSQL med Alembic-migrering |
| **JWT** | Behövs inte (dependency override) | Skapas vid OAuth callback |
| **Frontend** | `npm run dev` → localhost:3000 | Vercel / annan hosting |
| **Backend** | `uvicorn main:app --reload` | Docker / fly.io / etc. |

### Request-flöde i DEV_MODE

```
ExportPanel → api.ts → GET /api/rr?...
                            ↓
                    main.py: dependency override
                    returnerar global FortnoxProvider
                            ↓
                    FortnoxProvider → FortnoxClient
                    → Fortnox API (Client Credentials)
                            ↓
                    SIE-parsning → JSON-svar
                            ↓
ExportPanel ← { headers, rows, period }
    ↓
ExcelWriter → Excel.run() → data i arket
```

### Request-flöde i produktion

```
ExportPanel → api.ts → GET /api/rr?...
              headers: Authorization: Bearer <JWT>
                            ↓
                    auth.py: get_current_provider
                    1. Validera JWT-signatur
                    2. Kolla session ej revoked i DB
                    3. Ladda tenant + krypterade tokens
                    4. Dekryptera tokens
                    5. Skapa FortnoxProvider med callback
                            ↓
                    FortnoxProvider → FortnoxClient
                    → Fortnox API (Authorization Code tokens)
                            ↓
                    (om token expired: refresh → callback → spara nya i DB)
                            ↓
                    SIE-parsning → JSON-svar
                            ↓
ExportPanel ← { headers, rows, period }
    ↓
ExcelWriter → Excel.run() → data i arket
```

---

## OAuth-flödet steg för steg

Det här händer när en användare klickar "Logga in med Fortnox" i produktion:

### 1. LoginScreen → AuthContext.login()

`LoginScreen.tsx` anropar `login()` från `useAuth()`.

### 2. Office Dialog öppnas

`AuthContext.tsx` öppnar ett separat fönster via Offices Dialog API:

```
Office.context.ui.displayDialogAsync("dialog.html", ...)
```

Varför en dialog? Taskpane:n körs i en iframe med sandboxade cookies och
partitionerad localStorage (Chromium 115+). OAuth-redirect fungerar inte i en
iframe, så vi måste öppna ett eget fönster.

### 3. Dialog hämtar OAuth-config

`dialog.ts` kallar `GET /api/auth/config/fortnox` som returnerar:
- `auth_url` — Fortnox OAuth-endpoint
- `client_id` — appens klient-ID
- `scopes` — vilka behörigheter som begärs

### 4. Redirect till Fortnox

Dialogen redirectar till Fortnox consent-sida. Användaren godkänner och
Fortnox redirectar tillbaka till `callback.html?code=ABC123&state=fortnox`.

### 5. Callback skickar code till taskpane

`callback.ts` extraherar `code` och `state` från URL:en och skickar till
taskpane:n via `Office.context.ui.messageParent()`.

Viktigt: vi använder inte `localStorage` (partitionerat i iframes).
Kommunikation sker enbart via `messageParent`.

### 6. AuthContext byter code mot JWT

Taskpane:n tar emot meddelandet och POSTar till `POST /api/auth/callback`:

```json
{
  "code": "ABC123",
  "state": "fortnox",
  "redirect_uri": "https://your-domain/callback.html"
}
```

### 7. Backend-callback

`routers/auth.py` gör följande:

1. **Token exchange** — POSTar authorization code till Fortnox token-endpoint,
   får tillbaka `access_token`, `refresh_token`, `expires_in` och `tenant_id`
2. **Hitta/skapa tenant** — söker i `tenants`-tabellen på `(provider_type, external_tenant_id)`,
   skapar ny rad om företaget inte setts förut
3. **Kryptera och spara tokens** — AES-256-GCM, sparar i `oauth_tokens`
4. **Skapa session** — ny rad i `user_sessions`, skapar JWT med `sub=tenant_id`
   och `jti=session_id`
5. **Returnerar JWT** — frontend lagrar den i React state (inte localStorage!)

### 8. Frontend är inloggad

`AuthContext` uppdaterar `isAuthenticated = true`. `App.tsx` visar `ExportPanel`
istället för `LoginScreen`. JWT:n synkas till `api.ts` via `setAuthToken()`.

---

## DEV_MODE — lokal utveckling utan OAuth

Med `DEV_MODE=true` (default i `.env`) händer detta vid startup i `main.py`:

```python
app.dependency_overrides[get_current_provider] = _dev_provider_override
```

FastAPIs dependency injection-system ersätter `get_current_provider` (som normalt
validerar JWT, laddar tenant, dekrypterar tokens) med en funktion som bara
returnerar den globala providern som skapades vid startup.

Det betyder att:
- **Ingen databas behövs** — inga JWT-kontroller, ingen token-lagring
- **Ingen OAuth** — providern använder Client Credentials från `.env`
- **Alla endpoints fungerar direkt** med bara `FORTNOX_CLIENT_ID`,
  `FORTNOX_CLIENT_SECRET` och `FORTNOX_TENANT_ID`

Frontend-inloggningsskärmen visas fortfarande, men du kan testa endpoints direkt
med t.ex. curl utan JWT.

---

## Provider-abstraktion — stöd för flera bokföringssystem

### Problemet

Endpoints som `/api/rr` eller `/api/huvudbok` ska inte behöva veta vilken
leverantör (Fortnox, Visma, etc.) som används. Koden ska vara identisk
oavsett.

### Lösningen

`AccountingProvider` (abstrakt klass i `providers/base.py`) definierar
interfacet:

| Metod | Beskrivning |
|---|---|
| `provider_type` | `"fortnox"`, `"visma"`, etc. |
| `tenant_id` | Företagets ID hos leverantören |
| `get_invoices(endpoint, params)` | Hämta fakturor (alla sidor) |
| `get_sie_export(sie_type, fy_id)` | Hämta SIE-fil (typ 2 eller 4) |
| `get_financial_years()` | Lista räkenskapsår |
| `close()` | Stäng HTTP-sessioner |

`FortnoxProvider` wrappar `FortnoxClient` (från `fortnox-mcp/`) och
`FortnoxSIEClient` (från `sie-pipeline/`).

Endpoints tar emot providern via dependency injection:

```python
@router.get("/rr")
async def get_rr(
    ...,
    provider: AccountingProvider = Depends(get_current_provider),
):
    sie_content = await provider.get_sie_export(sie_type=2, ...)
```

---

## Token-kryptering och refresh

### Kryptering (AES-256-GCM)

Fortnox access- och refresh-tokens krypteras med AES-256-GCM innan de sparas
i databasen. Nyckeln läses från `TOKEN_ENCRYPTION_KEY` (base64-kodad, 32 bytes).

```
Plaintext → AES-256-GCM(nonce + ciphertext) → base64 → TEXT-kolumn i DB
```

Dekryptering: base64-avkoda → separera nonce (12 bytes) → dekryptera.

### Token refresh med callback

Fortnox roterar refresh tokens vid varje användning (45 dagars rullande utgång).
Det betyder att efter varje refresh måste de nya tokens sparas, annars blir
de gamla ogiltiga.

Flödet:

1. `auth.py` skapar en `FortnoxProvider` med en `on_token_refresh`-callback
2. `FortnoxClient` upptäcker att access token är expired
3. `FortnoxClient` refreshar med `asyncio.Lock` (serialiserar refresh)
4. `FortnoxClient` anropar `on_token_refresh(new_access, new_refresh, expires_in)`
5. Callbacken krypterar nya tokens och uppdaterar `oauth_tokens`-tabellen
6. Nästa request använder de nya tokens

---

## Databasschema

Tre tabeller, skapade av Alembic-migrering `b289bc45b1c1`:

### tenants
| Kolumn | Typ | Beskrivning |
|---|---|---|
| `id` | UUID (PK) | Intern identifierare |
| `provider_type` | VARCHAR(50) | `"fortnox"`, `"visma"`, etc. |
| `external_tenant_id` | VARCHAR(255) | Företags-ID hos leverantören |
| `company_name` | VARCHAR(255) | Fritext, nullable |
| `created_at` | TIMESTAMPTZ | Auto |

Unikt index på `(provider_type, external_tenant_id)`.

### oauth_tokens
| Kolumn | Typ | Beskrivning |
|---|---|---|
| `id` | UUID (PK) | |
| `tenant_id` | UUID (FK → tenants) | |
| `access_token_encrypted` | TEXT | AES-256-GCM krypterad |
| `refresh_token_encrypted` | TEXT | AES-256-GCM krypterad |
| `token_expires_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | Auto-uppdateras |

### user_sessions
| Kolumn | Typ | Beskrivning |
|---|---|---|
| `id` | UUID (PK) | |
| `tenant_id` | UUID (FK → tenants) | |
| `jwt_id` | VARCHAR(255) | Matchar JWT:ns `jti`-claim |
| `created_at` | TIMESTAMPTZ | |
| `expires_at` | TIMESTAMPTZ | |
| `revoked` | BOOLEAN | `true` efter logout |

Unikt index på `jwt_id`.

---

## Vad frontend gör

### Komponent-hierarki

```
App.tsx
├── AuthProvider (React Context)
│   └── AppContent
│       ├── LoginScreen     (om !isAuthenticated)
│       └── ExportPanel     (om isAuthenticated)
│           └── ExcelWriter  (hjälpfunktion, inte en komponent)
```

### ExportPanel — vad kan användaren göra?

1. **Välj rapporttyp**: Resultaträkning, Balansräkning, RR Flat, BR Flat,
   Leverantörsreskontra, Kundreskontra, Huvudbok
2. **Välj räkenskapsår** (hämtas automatiskt från `/api/financial-years`)
3. **Välj period** (från/till)
4. **Välj kolumner** (konfigurerbart per rapporttyp)
5. **Välj destination**: nytt ark eller ersätt befintligt
6. **Klicka "Exportera till Excel"** → data skrivs till arket

### 401-hantering

Om backend returnerar 401 (expired/revoked session):
- `api.ts` kastar `AuthError`
- `ExportPanel` fångar `AuthError` och anropar `logout()`
- `AuthContext` nollställer state → `App.tsx` visar `LoginScreen`

---

## Livscykel: från knapptryck till Excel-ark

Hela flödet för en export:

```
1. Användaren klickar "Exportera" i ExportPanel
2. ExportPanel anropar t.ex. getRR({ financial_year_id, from_period, to_period })
3. api.ts bygger URL: /api/rr?financial_year_id=5&from_period=2025-01&to_period=2025-12
4. api.ts lägger till header: Authorization: Bearer <JWT>
5. Backend tar emot requesten
6. FastAPI resolver get_current_provider:
   a. Extrahr JWT från header
   b. Verifiera signatur (HS256)
   c. Slå upp session i DB, kolla att revoked=false
   d. Ladda tenant + krypterade tokens
   e. Dekryptera tokens
   f. Skapa FortnoxProvider med tokens + refresh-callback
7. Router-funktionen anropar provider.get_sie_export(sie_type=2, financial_year_id=5)
8. FortnoxProvider → FortnoxClient → HTTPS till Fortnox API
9. (Om token expired: refresh → callback sparar nya tokens → retry)
10. SIE-data returneras som text
11. sie_report_service.py parsar SIE-filen
12. Aggregera per konto, period, dimension → { headers, rows, period }
13. JSON-svar tillbaka till frontend
14. ExportPanel tar emot data
15. ExcelWriter.ts anropar Excel.run():
    a. Skapa/hitta ark med rätt namn
    b. Skriv headers i rad 1
    c. Skriv datarader
    d. Formatera beloppskolumner som tal
16. Visa bekräftelse: "47 rader skrivna till Resultaträkning 2025"
```

---

## Praktisk testguide

### Förutsättningar

- Node.js 18+ och npm
- Python 3.12+
- Fortnox Developer-konto med sandbox-företag
  (https://developer.fortnox.se → skapa app → aktivera sandbox)

### Test 1: Lokal utveckling med DEV_MODE (enklast)

**Det här testar**: att backend + frontend fungerar, data hämtas från Fortnox,
och data skrivs korrekt till Excel.

```bash
# 1. Backend
cd projects/excel-addin/backend
cp .env.example .env
# Fyll i FORTNOX_CLIENT_ID, FORTNOX_CLIENT_SECRET, FORTNOX_TENANT_ID
# Behåll DEV_MODE=true (default)

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 2. Testa API direkt (inget JWT behövs i dev mode)
curl http://localhost:8000/health
curl http://localhost:8000/api/financial-years

# 3. Frontend
cd ../frontend
npm install
npm run dev    # Startar webpack-dev-server på https://localhost:3000

# 4. Sideloada i Excel
# I Excel: Insert → My Add-ins → Upload My Add-in → manifest.xml (dev-version)
# Taskpane öppnas → LoginScreen visas
# (I dev mode ignoreras login-flödet av backend, men det visas ändå)
```

**Vad du bör kontrollera:**
- [ ] `/health` svarar `{"status": "ok"}`
- [ ] `/api/financial-years` returnerar en lista med räkenskapsår
- [ ] Frontend visar LoginScreen korrekt
- [ ] Export till Excel fungerar (välj rapporttyp, period, klicka Exportera)
- [ ] Data hamnar i rätt ark med korrekta kolumner

### Test 2: Backend API manuellt med curl

```bash
# Räkenskapsår
curl -s http://localhost:8000/api/financial-years | python3 -m json.tool

# Resultaträkning (byt financial_year_id till ett giltigt ID)
curl -s "http://localhost:8000/api/rr?financial_year_id=5&from_period=2025-01&to_period=2025-12" \
  | python3 -m json.tool

# Balansräkning
curl -s "http://localhost:8000/api/br?financial_year_id=5&period=2025-12" \
  | python3 -m json.tool

# Leverantörsreskontra
curl -s "http://localhost:8000/api/lrk?from_date=2025-01-01&to_date=2025-12-31" \
  | python3 -m json.tool

# Huvudbok
curl -s "http://localhost:8000/api/huvudbok?financial_year_id=5&from_account=1000&to_account=9999&from_period=2025-01&to_period=2025-12" \
  | python3 -m json.tool
```

### Test 3: Docker-bygge (utan databas)

```bash
cd projects/excel-addin

# Bygg bara backend-imagen (behöver inte PostgreSQL)
docker compose build backend

# Om det lyckas → Dockerfile och build context funkar
```

### Test 4: Fullständig produktion med PostgreSQL

**Det här testar**: OAuth-flödet, JWT-sessioner, token-kryptering, databasschema.

```bash
# 1. Starta PostgreSQL
cd projects/excel-addin
docker compose up db -d

# 2. Konfigurera backend för produktion
cd backend
cp .env.example .env
# Ändra:
#   DEV_MODE=false
#   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/excel_addin
#   JWT_SECRET=<generera: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
#   TOKEN_ENCRYPTION_KEY=<generera: python3 -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())">
#   FORTNOX_CLIENT_ID=<din app>
#   FORTNOX_CLIENT_SECRET=<din secret>

# 3. Kör Alembic-migrering
source .venv/bin/activate
alembic upgrade head

# 4. Starta backend
uvicorn main:app --reload --port 8000

# 5. Starta frontend
cd ../frontend
npm run dev

# 6. Sideloada i Excel och testa OAuth-inloggning
# Klicka "Logga in med Fortnox" → Fortnox consent-sida → godkänn
# → session skapas → ExportPanel visas med företagsnamn i headern
```

**Vad du bör kontrollera:**
- [ ] `alembic upgrade head` skapar tabellerna utan fel
- [ ] OAuth-dialogen öppnas och visar Fortnox inloggning
- [ ] Efter godkännande: ExportPanel visas med företagsnamn
- [ ] Dataexport fungerar (resultaträkning, etc.)
- [ ] Utloggning fungerar (knapp finns i framtida iteration)
- [ ] Om du stänger/öppnar Excel: sessionens JWT har expirat → LoginScreen visas

### Test 5: 401-hantering

```bash
# Starta med DEV_MODE=false och giltig databas

# 1. Logga in normalt via frontend
# 2. I en annan terminal, revoka sessionen direkt i DB:
docker exec -it excel-addin-db-1 psql -U postgres excel_addin \
  -c "UPDATE user_sessions SET revoked = true;"

# 3. Försök exportera data i Excel
# → Bör visa LoginScreen igen (AuthError → logout)
```

### Test 6: Verifiera kryptering

```bash
# Kör med DEV_MODE=false, en inloggad session

# Kolla att tokens är krypterade (inte klartext):
docker exec -it excel-addin-db-1 psql -U postgres excel_addin \
  -c "SELECT access_token_encrypted FROM oauth_tokens LIMIT 1;"

# Ska returnera en lång base64-sträng, inte en vanlig JWT/bearer token
```

### Frontend-bygge (verifiering)

```bash
cd projects/excel-addin/frontend
npm run build

# Kontrollera att dist/ skapas utan fel
# Varning om bundle-storlek (>244 KiB) är ok — det är Fluent UI
```

### Python-kompilering (verifiering)

```bash
cd projects/excel-addin/backend
source .venv/bin/activate

# Alla .py-filer ska kompilera utan fel:
find . -name "*.py" -not -path "./.venv/*" | while read f; do
  python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" && echo "OK: $f"
done
```

---

## Miljövariabler

Se `backend/.env.example` för fullständig referens. Sammanfattning:

| Variabel | Krävs i dev | Krävs i prod | Beskrivning |
|---|---|---|---|
| `DEV_MODE` | ✅ (`true`) | ✅ (`false`) | Koppla förbi OAuth |
| `FORTNOX_CLIENT_ID` | ✅ | ✅ | Från developer.fortnox.se |
| `FORTNOX_CLIENT_SECRET` | ✅ | ✅ | Från developer.fortnox.se |
| `FORTNOX_TENANT_ID` | ✅ | — | Sandbox företags-ID (bara dev) |
| `DATABASE_URL` | — | ✅ | PostgreSQL connection string |
| `JWT_SECRET` | — | ✅ | Slumpmässig sträng (minst 32 tecken) |
| `TOKEN_ENCRYPTION_KEY` | — | ✅ | Base64-kodad 32-byte AES-nyckel |
| `ALLOWED_ORIGINS` | — | ✅ | Kommaseparerade CORS-origins |

---

## Att lägga till ett nytt bokföringssystem

Exempel: lägga till Visma eEkonomi.

### 1. Skapa provider

```python
# backend/providers/visma.py
class VismaProvider(AccountingProvider):
    provider_type = "visma"
    # Implementera get_invoices, get_sie_export, etc.
```

### 2. Lägg till OAuth-config

```python
# backend/routers/auth.py
PROVIDER_CONFIGS["visma"] = {
    "auth_url": "https://connect.visma.com/oauth/authorize",
    "token_url": "https://connect.visma.com/oauth/token",
    "client_id": lambda: _settings.visma_client_id,
    "client_secret": lambda: _settings.visma_client_secret,
    "scopes": "accounting:read",
}
```

### 3. Uppdatera factory

```python
# backend/auth.py → _create_provider()
elif tenant.provider_type == "visma":
    return VismaProvider(...)
```

### 4. Uppdatera frontend (valfritt)

Lägg till "Logga in med Visma"-knapp i `LoginScreen.tsx` och parameterisera
`dialog.ts` att skicka `providerType` via URL-hash.

---

## Commit-historik

Senaste 7 commits (produktionsklarhet):

| Hash | Meddelande |
|---|---|
| `277c2d1` | chore: generate real UUID for manifest and add deployment comments |
| `242e033` | security: restrict CORS to only used methods and headers |
| `2fde78a` | fix: handle 401 responses by logging out to login screen |
| `cfe00ad` | feat: add initial Alembic migration for auth schema |
| `41786a9` | docs: add .env.example documenting all environment variables |
| `ef08161` | fix: Dockerfile build context + add docker-compose for local dev |
| `18629b8` | feat: add OAuth multi-tenant auth, provider abstraction, and login UI |

Dessförinnan:

| Hash | Meddelande |
|---|---|
| `0a32344` | refactor: code quality improvements across Excel add-in |
| `8ef6bf0` | improve: ExportPanel UX with loading states, validation, presets |
| `d59a5d8` | feat: unified ExportPanel with flat RR/BR, column selection |
