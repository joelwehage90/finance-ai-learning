# MCP (Model Context Protocol)

## Vad det är

MCP är ett öppet protokoll (skapat av Anthropic) som standardiserar hur AI-modeller pratar med externa system. Tänk på det som **USB-C för AI** — en universell kontakt. Innan MCP behövde varje AI-integration byggas custom. Med MCP kan vilken AI-klient som helst (Claude Code, Claude Desktop, Cursor, etc.) prata med vilken MCP-server som helst, utan att veta något om varandras interna detaljer.

## Varför det är viktigt

MCP löser "M×N-problemet": utan MCP behöver M stycken AI-klienter × N stycken verktyg = M×N integrationer. Med MCP behövs bara M + N — varje klient implementerar MCP-protokollet, varje verktyg exponeras som en MCP-server.

**Konkret:** Vår Fortnox MCP-server fungerar automatiskt med Claude Code, Claude Desktop, Cursor, Cline — utan en enda rad klientspecifik kod.

## Ekonomiexempel

En CFO vill fråga Claude: "Hur ser cashflowet ut den här månaden?" Claude kan via MCP-servern hämta obetalda kundfakturor, leverantörsfakturor som förfaller, och kontosaldon — allt utan att CFO:n behöver öppna Fortnox, exportera data, eller skriva ett enda API-anrop.

---

## Arkitektur — Hur allting hänger ihop

```
┌─────────────────────────────────────────────────────────────────┐
│                        DIN DATOR                                │
│                                                                 │
│  ┌──────────────┐     stdio (stdin/stdout)     ┌─────────────┐ │
│  │              │ ◄──────────────────────────► │             │ │
│  │  Claude Code │     JSON-RPC meddelanden      │  Fortnox    │ │
│  │  (AI-klient) │                               │  MCP Server │ │
│  │              │  "Vilka tools finns?"          │  (Python)   │ │
│  │  Förstår MCP │  "Kör list_invoices"          │             │ │
│  │  protokollet │  "Här är resultatet: ..."     │  Förstår    │ │
│  │              │                               │  Fortnox    │ │
│  └──────────────┘                               └──────┬──────┘ │
│                                                        │        │
└────────────────────────────────────────────────────────│────────┘
                                                         │
                                                    HTTPS (internet)
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │   Fortnox API   │
                                                │  api.fortnox.se │
                                                │                 │
                                                │  Fakturor       │
                                                │  Kunder         │
                                                │  Konton         │
                                                │  Bokföring      │
                                                └─────────────────┘
```

### Kommentarer till diagrammet

1. **Claude Code** är AI-klienten — den du chattar med. Den vet inte vad Fortnox är, men den vet hur man pratar MCP.

2. **Fortnox MCP Server** är bryggan. Den översätter MCP-anrop ("kör `list_invoices`") till Fortnox API-anrop (`GET /3/invoices`). Den körs lokalt på din dator som en Python-process.

3. **Kommunikationen** mellan Claude Code och MCP-servern sker via **stdio** (standard input/output) — de skickar JSON-meddelanden till varandra via terminalen. Ingen nätverkstrafik, ingen port, ingen server att starta separat.

4. **Fortnox API** lever på internet. MCP-servern gör HTTPS-anrop dit med dina credentials.

---

## Detaljerat flöde — Vad händer när du frågar om fakturor?

```
Du skriver i terminalen:
"Visa obetalda fakturor för mars"

         │
         ▼
┌─── STEG 1: Claude tänker ───────────────────────────────────┐
│                                                              │
│  Claude analyserar din fråga och bestämmer:                  │
│  "Jag behöver använda list_invoices-verktyget                │
│   med status='unpaid' och from_date='2026-03-01'"           │
│                                                              │
│  Claude vet vilka tools som finns eftersom MCP-servern       │
│  berättade det vid uppstart (tool discovery).                │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌─── STEG 2: MCP-anrop (Claude → Server) ─────────────────────┐
│                                                               │
│  Claude skickar via stdin:                                    │
│  {                                                            │
│    "method": "tools/call",                                    │
│    "params": {                                                │
│      "name": "list_invoices",                                 │
│      "arguments": {                                           │
│        "status": "unpaid",                                    │
│        "from_date": "2026-03-01"                              │
│      }                                                        │
│    }                                                          │
│  }                                                            │
└───────────────────────────────────────────────────────────────┘
         │
         ▼
┌─── STEG 3: MCP-servern agerar ───────────────────────────────┐
│                                                               │
│  fortnox_server.py tar emot anropet och:                     │
│                                                               │
│  a) Hämtar/förnyar access token (Client Credentials)         │
│  b) Gör GET https://api.fortnox.se/3/invoices                │
│     ?filter=unpaid&fromdate=2026-03-01                        │
│  c) Formaterar svaret som läsbar text                        │
│  d) Returnerar resultatet via stdout                         │
└───────────────────────────────────────────────────────────────┘
         │
         ▼
┌─── STEG 4: Claude analyserar och svarar ─────────────────────┐
│                                                               │
│  Claude får tillbaka fakturadata (JSON) och                   │
│  formulerar ett naturligt svar:                               │
│                                                               │
│  "Du har 7 obetalda fakturor i mars, totalt 142 350 kr.     │
│   Störst är faktura #1047 till Acme AB på 85 000 kr          │
│   som förfaller 2026-03-25."                                 │
└───────────────────────────────────────────────────────────────┘
```

---

## MCP-protokollets tre byggstenar

| Byggsten | Vad det är | Vår implementation |
|---|---|---|
| **Tools** | Funktioner som AI:n kan anropa | `list_invoices`, `get_invoice`, `list_customers`, etc. |
| **Resources** | Data som AI:n kan läsa (typ filer) | Inte implementerat ännu |
| **Prompts** | Fördefinierade prompt-templates | Inte implementerat ännu |

I vår MCP-server använder vi bara **Tools** — det vanligaste och mest kraftfulla.

---

## Hur Claude Code hittar MCP-servern

`.mcp.json` i projektroten talar om för Claude Code vilka MCP-servrar som finns:

```json
{
  "mcpServers": {
    "fortnox": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--with-requirements", "projects/fortnox-mcp/requirements.txt",
        "projects/fortnox-mcp/fortnox_server.py"
      ]
    }
  }
}
```

**Vad detta säger:**
- Det finns en MCP-server som heter "fortnox"
- Den kommunicerar via stdio (terminal in/ut)
- Starta den med `uv run ...` (som hanterar Python och dependencies)

Claude Code läser denna fil vid uppstart, startar servern, frågar den "vilka tools har du?", och registrerar dem. Sedan kan Claude använda dem när det behövs.

---

## MCP vs direkt API vs Tool Use — vad är skillnaden?

```
Utan MCP (direkt tool use):
  Claude API → din app → tool definitions hårdkodade i appen → Fortnox API
  Problem: Varje AI-klient behöver egen Fortnox-integration

Med MCP:
  Vilken AI-klient som helst → MCP-protokoll → Fortnox MCP Server → Fortnox API
  Fördel: Bygg en gång, fungerar överallt
```

| Aspekt | Direkt Tool Use | MCP |
|---|---|---|
| Koppling | AI-klienten känner till varje verktyg | AI-klienten känner till MCP-protokollet |
| Återanvändning | Varje klient bygger egen integration | En server, många klienter |
| Deployment | Inuti din app | Separat process |
| Standard | Proprietärt per AI-leverantör | Öppet protokoll |

---

## Vad jag fortfarande behöver förstå bättre

<!-- TODO: Hur fungerar MCP Resources praktiskt? Kan vi exponera kontoplanen som en resource? -->
<!-- TODO: Kan MCP-servrar prata med varandra (chaining)? -->
<!-- TODO: Hur hanteras säkerhet — kan en MCP-server göra farliga saker? -->
<!-- TODO: SSE (Server-Sent Events) transport vs stdio — när behövs det? -->

## Relaterade koncept

- **Tool Use** — MCP är standardiserad tool use (se concepts/tool-use.md)
- **Fortnox API** — det underliggande API:t som MCP-servern wrapprar (se concepts/fortnox-api.md)
- **Agent loop** — Claude Code är en agent som använder MCP-tools i en loop
