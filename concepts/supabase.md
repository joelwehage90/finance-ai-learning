# Supabase

## Vad det är

Supabase är en open-source Firebase-alternativ byggd ovanpå **PostgreSQL**. Den ger dig en databas + auto-genererat REST API + autentisering + fillagring + Edge Functions + realtime — allt färdigt att använda. Du får en fullständig backend utan att bygga en.

## Varför det är viktigt

Supabase är vår **centrala dataplattform**. All bokföringsdata från Fortnox synkas hit. Både Claude Code (via Supabase MCP) och kund-appen (via REST API/Python-klient) frågar samma databas. En källa, alla kanaler.

## Ekonomiexempel

Fortnox → nattsynk → Supabase med alla verifikationer, saldon, konton. En controller frågar Claude Code: "Varför ökade personalkostnaderna i mars?" Claude kör SQL mot Supabase, drillar ned till verifikationsnivå, och svarar — utan ett enda anrop till Fortnox.

---

## 1. Supabase MCP Server

### Vad det är

Officiell MCP-server från Supabase som låter Claude Code/Desktop prata direkt med din Supabase-databas. Du kan köra SQL, hantera tabeller, deploya Edge Functions — allt via chat.

**Repo:** [github.com/supabase-community/supabase-mcp](https://github.com/supabase-community/supabase-mcp)
**npm:** `@supabase/mcp-server-supabase`

### Konfiguration

**Hosted (enklast — rekommenderas):**

Lägg till i `.mcp.json`:
```json
{
  "mcpServers": {
    "supabase": {
      "type": "url",
      "url": "https://mcp.supabase.com/mcp?read_only=true"
    }
  }
}
```

Vid första start autentiserar du via OAuth i webbläsaren. Inga API-nycklar att hantera.

**Med projektbegränsning (säkrare):**
```
https://mcp.supabase.com/mcp?project_ref=din-projekt-ref&read_only=true
```

**Lokalt (mot lokal Supabase CLI):**
```
http://localhost:54321/mcp
```

### Alla verktyg

| Kategori | Verktyg | Beskrivning |
|----------|---------|-------------|
| **Databas** | `execute_sql` | Kör godtycklig SQL |
| | `list_tables` | Lista alla tabeller |
| | `list_extensions` | Lista PostgreSQL-extensions |
| | `apply_migration` | Kör SQL-migration (spårad) |
| | `list_migrations` | Lista befintliga migrationer |
| **Projekt** | `list_projects` | Lista alla projekt |
| | `get_project` | Projektdetaljer |
| | `create_project` | Skapa nytt projekt |
| | `pause_project` / `restore_project` | Pausa/återställ |
| | `list_organizations` | Lista organisationer |
| **Edge Functions** | `list_edge_functions` | Lista funktioner |
| | `get_edge_function` | Läs funktionskod |
| | `deploy_edge_function` | Deploya funktion |
| **Debug** | `get_logs` | Loggar (API, Postgres, Edge, Auth) |
| | `get_advisors` | Säkerhets-/prestandarekommendationer |
| **Övrigt** | `search_docs` | Sök i Supabase-dokumentation |
| | `generate_typescript_types` | Generera TypeScript-typer |
| | `get_project_url` | API-URL |
| | `get_publishable_keys` | Publika API-nycklar |
| **Storage** | `list_storage_buckets` | Lista lagringsbuckets |
| | `get_storage_config` | Lagringskonfiguration |

### Säkerhet

- **`read_only=true`** — kör SQL som read-only Postgres-användare. Blockerar `apply_migration`, `create_project`, `deploy_edge_function` etc. **Rekommenderas som default.**
- **`project_ref=...`** — begränsar till ett projekt
- **`features=database,docs`** — aktivera/avaktivera verktygsgrupper
- **Prompt injection-skydd** — SQL-resultat wrappas med instruktioner som avråder LLM:en från att följa eventuella instruktioner i datan

### Vad det betyder för oss

Claude Code kan fråga Supabase direkt:
```
Du: "Vilka konton hade störst ökning i mars jämfört med februari?"
Claude → execute_sql → SQL-query mot period_balances → svar
```

Ingen MCP-server att bygga — Supabase MCP ger oss `execute_sql` som kan göra allt.

---

## 2. REST API (PostgREST)

### Vad det är

Supabase genererar automatiskt ett REST API från ditt databasschema via **PostgREST**. Varje tabell blir en endpoint. Inga routes att skriva.

```
Tabell "vouchers" → GET https://din-ref.supabase.co/rest/v1/vouchers
```

### Filtrering och queries

PostgREST stödjer avancerad filtrering via query-parametrar:

| Operator | Betydelse | Exempel |
|----------|-----------|---------|
| `eq` | Lika med | `?account=eq.5010` |
| `gt`, `lt` | Större/mindre | `?amount=gt.10000` |
| `gte`, `lte` | Större/mindre eller lika | `?date=gte.2026-01-01` |
| `like`, `ilike` | Mönster (case-sensitive/insensitive) | `?description=ilike.*hyra*` |
| `in` | I en lista | `?status=in.(active,pending)` |
| `is` | Null-check | `?deleted_at=is.null` |
| `order` | Sortering | `?order=date.desc` |
| `limit`, `offset` | Pagination | `?limit=25&offset=0` |
| `select` | Välj kolumner + joins | `?select=*,account:accounts(name)` |

### RPC (Remote Procedure Calls)

Du kan skapa PostgreSQL-funktioner och anropa dem via REST:

```sql
-- I Supabase SQL Editor:
CREATE FUNCTION get_monthly_pnl(p_year int, p_month int)
RETURNS TABLE(account_number int, account_name text, amount numeric)
AS $$
  SELECT account_number, account_name, SUM(amount)
  FROM transactions
  WHERE EXTRACT(YEAR FROM date) = p_year
    AND EXTRACT(MONTH FROM date) = p_month
  GROUP BY account_number, account_name
$$ LANGUAGE sql;
```

```
POST /rest/v1/rpc/get_monthly_pnl
{"p_year": 2026, "p_month": 3}
```

**Varför RPC?** Komplexa rapportberäkningar (RR, BR, funktionsindelad RR) bör vara databasfunktioner — snabbare, indexerade, och kan återanvändas från alla kanaler.

---

## 3. Python-klient (supabase-py)

### Installation

```bash
pip install supabase
```

Kräver Python ≥ 3.8. Senaste version: 2.28.0 (feb 2026).

### Användning

```python
from supabase import create_client

supabase = create_client(
    "https://din-ref.supabase.co",
    "din-service-role-key"     # Eller anon-key
)

# SELECT med filter
result = supabase.table("vouchers") \
    .select("*, voucher_rows(*)") \
    .eq("financial_year", 2026) \
    .gte("date", "2026-03-01") \
    .order("date", desc=True) \
    .limit(25) \
    .execute()

# INSERT
supabase.table("period_balances").insert({
    "tenant_id": "abc",
    "account_number": 5010,
    "period": "2026-03",
    "amount": 45000.00
}).execute()

# UPSERT (insert or update on conflict)
supabase.table("period_balances").upsert({
    "tenant_id": "abc",
    "account_number": 5010,
    "period": "2026-03",
    "amount": 45000.00
}).execute()

# RPC (call database function)
result = supabase.rpc("get_monthly_pnl", {
    "p_year": 2026,
    "p_month": 3
}).execute()
```

### Service Role Key vs Anon Key

| Nyckel | Användning | RLS |
|--------|------------|-----|
| **anon key** | Klient-sida (browser) | ✅ Begränsad av Row Level Security |
| **service role key** | Server-sida (FastAPI backend) | ❌ Kringgår RLS — full åtkomst |

**Vår backend använder service role key** — den behöver full åtkomst för synk och rapporter.

---

## 4. Edge Functions + Schemalagda jobb

### Vad Edge Functions är

Serverless funktioner som körs i **Deno** (TypeScript runtime) på Supabase infrastruktur. Perfekt för:
- Schemalagd Fortnox-synk
- Webhook-mottagare
- API-endpoints som behöver serverlogik

### Schemalägga med pg_cron

Supabase har `pg_cron` inbyggt. Du skapar ett cron-jobb i SQL som anropar din Edge Function via HTTP:

**Steg 1: Spara credentials i Vault**
```sql
SELECT vault.create_secret('https://din-ref.supabase.co', 'project_url');
SELECT vault.create_secret('DIN_ANON_KEY', 'anon_key');
```

**Steg 2: Schemalägg nattlig synk (kl 02:00)**
```sql
SELECT cron.schedule(
  'nightly-fortnox-sync',
  '0 2 * * *',     -- Varje natt kl 02:00
  $$
  SELECT net.http_post(
    url := (SELECT decrypted_secret FROM vault.decrypted_secrets
            WHERE name = 'project_url') || '/functions/v1/fortnox-sync',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (SELECT decrypted_secret
                                     FROM vault.decrypted_secrets
                                     WHERE name = 'anon_key')
    ),
    body := '{"full_sync": false}'::jsonb
  ) AS request_id;
  $$
);
```

**Steg 3: Edge Function som kör synken**
```typescript
// supabase/functions/fortnox-sync/index.ts
import { serve } from "https://deno.land/std/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js"

serve(async (req) => {
  const { full_sync } = await req.json()

  // 1. Hämta SIE4 från Fortnox
  // 2. Parsa
  // 3. Upsert i Supabase

  return new Response(JSON.stringify({ status: "ok" }))
})
```

### Alternativ: Trigga synk manuellt

En MCP-tool eller API-endpoint som triggar synken on-demand:

```
Du i Claude Code: "Synka från Fortnox"
Claude → execute_sql → SELECT net.http_post(.../fortnox-sync, '{"full_sync": true}')
```

Eller direkt via Supabase MCP:
```
Claude → deploy_edge_function (om den behöver uppdateras)
Claude → execute_sql (trigga via pg_net)
```

---

## 5. Databasdesign för bokföringsdata

### Tabellstruktur

```sql
-- Företag/tenants (multi-tenant)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    org_number TEXT,
    fortnox_client_id TEXT,
    fortnox_client_secret TEXT,
    fortnox_tenant_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Kontoplan
CREATE TABLE accounts (
    tenant_id UUID REFERENCES tenants(id),
    account_number INT NOT NULL,
    name TEXT NOT NULL,
    account_type CHAR(1),    -- T=Tillgång, S=Skuld, K=Kostnad, I=Intäkt
    active BOOLEAN DEFAULT true,
    sru_code INT,
    PRIMARY KEY (tenant_id, account_number)
);

-- Räkenskapsår
CREATE TABLE financial_years (
    tenant_id UUID REFERENCES tenants(id),
    year_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    PRIMARY KEY (tenant_id, year_id)
);

-- Dimensioner (kostnadsställen, projekt)
CREATE TABLE dimensions (
    tenant_id UUID REFERENCES tenants(id),
    dimension_id INT NOT NULL,    -- 1 = kostnadsställe, 6 = projekt
    object_id TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, dimension_id, object_id)
);

-- Verifikationer (header)
CREATE TABLE vouchers (
    tenant_id UUID REFERENCES tenants(id),
    series TEXT NOT NULL,
    number INT NOT NULL,
    year_id INT NOT NULL,
    date DATE NOT NULL,
    description TEXT,
    reference_number TEXT,
    reference_type TEXT,
    synced_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (tenant_id, series, number, year_id)
);

-- Verifikationsrader (transaktioner)
CREATE TABLE transactions (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    voucher_series TEXT NOT NULL,
    voucher_number INT NOT NULL,
    year_id INT NOT NULL,
    account_number INT NOT NULL,
    amount NUMERIC(15,2) NOT NULL,    -- Positiv = debet, negativ = kredit
    cost_center TEXT,
    project TEXT,
    transaction_info TEXT,
    FOREIGN KEY (tenant_id, voucher_series, voucher_number, year_id)
        REFERENCES vouchers(tenant_id, series, number, year_id),
    FOREIGN KEY (tenant_id, account_number)
        REFERENCES accounts(tenant_id, account_number)
);

-- Periodsaldon (pre-aggregerat, snabba rapporter)
CREATE TABLE period_balances (
    tenant_id UUID NOT NULL,
    account_number INT NOT NULL,
    period TEXT NOT NULL,           -- "2026-03"
    cost_center TEXT DEFAULT '*',
    project TEXT DEFAULT '*',
    amount NUMERIC(15,2) NOT NULL,
    balance_type TEXT NOT NULL,     -- 'result' eller 'balance'
    synced_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (tenant_id, account_number, period, cost_center, project)
);

-- Synk-status
CREATE TABLE sync_state (
    tenant_id UUID REFERENCES tenants(id),
    entity_type TEXT NOT NULL,      -- 'sie4', 'invoices', etc.
    last_sync TIMESTAMPTZ,
    last_full_sync TIMESTAMPTZ,
    records_synced INT,
    status TEXT DEFAULT 'idle',     -- 'idle', 'running', 'error'
    error_message TEXT,
    PRIMARY KEY (tenant_id, entity_type)
);

-- Funktionsindelad RR-mappning
CREATE TABLE functional_pnl_mapping (
    tenant_id UUID REFERENCES tenants(id),
    account_range_from INT NOT NULL,
    account_range_to INT NOT NULL,
    cost_center TEXT DEFAULT '*',   -- '*' = alla
    function_id TEXT NOT NULL,      -- 'cogs', 'selling', 'admin', etc.
    function_label TEXT NOT NULL,   -- 'Kostnad sålda varor', etc.
    sort_order INT,
    PRIMARY KEY (tenant_id, account_range_from, account_range_to, cost_center)
);

-- Budget
CREATE TABLE budget (
    tenant_id UUID NOT NULL,
    account_number INT NOT NULL,
    period TEXT NOT NULL,           -- "2026-03"
    cost_center TEXT DEFAULT '*',
    amount NUMERIC(15,2) NOT NULL,
    PRIMARY KEY (tenant_id, account_number, period, cost_center)
);
```

### Index för vanliga queries

```sql
-- Drill-down: "visa transaktioner för konto 5010 i mars"
CREATE INDEX idx_transactions_account_period
ON transactions(tenant_id, account_number, year_id);

-- Verifikationslista per datum
CREATE INDEX idx_vouchers_date
ON vouchers(tenant_id, date);

-- Periodsaldon för rapporter
CREATE INDEX idx_period_balances_period
ON period_balances(tenant_id, period);
```

### Materialized Views för rapporter

```sql
-- Resultaträkning (pre-beräknad)
CREATE MATERIALIZED VIEW mv_income_statement AS
SELECT
    pb.tenant_id,
    pb.period,
    CASE
        WHEN pb.account_number BETWEEN 3000 AND 3799 THEN 'Nettoomsättning'
        WHEN pb.account_number BETWEEN 3800 AND 3999 THEN 'Övriga rörelseintäkter'
        WHEN pb.account_number BETWEEN 4000 AND 4999 THEN 'Råvaror och förnödenheter'
        WHEN pb.account_number BETWEEN 5000 AND 6999 THEN 'Övriga externa kostnader'
        WHEN pb.account_number BETWEEN 7000 AND 7699 THEN 'Personalkostnader'
        WHEN pb.account_number BETWEEN 7700 AND 7899 THEN 'Avskrivningar'
        WHEN pb.account_number BETWEEN 8000 AND 8999 THEN 'Finansiella poster'
    END AS line_item,
    SUM(pb.amount) AS amount
FROM period_balances pb
WHERE pb.balance_type = 'result'
GROUP BY pb.tenant_id, pb.period, line_item;

-- Refresha efter synk:
-- REFRESH MATERIALIZED VIEW mv_income_statement;
```

### Designprinciper

| Princip | Implementation |
|---------|---------------|
| **NUMERIC, aldrig FLOAT** | `NUMERIC(15,2)` för alla belopp — inga avrundningsfel |
| **Multi-tenant via tenant_id** | Alla tabeller har `tenant_id` — RLS kan filtrera per kund |
| **Dubbel lagring** | `transactions` (rå verifikationer) + `period_balances` (aggregerat) |
| **Upsert vid synk** | `ON CONFLICT DO UPDATE` — idempotent synk |
| **Immutable verifikationer** | Följer bokföringslagen — verifikationer ändras aldrig |

---

## 6. Arkitektur — Hur allt hänger ihop

```
                    ┌─────────────────────┐
                    │    Fortnox API       │
                    └──────────┬──────────┘
                               │
                    SIE4 export (nattsynk via Edge Function)
                               │
                               ▼
                    ┌─────────────────────┐
                    │     Supabase        │
                    │   ┌─────────────┐   │
                    │   │ PostgreSQL   │   │
                    │   │ - vouchers   │   │
                    │   │ - transactions│  │
                    │   │ - balances   │   │
                    │   │ - accounts   │   │
                    │   │ - budget     │   │
                    │   └─────────────┘   │
                    │   ┌─────────────┐   │
                    │   │ Edge Funcs   │   │
                    │   │ - sync       │   │
                    │   └─────────────┘   │
                    │   ┌─────────────┐   │
                    │   │ pg_cron      │   │
                    │   │ 02:00 natt   │   │
                    │   └─────────────┘   │
                    └──┬───────────────┬──┘
                       │               │
              Supabase MCP       REST API + Python
              (execute_sql)      (supabase-py)
                       │               │
                       ▼               ▼
                  Claude Code     FastAPI backend
                  (intern)        → React UI (kund-app)
```

---

## Vad jag fortfarande behöver förstå bättre

<!-- TODO: Testa Supabase MCP praktiskt — funkar execute_sql med komplexa joins? -->
<!-- TODO: Hur stor kan en SIE4-import vara utan att Edge Function timeout:ar? (default 60s) -->
<!-- TODO: Row Level Security — hur sätter vi upp det för multi-tenant? -->
<!-- TODO: Realtime subscriptions — kan kund-appen prenumerera på synk-status? -->
<!-- TODO: Kostnader — vad kostar Supabase vid 10-100 tenants med bokföringsdata? -->

## Relaterade koncept

- **MCP** — Supabase MCP ger Claude Code direkt databasåtkomst (se concepts/mcp.md)
- **Fortnox API** — datakällan som synkas till Supabase (se concepts/fortnox-api.md)
- **Tool Use** — FastAPI-backenden exponerar Supabase-data som tools för Anthropic API (se concepts/tool-use.md)
