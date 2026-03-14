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

from config import get_settings

logger = logging.getLogger(__name__)

# Add sibling projects to import path so we can reuse existing code.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "fortnox-mcp"))
sys.path.insert(0, str(_PROJECT_ROOT / "sie-pipeline"))

settings = get_settings()

# Shared provider instance — created on startup, closed on shutdown.
# In dev mode this is used directly; in production the auth dependency
# creates per-request providers from stored OAuth tokens.
from providers.base import AccountingProvider  # noqa: E402

provider: AccountingProvider | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create and tear down the accounting provider."""
    global provider

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
    version="0.2.0",
    lifespan=lifespan,
)

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
from routers.meta import router as meta_router  # noqa: E402
from routers.invoices import router as invoices_router  # noqa: E402
from routers.reports import router as reports_router  # noqa: E402
from routers.huvudbok import router as huvudbok_router  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402

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
    """Translate exceptions into structured JSON error responses."""
    if isinstance(exc, ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    if isinstance(exc, RuntimeError):
        logger.error("Runtime error on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=502, content={"detail": str(exc)})
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
