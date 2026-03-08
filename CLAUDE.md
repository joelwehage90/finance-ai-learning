# Finance AI Learning — Projektinstruktioner

## Om detta projekt

Detta är Joels lärrepo för AI tooling, agentiska system och modern developer productivity, med fokus på tillämpningar inom ekonomi, controlling och CFO-arbete.

## Språk och kontext

- Dokumentation skrivs på **svenska** om inget annat anges
- Kod och kodkommentarer skrivs på **engelska**
- Ekonomitermer följer svensk praxis (BAS-kontoplan, K2/K3, Fortnox-terminologi)

## Mappstruktur

```
journal/       → Daterade läranteckningar (YYYY-MM-DD.md)
concepts/      → En fil per koncept, i egna ord med ekonomiexempel
prompts/       → System prompts för controlleruppgifter
projects/      → Praktiska projekt (varje projekt i egen mapp)
templates/     → Återanvändbara mallar
decisions.md   → Arkitekturbeslut och motiveringar
```

## Kodstil

- Python: följ PEP 8, type hints där det är naturligt
- Markdown: ATX-rubriker (#), inga HTML-taggar om det inte behövs
- JSON-schema: använd descriptive field names på engelska

## Principer

1. **Skriv för dig själv om 6 månader** — om du inte förstår det då var det för vagt
2. **Ekonomiexempel alltid** — varje koncept ska ha minst ett kopplat till controlling/CFO
3. **Beslut motiveras** — varför, inte bara vad
4. **Ärligt om luckor** — markera saker du inte förstår med `<!-- TODO: förstå detta bättre -->`
