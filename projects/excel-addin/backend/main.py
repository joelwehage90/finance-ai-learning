"""Excel Add-in Backend — FastAPI server for Fortnox data.

Serves LRK, KRK, Resultaträkning and Balansräkning data to the
Excel taskpane frontend. Reuses FortnoxClient, FortnoxSIEClient
and sie_parser from the existing codebase.

Usage:
    uvicorn main:app --reload --port 8000
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add sibling projects to import path so we can reuse existing code.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "fortnox-mcp"))
sys.path.insert(0, str(_PROJECT_ROOT / "sie-pipeline"))

from fortnox_client import FortnoxClient  # noqa: E402
from fortnox_sie_client import FortnoxSIEClient  # noqa: E402

# Load environment variables — try local .env first, fall back to fortnox-mcp
_env_path = Path(__file__).resolve().parent / ".env"
if not _env_path.exists():
    _env_path = _PROJECT_ROOT / "fortnox-mcp" / ".env"
load_dotenv(_env_path)


def _require_env(name: str) -> str:
    """Get a required environment variable or exit."""
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


# Shared client instances — created on startup, closed on shutdown.
fortnox_client: FortnoxClient | None = None
sie_client: FortnoxSIEClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create and tear down Fortnox clients."""
    global fortnox_client, sie_client

    client_id = _require_env("FORTNOX_CLIENT_ID")
    client_secret = _require_env("FORTNOX_CLIENT_SECRET")
    tenant_id = _require_env("FORTNOX_TENANT_ID")

    fortnox_client = FortnoxClient(client_id, client_secret, tenant_id)
    sie_client = FortnoxSIEClient(client_id, client_secret, tenant_id)

    yield

    await fortnox_client.close()
    await sie_client.close()


app = FastAPI(
    title="Fortnox Excel Add-in API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Excel taskpane (localhost dev server) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost:3000",
        "https://localhost:3001",
        "http://localhost:3000",
        "http://localhost:3001",
        "null",  # Office taskpane may send origin: null
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Import and register routers
from routers.meta import router as meta_router  # noqa: E402
from routers.invoices import router as invoices_router  # noqa: E402
from routers.reports import router as reports_router  # noqa: E402

app.include_router(meta_router, prefix="/api")
app.include_router(invoices_router, prefix="/api")
app.include_router(reports_router, prefix="/api")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
