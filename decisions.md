# Arkitekturbeslut & Designval

Här dokumenterar jag tekniska och strategiska val jag gör under lärandet, med motivering och kända nackdelar.

---

## Mall för beslut

```
### [Datum] Kort rubrik

**Kontext:** Vad var situationen?
**Beslut:** Vad valde jag?
**Motivering:** Varför?
**Nackdelar:** Vad förlorar jag?
**Uppföljning:** När/hur bör jag ompröva detta?
```

---

### 2026-03-08 Dokumentationsformat: Markdown i Git-repo

**Kontext:** Behöver ett sätt att dokumentera lärandet som är sökbart, versionerbart och integrerat med Claude-ekosystemet.

**Beslut:** Markdown-filer i ett git-repo med strukturerade mappar.

**Motivering:** Markdown är det format CLAUDE.md, Skills och README-filer använder. Genom att skriva i .md tränar jag samtidigt på formatet jag kommer använda i produktion. Git ger historik och backup.

**Nackdelar:** Inget visuellt gränssnitt — kan bli ostrukturerat om jag inte håller disciplinen. Saknar inbyggd sökning (men `grep` och Claude Code löser det).

**Uppföljning:** Utvärdera efter 4 veckor om strukturen fungerar eller behöver justeras.
