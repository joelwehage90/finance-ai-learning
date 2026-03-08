# Tool Use (Function Calling)

## Vad det är

Möjligheten för en LLM att anropa externa funktioner under ett resonemang. Jag definierar "verktyg" med namn, beskrivning och parameterschema. LLM:en bestämmer själv när det är lämpligt att anropa verktyget och genererar rätt parametrar.

## Varför det är viktigt

Utan tool use är en LLM bara en textgenerator. Med tool use kan den agera i världen — slå upp data, räkna, skriva filer. Det är mekanismen som gör allt annat möjligt: MCP är standardiserad tool use, agents är tool use i en loop, Skills styr hur tool use används.

## Ekonomiexempel

En agent som analyserar månadsresultatet behöver kunna:

1. `hämta_resultaträkning(företag, period)` — hämtar data från Fortnox
2. `hämta_budget(företag, period)` — hämtar budgetdata
3. `beräkna_varians(utfall, budget)` — räknar ut avvikelser
4. `formatera_rapport(data, mall)` — producerar färdig rapport

LLM:en bestämmer själv ordningen och hanterar resultaten.

## Hur det fungerar (API-flöde)

```
User: "Hur gick februari för Bolaget AB?"
    ↓
Assistant: tool_use → hämta_resultaträkning("bolaget-ab", "2026-02")
    ↓
User (tool_result): { revenue: 1250000, costs: 1080000, ... }
    ↓
Assistant: tool_use → hämta_budget("bolaget-ab", "2026-02")
    ↓
User (tool_result): { revenue: 1300000, costs: 1050000, ... }
    ↓
Assistant: "Intäkterna landade 3.8% under budget, främst drivet av..."
```

## Vad jag fortfarande behöver förstå bättre

<!-- TODO: Hur structured outputs interagerar med tool use — kan jag tvinga JSON-schema på slutsvaret även när tools används? -->
<!-- TODO: Felhantering — vad händer om ett verktyg returnerar ett oväntat format? -->

## Relaterade koncept

- **MCP** — standardiserar hur tools exponeras (se concepts/mcp.md)
- **Agent loop** — tool use i en while-loop tills uppgiften är klar
- **Structured outputs** — garanterar output-format
