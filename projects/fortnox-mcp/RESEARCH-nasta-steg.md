# Research: Nästa steg för Fortnox MCP

Detaljerad research kring tre features som bygger vidare på nuvarande MVP: **SIE-baserad resultaträkning/balansräkning**, **verifikationer (read)**, och **funktionsindelad resultaträkning med custom mapping**.

---

## 1. SIE-baserad resultaträkning och balansräkning

### 1.1 SIE4-formatet — Hur ser filerna ut?

SIE (Standard Import Export) är Sveriges de facto-standard för bokföringsdata. Skapad 1992 av SIE-Gruppen. Nästan 100% av svenska bokföringsprogram stödjer formatet.

**Filstruktur:** Platt textfil, varje rad börjar med en tagg (`#TAGG`). CP437-encoding (IBM PC 8-bit extended ASCII). Inga binära element.

**Exempel på SIE4-fil:**
```
#FLAGGA 0
#FORMAT PC8
#SIETYP 4
#PROGRAM "Fortnox" 1.0
#GEN 20260310
#FNAMN "Mitt Företag AB"
#ORGNR 5561234567
#RAR 0 20260101 20261231
#RAR -1 20250101 20251231
#KPTYP BAS2025

#KONTO 1930 "Företagskonto"
#KONTO 3010 "Försäljning tjänster"
#KONTO 4010 "Inköp material"
#KONTO 5010 "Lokalhyra"
#KONTO 7210 "Löner tjänstemän"

#IB 0 1930 340000.00
#UB 0 1930 425000.00
#RES 0 3010 -1250000.00
#RES 0 4010 450000.00
#RES 0 5010 180000.00

#VER A 1 20260115 "Kundfaktura 1001"
{
    #TRANS 1510 {} 50000.00
    #TRANS 3010 {} -50000.00
}

#VER B 1 20260120 "Hyra januari"
{
    #TRANS 5010 {} 15000.00
    #TRANS 1930 {} -15000.00
}
```

### 1.2 Viktiga taggar

| Tagg | Syfte | Exempel |
|------|-------|---------|
| `#FLAGGA` | Importstatus (0 = ej importerad) | `#FLAGGA 0` |
| `#SIETYP` | Filtyp 1-4 | `#SIETYP 4` |
| `#FNAMN` | Företagsnamn | `#FNAMN "Mitt AB"` |
| `#ORGNR` | Organisationsnummer | `#ORGNR 5561234567` |
| `#RAR` | Räkenskapsår (0=nuvarande, -1=förra) | `#RAR 0 20260101 20261231` |
| `#KONTO` | Kontodefinition | `#KONTO 1930 "Företagskonto"` |
| `#KTYP` | Kontotyp (T/S/K/I) | `#KTYP 1930 T` |
| `#DIM` | Dimensionsdefinition | `#DIM 1 "Kostnadsställe"` |
| `#OBJEKT` | Objekt inom dimension | `#OBJEKT 1 "SALJ" "Försäljning"` |
| `#IB` | Ingående balans | `#IB 0 1930 340000.00` |
| `#UB` | Utgående balans | `#UB 0 1930 425000.00` |
| `#OIB` | Ingående balans per objekt | `#OIB 0 1930 {1 "SALJ"} 170000.00` |
| `#OUB` | Utgående balans per objekt | `#OUB 0 1930 {1 "SALJ"} 210000.00` |
| `#RES` | Resultaträkningspost | `#RES 0 3010 -1250000.00` |
| `#PSALDO` | Periodsaldo | `#PSALDO 0 202601 3010 {} -105000.00` |
| `#PBUDGET` | Periodbudget | `#PBUDGET 0 202601 3010 {} -100000.00` |
| `#VER` | Verifikation (header) | `#VER A 1 20260115 "Text"` |
| `#TRANS` | Transaktionsrad (inom VER-block) | `#TRANS 5010 {} 15000.00` |

### 1.3 SIE-typer från Fortnox

**Endpoint:** `GET https://api.fortnox.se/3/sie/{Type}?financialyear={id}`

| Typ | Innehåll | Bäst för |
|-----|----------|----------|
| **1** | Årssaldon (IB/UB) | Snabb balansräkning (årsvis) |
| **2** | Periodsaldon (PSALDO) | Månatlig RR/BR utan transaktionsdetaljer |
| **3** | Objektsaldon (per kostnadsställe/projekt) | Funktionsindelad RR |
| **4** | Alla verifikationer + allt ovan | Fullständig analys, men stor fil |

**Rekommendation:**
- **Typ 2** för enkel resultaträkning/balansräkning per månad
- **Typ 3** för funktionsindelad RR (behöver kostnadsställe-data)
- **Typ 4** om Claude behöver analysera enskilda transaktioner

**Viktigt:** SIE-endpointen returnerar SIE-format (text), inte JSON. Servern måste parsa SIE-filen.

### 1.4 Python-bibliotek för SIE-parsning

**Landskapet är tunt.** Det finns inget välunderhållet PyPI-paket.

| Bibliotek | Källa | Stjärnor | Status | Notering |
|-----------|-------|----------|--------|----------|
| `magapp/parse-sie` | GitHub | 20 | Okänt senaste datum | Stödjer #VER, #TRANS, #KONTO, #IB, #UB, #RES. CSV/Google Sheets export. Hanterar cp850, latin-1, utf-8 |
| `magnusfroste/sie-parser` | GitHub | 1 | Jan 2025 | Flask-app. Konverterar SIE4 → JSON för LLM-analys. Stödjer Fortnox/Bokio/Dooer. CP437 |
| `jswetzen/sie-parse` | GitHub | Okänt | Okänt | Parser för .si och .sie filer |
| `pysie-accounting` | PyPI | Okänt | Okänt | Finns på PyPI men oklart underhåll |

**Rekommendation: Skriv egen parser.**

SIE4-formatet är enkelt nog att parsa själv (rad-baserat, taggat textformat). En custom parser ger full kontroll och inga yttre beroenden. Uppskattning: ~150-200 rader Python.

### 1.5 Beräkna RR och BR från SIE-data

**Balansräkning** — baserat på `#UB` (utgående balanser):
```
Tillgångar        = Summa UB för konton 1000-1999
Eget kapital      = Summa UB för konton 2000-2099
Skulder           = Summa UB för konton 2100-2999
```

**Resultaträkning** — baserat på `#RES` eller `#PSALDO`:
```
Nettoomsättning         = Summa konton 3000-3799 (negativt i SIE = intäkt)
Övriga rörelseintäkter  = Summa konton 3800-3999
Varuinköp/material      = Summa konton 4000-4999
Övriga ext. kostnader   = Summa konton 5000-6999
Personalkostnader       = Summa konton 7000-7699
Avskrivningar           = Summa konton 7700-7899
Finansiella poster      = Summa konton 8000-8799
Skatt                   = Summa konton 8800-8899
```

**OBS:** I SIE-filer är intäkter negativa och kostnader positiva. Vid presentation inverteras tecknet.

**Periodfiltrering med `#PSALDO`:**
```
#PSALDO 0 202601 3010 {} -105000.00    ← Januari
#PSALDO 0 202602 3010 {} -98000.00     ← Februari
```
Summera PSALDO-poster för önskade månader → periodens resultaträkning.

### 1.6 Förslag: MCP-tools

```python
@mcp.tool()
async def get_profit_and_loss(
    period_from: Optional[str] = None,   # "2026-01"
    period_to: Optional[str] = None,     # "2026-03"
    financial_year_date: Optional[str] = None,
) -> str:
    """Get profit and loss statement (resultaträkning).

    Returns revenue, costs, and result grouped by BAS account class.
    Uses SIE export from Fortnox and calculates period totals.
    """
```

```python
@mcp.tool()
async def get_balance_sheet(
    financial_year_date: Optional[str] = None,
) -> str:
    """Get balance sheet (balansräkning).

    Returns assets, equity, and liabilities from closing balances.
    """
```

**Intern implementation:**
1. `GET /3/sie/2?financialyear={id}` — hämta periodsaldon
2. Parsa SIE-textdata
3. Gruppera per kontoklass
4. Beräkna summor
5. Returnera formaterat resultat

---

## 2. Verifikationer (read)

### 2.1 Fortnox Voucher API

**Endpoint:** `GET /3/vouchers`

**List-response** (begränsat antal fält):

| Fält | Typ | Beskrivning |
|------|-----|-------------|
| `@url` | string | URL till full verifikation |
| `Description` | string | Beskrivning |
| `ReferenceNumber` | string | Referensnummer |
| `ReferenceType` | string | Typ: `INVOICE`, `SUPPLIERINVOICE`, etc. |
| `TransactionDate` | date | Transaktionsdatum |
| `VoucherNumber` | int | Verifikationsnummer |
| `VoucherSeries` | string | Serie (A, B, C, D...) |
| `Year` | int | Räkenskapsår-ID |

**Detail-response** (`GET /3/vouchers/{Series}/{Number}?financialyear={Year}`):

Samma fält som ovan PLUS:
- `Comments` — Kommentarer
- `CostCenter` — Kostnadsställe
- `Project` — Projekt
- `VoucherRows` — Array med transaktionsrader

**VoucherRow-fält:**

| Fält | Typ | Beskrivning |
|------|-----|-------------|
| `Account` | int | Kontonummer (t.ex. 5010) |
| `Debit` | decimal | Debetbelopp |
| `Credit` | decimal | Kreditbelopp |
| `Description` | string | Kontobeskrivning (auto från kontoplan) |
| `TransactionInformation` | string | Fritext |
| `CostCenter` | string | Kostnadsställe |
| `Project` | string | Projekt |
| `Removed` | bool | Borttagen rad |

### 2.2 Verifikationsserier (Voucher Series)

I svensk bokföring kategoriserar verifikationsserier olika typer av affärshändelser:

| Serie | Typisk användning |
|-------|-------------------|
| **A** | Manuella verifikationer (huvudbok) |
| **B** | Kundfakturor |
| **C** | Leverantörsfakturor |
| **D** | Kassaverifikationer / Löpande |
| **E-Z** | Valfria (lön, bank, etc.) |

Serierna konfigureras per räkenskapsår i Fortnox.

### 2.3 Query-parametrar

| Parameter | Beskrivning |
|-----------|-------------|
| `financialyear` | Räkenskapsår-ID (krävs) |
| `financialyeardate` | Datum inom räkenskapsår (alternativ) |
| `fromdate` | Filtrera från datum (YYYY-MM-DD) |
| `todate` | Filtrera till datum (YYYY-MM-DD) |
| `lastmodified` | Ändrade efter tidpunkt |
| `costcenter` | Filtrera per kostnadsställe |
| `project` | Filtrera per projekt |
| `sublist/{Series}` | Lista per serie (`GET /3/vouchers/sublist/A`) |

### 2.4 Viktigt: Rate limits och SIE-alternativ

**Problem:** Att hämta alla verifikationer med raddetaljer kräver ett API-anrop per verifikation (raderna finns inte i list-endpointen). Med Fortnox rate limit på 25 req/5s tar 500 verifikationer ~100 sekunder.

**Alternativ:** `GET /3/sie/4` ger ALLA verifikationer i en enda request. Bättre för bulk-analys. Enskild verifikationssökning via REST.

### 2.5 Förslag: MCP-tools

```python
@mcp.tool()
async def list_vouchers(
    financial_year_date: Optional[str] = None,
    series: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 25,
) -> str:
    """List vouchers (verifikationer) from Fortnox.

    Args:
        financial_year_date: Date within the financial year (YYYY-MM-DD).
        series: Filter by voucher series (e.g. "A", "B").
        from_date: Start date filter (YYYY-MM-DD).
        to_date: End date filter (YYYY-MM-DD).
        limit: Max vouchers to return (default 25).
    """
```

```python
@mcp.tool()
async def get_voucher(
    series: str,
    number: int,
    financial_year_date: Optional[str] = None,
) -> str:
    """Get full details for a specific voucher including all rows.

    Args:
        series: Voucher series (e.g. "A", "B").
        number: Voucher number within the series.
        financial_year_date: Date within the financial year (YYYY-MM-DD).
    """
```

```python
@mcp.tool()
async def search_vouchers(
    account: Optional[int] = None,
    cost_center: Optional[str] = None,
    min_amount: Optional[float] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> str:
    """Search vouchers by account, cost center, or amount.

    Uses SIE4 export for efficient bulk search instead of
    individual API calls per voucher.
    """
```

---

## 3. Funktionsindelad resultaträkning med custom mapping

### 3.1 Bakgrund: Två typer av resultaträkning

**Kostnadsslagsindelad** (ÅRL uppställningsform I) — standard i Sverige:
```
Nettoomsättning
Råvaror och förnödenheter         ← Kontoklass 4
Övriga externa kostnader          ← Kontoklass 5-6
Personalkostnader                 ← Kontoklass 7 (delar)
Avskrivningar                    ← Kontoklass 7 (delar)
= Rörelseresultat
```
Kostnaderna grupperas **efter sin natur** (vad de är).

**Funktionsindelad** (ÅRL uppställningsform II) — vanlig för större bolag:
```
Nettoomsättning
Kostnad för sålda varor           ← Produktion/tillverkning
Bruttoresultat
Försäljningskostnader             ← Alla kostnader relaterade till försäljning
Administrationskostnader          ← Alla kostnader relaterade till admin
Övriga rörelseintäkter
Övriga rörelsekostnader
= Rörelseresultat
```
Kostnaderna grupperas **efter sin funktion** (vad de används till).

### 3.2 Problemet: BAS-kontoplanen är kostnadsslagsindelad

BAS-konton mappar inte direkt till funktioner. Konto 5010 (Lokalhyra) kan vara:
- **Kostnad sålda varor** — om det är hyra för produktionslokal
- **Försäljningskostnad** — om det är hyra för säljkontor
- **Administrationskostnad** — om det är hyra för huvudkontor

**Lösning:** Fördelning via **kostnadsställe** (dimension 1 i Fortnox).

### 3.3 Visma Boksluts modell (referensimplementation)

Visma Bokslut löser detta med:

1. **Default-mappning baserad på kontonummer:**
   - Konton 3000-3799 → Nettoomsättning
   - Konton 3800-3899, 4000-5699 → Kostnad sålda varor
   - Konton 5700-6099 → Försäljningskostnader
   - Konton 6100-6999 → Administrationskostnader

2. **Fördelningsnycklar** — procentsatser som fördalar ett kontos saldo mellan funktioner

3. **"Belopp att fördela"** — om inget passat visas det separat

### 3.4 Vår modell: Kostnadsställe + Konto → Funktion

Istället för procentuell fördelning kan vi använda **kostnadsställen** som funktionsindikator. Varje transaktion i Fortnox har redan en kostnadsställe-dimension.

**Mappningsregel:**
```
(Konto, Kostnadsställe) → Funktion i RR
```

**Exempel:**
| Konto | Kostnadsställe | → Funktion |
|-------|---------------|------------|
| 5010 (Hyra) | PROD | Kostnad sålda varor |
| 5010 (Hyra) | SALJ | Försäljningskostnader |
| 5010 (Hyra) | ADMIN | Administrationskostnader |
| 7210 (Löner) | PROD | Kostnad sålda varor |
| 7210 (Löner) | SALJ | Försäljningskostnader |
| 7210 (Löner) | FOU | FoU-kostnader |
| 4010 (Material) | * | Kostnad sålda varor |
| 3010 (Försäljning) | * | Nettoomsättning |

`*` = alla kostnadsställen (default).

### 3.5 Dataformat: JSON-konfiguration

Ingen UI behövs i första steget. En JSON-fil räcker:

```json
{
  "version": "1.0",
  "description": "Funktionsindelad RR-mappning för Mitt Företag AB",

  "functions": [
    {"id": "net_sales", "label": "Nettoomsättning", "sort": 1},
    {"id": "cogs", "label": "Kostnad för sålda varor", "sort": 2},
    {"id": "selling", "label": "Försäljningskostnader", "sort": 4},
    {"id": "admin", "label": "Administrationskostnader", "sort": 5},
    {"id": "rnd", "label": "Forsknings- och utvecklingskostnader", "sort": 6},
    {"id": "other_income", "label": "Övriga rörelseintäkter", "sort": 7},
    {"id": "other_expense", "label": "Övriga rörelsekostnader", "sort": 8},
    {"id": "financial", "label": "Finansiella poster", "sort": 9}
  ],

  "calculated_lines": [
    {"id": "gross_profit", "label": "Bruttoresultat", "formula": "net_sales + cogs", "sort": 3},
    {"id": "operating_result", "label": "Rörelseresultat", "formula": "gross_profit + selling + admin + rnd + other_income + other_expense", "sort": 8.5}
  ],

  "default_rules": [
    {"account_range": [3000, 3799], "function": "net_sales"},
    {"account_range": [3800, 3999], "function": "other_income"},
    {"account_range": [4000, 4999], "function": "cogs"},
    {"account_range": [5000, 6999], "function": "admin"},
    {"account_range": [7000, 7699], "function": "admin"},
    {"account_range": [7700, 7899], "function": "admin"},
    {"account_range": [8000, 8999], "function": "financial"}
  ],

  "cost_center_overrides": [
    {"cost_center": "PROD", "account_range": [5000, 7899], "function": "cogs"},
    {"cost_center": "SALJ", "account_range": [5000, 7899], "function": "selling"},
    {"cost_center": "FOU",  "account_range": [5000, 7899], "function": "rnd"}
  ]
}
```

**Logik:**
1. Kolla om det finns en `cost_center_override` som matchar → använd den
2. Annars → använd `default_rule` baserad på kontonummer
3. Beräkna `calculated_lines` (bruttoresultat, rörelseresultat)

### 3.6 Datakälla: SIE Typ 3

SIE Typ 3 ger saldon **per objekt** (kostnadsställe/projekt). Det innehåller `#OUB` och `#PSALDO` med dimensionsdata:

```
#PSALDO 0 202601 5010 {1 "SALJ"} 8500.00
#PSALDO 0 202601 5010 {1 "ADMIN"} 12000.00
#PSALDO 0 202601 5010 {1 "PROD"} 6500.00
```

Med denna data + mappnings-JSON kan vi beräkna funktionsindelad RR automatiskt.

### 3.7 Förslag: MCP-tool

```python
@mcp.tool()
async def get_functional_pnl(
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
) -> str:
    """Get functional profit and loss (funktionsindelad resultaträkning).

    Distributes costs to functions (COGS, selling, admin, R&D)
    based on cost center mapping defined in functional_pnl_mapping.json.

    Requires SIE Type 3 data with cost center dimensions.
    """
```

### 3.8 Framtida UI-alternativ (ej nu)

När JSON-filen fungerar kan man tänka sig:
- **Claude Code prompt:** "Lägg till kostnadsstället LAGER som mappas till Kostnad sålda varor" → Claude redigerar JSON-filen
- **Enkel webapp:** React-formulär som redigerar JSON-filen
- **Excel-mall:** Sheet med mappningsregler som importeras

Men i MVP räcker det med att redigera JSON-filen direkt.

---

## 4. Implementationsplan

### Fas 1: SIE-parser + enkel RR/BR (1-2 dagar)

1. Skriv `sie_parser.py` — parsear SIE-text till Python-dicts
2. Testa med Fortnox sandbox (exportera SIE typ 2)
3. Implementera `get_profit_and_loss` tool
4. Implementera `get_balance_sheet` tool
5. Testa via Claude Code

### Fas 2: Verifikationer (0.5 dag)

1. Implementera `list_vouchers` tool
2. Implementera `get_voucher` tool
3. Testa med sandbox-data

### Fas 3: Funktionsindelad RR (1-2 dagar)

1. Skapa `functional_pnl_mapping.json` med default BAS-regler
2. Utöka SIE-parsern för att hantera Typ 3 (objektsaldon)
3. Implementera mappningslogik
4. Implementera `get_functional_pnl` tool
5. Testa med sandbox-data (kräver kostnadsställen)

### Fas 4: Compound tools (0.5 dag)

1. `get_cashflow_summary` — kombinerar obetalda fakturor + banksaldo
2. `compare_periods` — jämför två perioder automatiskt

---

## 5. Öppna frågor

- **SIE-encoding:** Fortnox returnerar SIE i CP437, men vi behöver verifiera detta praktiskt. `magnusfroste/sie-parser` har löst detta.
- **SIE Content-Type:** Fortnox SIE-endpoint returnerar troligen `text/plain` eller `application/octet-stream` — behöver testas.
- **Periodsaldon:** Finns `#PSALDO`-poster i Fortnox SIE Typ 2, eller bara i Typ 3/4? Behöver testas mot sandbox.
- **Kostnadsställen i SIE:** Hur representeras de i Fortnox SIE-export? Verifiera `#DIM`/`#OBJEKT`/`#OUB`-format.
- **Performance:** Hur stor är en SIE Typ 4-fil för ett typiskt SME? Viktig för att avgöra om vi kan parsa i realtid eller behöver caching.
- **JSON-mappning:** Ska filen ligga i `projects/fortnox-mcp/` eller vara konfigurerbar per bolag?

---

## Källor

- [SIE-Gruppen (sie.se)](https://sie.se/in-english/)
- [SIE4 Spec v4B (PDF)](https://sie.se/wp-content/uploads/2020/05/SIE_filformat_ver_4B_ENGLISH.pdf)
- [Fortnox Developer — Vouchers best practices](https://www.fortnox.se/developer/guides-and-good-to-know/best-practices/vouchers)
- [SCB Funktionsindelad RR (PDF)](https://www.scb.se/contentassets/4697fd6fb40147818a7d352dd100de5d/funktionsindelad-resultatrakning.pdf)
- [magnusfroste/sie-parser (GitHub)](https://github.com/magnusfroste/sie-parser)
- [magapp/parse-sie (GitHub)](https://github.com/magapp/parse-sie)
- [Visma Bokslut — Funktionsindelad RR](https://support.spiris.se/visma-bokslut/content/online-help/start-funktionsindelad-resultatrakning.htm)
