# Säkerhetsåtgärder att implementera

> Skapad 2026-03-14 efter säkerhetsgranskning.
> Instruktion till Claude: "implementera alla punkter om it-säkerhet" = denna fil.
> **Status: ALLA 22 PUNKTER IMPLEMENTERADE** (2026-03-14)

## KRITISKT

- [x] **S1. Default dev_mode=False** — Ändra `config.py` så `dev_mode` defaultar till `False`. Kräv explicit `DEV_MODE=true` i `.env` för lokal utveckling.

- [x] **S2. Ingen default JWT-hemlighet** — Ta bort default-värdet `"dev-secret-change-in-production"` från `jwt_secret` i `config.py`. Lägg till startup-validering: om `DEV_MODE=false` och `jwt_secret` saknas eller matchar default → kasta fel vid uppstart.

- [x] **S3. Validera krypteringsnyckel vid uppstart** — Flytta valideringen av `token_encryption_key` från `crypto.py` (lazy) till startup/lifespan i `main.py`. Om `DEV_MODE=false` och nyckeln saknas → stoppa appen direkt.

- [x] **S4. Säkra docker-compose** — Bind PostgreSQL-porten till `127.0.0.1:5432:5432` istället för `5432:5432`. Byt lösenord från `postgres` till en env-variabel. Lägg kommentar att produktionslösenord ska vara starkt.

## HÖGT

- [x] **S5. Kryptografisk OAuth state** — I `dialog.ts`: generera `crypto.randomUUID()` som state, spara i variabel. I `callback.ts`: skicka med den i messageParent. I `AuthContext.tsx`: verifiera att state matchar innan callback-POST. Backend: verifiera state om möjligt.

- [x] **S6. Vitlista redirect_uri** — I `routers/auth.py`: hårdkoda eller vitlista tillåtna redirect_uri:er. Ignorera `body.redirect_uri` och använd server-side konfiguration.

- [x] **S7. Sanera felmeddelanden** — I `routers/auth.py`: logga Fortnox-svar server-side, returnera generiskt fel till klient. I `main.py`: returnera generiska meddelanden för ValueError/RuntimeError, logga detaljer.

- [x] **S8. Rate limiting** — Installera `slowapi`. Lägg till rate limits: `/api/auth/callback` (max 5/min/IP), `/api/auth/config/*` (max 20/min/IP), övriga endpoints (max 60/min/IP).

- [x] **S9. HTTPS-varning** — Lägg till startup-check i `main.py` lifespan: om `DEV_MODE=false`, logga varning "Running without TLS — ensure a reverse proxy provides HTTPS".

## MEDIUM

- [x] **S10. Granska null-origin i CORS** — Testa om Office taskpane faktiskt skickar `origin: null`. Om ja: dokumentera varför. Om nej: ta bort den. Lägg till kommentar oavsett.

- [x] **S11. Begränsad SIE-cache** — Byt från rå dict till `cachetools.TTLCache(maxsize=100, ttl=60)`. Lägg till `cachetools` i requirements.

- [x] **S12. Dokumentera JWT-i-minne** — Lägg kommentar i `api.ts` och `AuthContext.tsx` att detta är en medveten trade-off pga Office iframe-begränsningar. Notera att XSS-prevention är kritiskt.

- [x] **S13. Pinna dependencies** — Kör `pip freeze` och pinna alla versioner i `requirements.txt`. Lägg till kommentar om att köra `pip-audit` regelbundet.

- [x] **S14. Session-cleanup** — Lägg till en startup-rutin i `main.py` lifespan som kör `DELETE FROM user_sessions WHERE expires_at < now() OR revoked = true`. Lägg till index på `expires_at`.

- [x] **S15. Verifiera logout-anropare** — Ändra `/api/auth/logout` att använda `Authorization`-header istället för body. Verifiera att JWT:ns `jti` matchar sessionen som revokeras.

- [x] **S16. AAD i AES-GCM** — Skicka `tenant_id.encode()` som AAD-parameter till `aesgcm.encrypt()` och `aesgcm.decrypt()`. Kräver migrering av befintliga tokens (dekryptera utan AAD, kryptera med AAD).

## LÅGT

- [x] **S17. Icke-root Docker-user** — Lägg till `RUN adduser --disabled-password --no-create-home appuser` och `USER appuser` i Dockerfile.

- [x] **S18. Fixa datetime.utcnow()** — Byt alla `default=datetime.utcnow` i `models.py` till `default=lambda: datetime.now(timezone.utc)`.

- [x] **S19. Validera datum/period-format** — Lägg till regex-validering i FastAPI Query-parametrar: `Query(..., pattern=r"^\d{4}-\d{2}$")` för perioder, `r"^\d{4}-\d{2}-\d{2}$"` för datum.

- [x] **S20. Fixa sys.path-import** — I Dockerfile: PYTHONPATH hanterar redan detta. I lokal dev: dokumentera att `sys.path`-manipulation är en medveten trade-off tills paketen eventuellt publiceras som pip-paket.

- [x] **S21. Hantera logout-fel** — I `AuthContext.tsx`: lägg till retry-logik eller visa meddelande om servern inte svarar vid logout.

- [x] **S22. Multi-stage Docker build** — Bygg dependencies i en builder-stage med gcc, kopiera enbart kompilerade paket till en slim final-image utan gcc.
