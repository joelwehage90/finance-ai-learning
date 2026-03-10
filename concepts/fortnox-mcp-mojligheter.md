# Fortnox MCP — Möjligheter

Vad kan vi bygga med en MCP-server mot Fortnox? Det här dokumentet utforskar möjligheter i tre tidshorisonter: **nu (det vi har)**, **nästa steg (veckor)**, och **vision (blue sky)**.

---

## Vad vi har idag (MVP)

Fem read-only tools:

| Tool | Controller-nytta |
|---|---|
| `list_invoices` | "Vilka fakturor är obetalda?" |
| `get_invoice` | "Visa detaljer för faktura 1047" |
| `list_customers` | "Vilka kunder har vi?" |
| `get_account_balances` | "Vad står det på konto 1930?" |
| `get_company_info` | "Visa företagsinformation" |
| `list_supplier_invoices` | "Vilka leverantörsfakturor har vi?" |
| `get_supplier_invoice` | "Visa detaljer för leverantörsfaktura 5023" |

**Vad vi kan fråga Claude redan idag:**
- "Vilka obetalda fakturor finns det just nu?"
- "Hur mycket har vi fakturerat Acme AB i år?"
- "Vad är saldot på konto 1930 (företagskontot)?"
- "Lista alla leverantörsfakturor som är obetalda och förfallna"

**Begränsningar:** Enbart läsning. Ingen rapportgenerering. Inget historiskt perspektiv (jämförelser). Inga verifikationer.

---

## Nästa steg — Görbart inom veckor

### 1. Fler read-tools

```
get_vouchers          → "Visa verifikationer för mars"
get_profit_and_loss   → SIE-export + beräkning av resultaträkning
get_balance_sheet     → SIE-export + beräkning av balansräkning
list_projects         → "Vilka projekt har vi?"
list_cost_centers     → "Vilka kostnadsställen finns?"
```

**Varför viktigt:** `get_profit_and_loss` och `get_balance_sheet` är *the killer features* för en controller. Idag finns inga rapport-endpoints i Fortnox API — man måste hämta SIE-data och beräkna själv. MCP-servern kan göra detta åt Claude, och Claude kan sedan analysera resultatet.

**Ekonomiexempel:** "Jämför intäkterna Q1 2025 mot Q1 2026 och förklara de största avvikelserna" — detta kräver SIE-export för två perioder, beräkning av periodsaldon, och analys. Allt möjligt med rätt tools.

### 2. Smarta sammanställningar (compound tools)

Istället för att Claude gör flera anrop kan vi skapa tools som kombinerar data:

```python
@mcp.tool()
async def get_cashflow_summary(month: str):
    """Kassaflödessammanställning: kundfordringar in, leverantörsskulder ut."""
    # Hämtar obetalda kundfakturor (pengar på väg in)
    # Hämtar obetalda leverantörsfakturor (pengar på väg ut)
    # Hämtar saldo på bankkonto (1930)
    # Returnerar sammanfattning
```

**Varför:** Sparar tokens och API-anrop. Claude behöver bara ett tool-anrop istället för tre. Snabbare svar.

### 3. MCP Resources — Kontoplanen som referensdata

```python
@mcp.resource("bas://kontoplan")
async def get_kontoplan():
    """BAS-kontoplanen — Claude kan referera till denna för att förstå kontonummer."""
    return kontoplan_data
```

**Vad det ger:** Claude kan slå upp "vad är konto 4010?" utan att göra ett API-anrop. Kontoplanen ändras sällan och kan cachas. Resources laddas vid behov — inte vid varje anrop.

### 4. Prompt-templates för vanliga uppgifter

```python
@mcp.prompt()
def monthly_review(month: str):
    """Mall för månatlig uppföljning."""
    return f"""Gör en månatlig uppföljning för {month}:
    1. Hämta resultaträkning
    2. Jämför intäkter och kostnader mot föregående månad
    3. Identifiera de 3 största avvikelserna
    4. Sammanfatta i en tabell
    """
```

**Vad det ger:** Standardiserade arbetsflöden som en controller kör varje månad. Tryck på en knapp, få en rapport.

---

## Vision — Blue sky (månader)

### 5. Write-operationer med human-in-the-loop

```
Du: "Periodisera hyran 60 000 kr över Q1 (konto 5010, 20 000/mån)"

Claude: "Jag föreslår att skapa tre verifikationer:
  - Jan: Debet 5010 (20 000), Kredit 1790 (20 000)
  - Feb: Debet 5010 (20 000), Kredit 1790 (20 000)
  - Mar: Debet 5010 (20 000), Kredit 1790 (20 000)

  Ska jag bokföra dessa?"

Du: "Ja"

Claude: [skapar verifikationerna i Fortnox]
```

**Varför human-in-the-loop?** Skrivoperationer i bokföring är oåterkalleliga (verifikationer kan inte ändras i Fortnox). Claude måste alltid visa vad den tänker göra och vänta på godkännande.

**Implementation:** MCP har stöd för "confirmation" — verktyget kan pausa och vänta på användarens svar innan det utför handlingen.

### 6. AI-driven Controller-assistent

Tänk dig en controller som öppnar Claude Code på morgonen:

```
"God morgon. Gör min dagliga genomgång."

Claude:
- Kollar obetalda fakturor → 3 förfallna, totalt 127 000 kr
- Kollar leverantörsfakturor → 2 som förfaller idag
- Kollar kassaflöde → 340 000 kr på banken
- Kollar avvikelser mot budget → Kontorsmaterial 15% över budget

"God morgon! Här är din dagliga sammanfattning:

📊 Likviditet: 340 000 kr på bankkontot
⚠️  3 förfallna kundfakturor (127 000 kr) — äldsta är 12 dagar sen
💸 2 leverantörsfakturor förfaller idag (45 000 kr)
📈 Kontorsmaterial ligger 15% över budget — vill du att jag gräver djupare?
"
```

**Vad som krävs:** Prompt-template + rätt tools + eventuellt schemaläggning.

### 7. Multi-bolag-stöd

Om du hanterar ekonomin för flera bolag (t.ex. inom en koncern):

```
Du: "Jämför EBITDA för alla tre bolagen i Q4"

Claude: [byter TenantId, hämtar data för Bolag A, B, C]
"Här är jämförelsen:
| Bolag    | Intäkter  | EBITDA    | Marginal |
|----------|-----------|-----------|----------|
| Bolag A  | 2.1 Mkr   | 420 tkr   | 20%      |
| Bolag B  | 1.8 Mkr   | 162 tkr   | 9%       |
| Bolag C  | 3.4 Mkr   | 850 tkr   | 25%      |
"
```

**Implementation:** Antingen flera `.env`-filer eller en databas med credentials per bolag. MCP-servern stödjer en parameter `company` som väljer rätt credentials.

### 8. Realtidsnotifieringar via WebSocket

```
Fortnox WebSocket → MCP-server → notifiering till Claude

"Ny kundfaktura registrerad: #1089, Acme AB, 45 000 kr"
"Leverantörsfaktura #5024 betald"
```

Fortnox har WebSocket-stöd (se concepts/fortnox-api.md, sektion 9). MCP-servern kan prenumerera på events och proaktivt informera Claude.

**Begränsning:** Kräver att MCP-servern kör kontinuerligt, inte bara vid anrop.

### 9. Integration med andra MCP-servrar

MCP:s styrka är att flera servrar kan samexistera. Tänk dig:

```json
{
  "mcpServers": {
    "fortnox": { "..." },
    "supabase": { "..." },
    "google-sheets": { "..." },
    "email": { "..." }
  }
}
```

```
Du: "Hämta försäljningsdata från Fortnox, jämför med budget i Google Sheets,
     och maila rapporten till CFO:n"

Claude:
1. fortnox.get_profit_and_loss(period="2026-Q1")
2. google-sheets.read_range(sheet="Budget 2026", range="B2:D13")
3. [analyserar avvikelser]
4. email.send(to="cfo@foretaget.se", subject="Q1 avvikelserapport", body="...")
```

**Poängen:** Varje MCP-server gör en sak bra. Claude orkestrerar dem.

### 10. Excel-rapporter direkt från Claude

```
Du: "Skapa en Excel-rapport med alla kundfakturor från Q1, grupperade per kund"

Claude:
1. fortnox.list_invoices(from_date="2026-01-01", to_date="2026-03-31")
2. [grupperar och formaterar data]
3. [genererar .xlsx med xlsxwriter]
4. "Rapporten är sparad som Q1_fakturor.xlsx"
```

**Implementation:** Claude Code kan redan skriva filer. Kombinerat med Fortnox-data kan det bli en kraftfull rapportmotor.

---

## Prioritering — Var ger det mest värde?

| # | Möjlighet | Värde för controller | Svårighet | Rekommendation |
|---|---|---|---|---|
| 1 | SIE-baserad P&L/BR | ⭐⭐⭐⭐⭐ | Medel | **Gör först** |
| 2 | Verifikationer (read) | ⭐⭐⭐⭐ | Låg | Gör snart |
| 3 | Compound tools (cashflow) | ⭐⭐⭐⭐ | Låg | Gör snart |
| 4 | Kontoplans-resource | ⭐⭐⭐ | Låg | Enkel vinst |
| 5 | Prompt-templates | ⭐⭐⭐ | Låg | Enkel vinst |
| 6 | Write med bekräftelse | ⭐⭐⭐⭐ | Hög | Planera noga |
| 7 | Multi-bolag | ⭐⭐⭐⭐ | Medel | Om relevant |
| 8 | WebSocket-events | ⭐⭐ | Hög | Nice-to-have |
| 9 | Multi-MCP (Sheets, email) | ⭐⭐⭐⭐⭐ | Medel (andra bygger servrarna) | Undersök befintliga MCP-servrar |
| 10 | Excel-generering | ⭐⭐⭐⭐ | Låg (Claude Code kan redan) | Testa direkt |

---

## Den stora bilden

```
          Idag                    Snart                     Vision
     ┌─────────────┐      ┌─────────────────┐      ┌──────────────────┐
     │ Read-only   │      │ + Rapporter     │      │ AI Controller-   │
     │ fakturor,   │  →   │ + Verifikationer│  →   │ assistent som    │
     │ kunder,     │      │ + Cashflow      │      │ gör daglig       │
     │ konton      │      │ + Prompt-mallar │      │ uppföljning,     │
     │             │      │                 │      │ bokför, och      │
     │ "Visa data" │      │ "Analysera data"│      │ rapporterar      │
     └─────────────┘      └─────────────────┘      └──────────────────┘
```

Varje steg bygger på det förra. MVP:n vi har nu bevisar att konceptet fungerar. Nästa steg handlar om att göra det *användbart* för en controller. Visionen handlar om att göra det *oumbärligt*.

---

## Vad jag fortfarande behöver förstå bättre

<!-- TODO: Hur parsas SIE4-filer i Python? Finns det ett bibliotek? -->
<!-- TODO: Vilka befintliga MCP-servrar finns för Google Sheets, email, etc.? -->
<!-- TODO: Hur funkar MCP confirmation/human-in-the-loop för write-operationer? -->
<!-- TODO: Vad är Fortnox prissättning för API-anrop vid höga volymer? -->
<!-- TODO: Hur hanterar man audit trail — logga alla MCP-anrop? -->
