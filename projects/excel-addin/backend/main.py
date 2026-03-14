"""Excel Add-in Backend — FastAPI server for accounting data.

Serves LRK, KRK, Resultaträkning, Balansräkning, Huvudbok, and
comparative reports to the Excel taskpane frontend. Uses the
AccountingProvider abstraction to support multiple accounting systems
(Fortnox, Visma, etc.).

Usage:
    uvicorn main:app --reload --port 8000
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import get_settings, validate_production_settings

logger = logging.getLogger(__name__)

# Add sibling projects to import path so we can reuse existing code.
# NOTE: In Docker, PYTHONPATH env var handles this instead.
# This sys.path manipulation is a known trade-off for local dev
# until packages are published as proper pip packages.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "fortnox-mcp"))
sys.path.insert(0, str(_PROJECT_ROOT / "sie-pipeline"))

settings = get_settings()

# --- Rate limiting (S8) ---
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

# Shared provider instance — created on startup, closed on shutdown.
# In dev mode this is used directly; in production the auth dependency
# creates per-request providers from stored OAuth tokens.
from providers.base import AccountingProvider  # noqa: E402

provider: AccountingProvider | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create and tear down the accounting provider.

    Also validates production settings and cleans up expired sessions.
    """
    global provider

    # SECURITY (S2, S3): Validate critical settings before serving traffic.
    validate_production_settings(settings)

    # SECURITY (S9): Remind operator about TLS in production.
    if not settings.dev_mode:
        logger.warning(
            "Running without TLS — ensure a reverse proxy (Caddy, nginx, "
            "or a cloud provider like Render) provides HTTPS in production."
        )

        # (S14) Clean up expired/revoked sessions on startup.
        try:
            from datetime import datetime, timezone

            from sqlalchemy import delete, or_

            from db import async_session
            from models import UserSession

            async with async_session() as db:
                result = await db.execute(
                    delete(UserSession).where(
                        or_(
                            UserSession.expires_at < datetime.now(timezone.utc),
                            UserSession.revoked == True,  # noqa: E712
                        )
                    )
                )
                await db.commit()
                if result.rowcount:
                    logger.info("Cleaned up %d expired/revoked sessions", result.rowcount)
        except Exception:
            logger.debug("Session cleanup skipped (database may not be available)")

    from providers.fortnox import FortnoxProvider  # noqa: E402

    provider = FortnoxProvider(
        client_id=settings.fortnox_client_id,
        client_secret=settings.fortnox_client_secret,
        tenant_id=settings.fortnox_tenant_id,
    )

    yield

    await provider.close()


app = FastAPI(
    title="Bokföring Excel Add-in API",
    version="0.3.0",
    lifespan=lifespan,
)

# Register rate limiter (S8).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — dynamic origins from settings (includes localhost defaults
# plus any production URLs configured via ALLOWED_ORIGINS env var).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Import and register routers
from routers.auth import router as auth_router  # noqa: E402
from routers.huvudbok import router as huvudbok_router  # noqa: E402
from routers.invoices import router as invoices_router  # noqa: E402
from routers.meta import router as meta_router  # noqa: E402
from routers.reports import router as reports_router  # noqa: E402

app.include_router(meta_router, prefix="/api")
app.include_router(invoices_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(huvudbok_router, prefix="/api")
app.include_router(auth_router, prefix="/api")


# In DEV_MODE, override the auth dependency to return the global
# env-var-based provider — no OAuth needed for local development.
if settings.dev_mode:
    from auth import get_current_provider  # noqa: E402

    async def _dev_provider_override():
        """Return the global provider without auth checks."""
        return provider

    app.dependency_overrides[get_current_provider] = _dev_provider_override


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Translate exceptions into structured JSON error responses.

    SECURITY (S7): Never return raw exception messages to clients — they
    may contain file paths, DB connection strings, or internal state.
    Log details server-side only.
    """
    if isinstance(exc, ValueError):
        logger.warning("Validation error on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=400, content={"detail": "Invalid request parameters"})
    if isinstance(exc, RuntimeError):
        logger.error("Runtime error on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=502, content={"detail": "Upstream service error"})
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
