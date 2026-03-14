"""Application configuration — Pydantic settings with env/.env support.

All configuration is read from environment variables (or a .env file).
Import ``settings`` from this module to access config values.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central config for the Excel add-in backend."""

    # --- Database ---
    database_url: str = "postgresql+asyncpg://localhost/excel_addin"

    # --- JWT ---
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_expiry_hours: int = 24

    # --- Token encryption ---
    # Base64-encoded 32-byte key for AES-256-GCM.
    token_encryption_key: str = ""

    # --- Fortnox OAuth ---
    fortnox_client_id: str = ""
    fortnox_client_secret: str = ""
    fortnox_tenant_id: str = ""

    # --- CORS ---
    # Comma-separated list of additional allowed origins.
    allowed_origins: str = ""

    # --- Dev mode ---
    # When true, the auth dependency is overridden to return a
    # global provider (no OAuth needed for local development).
    dev_mode: bool = True

    @property
    def cors_origins(self) -> list[str]:
        """Compute the full list of allowed CORS origins."""
        defaults = [
            "https://localhost:3000",
            "https://localhost:3001",
            "http://localhost:3000",
            "http://localhost:3001",
            "null",  # Office taskpane may send origin: null
        ]
        if self.allowed_origins:
            extras = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
            defaults.extend(extras)
        return defaults

    model_config = {
        "env_file": str(Path(__file__).resolve().parent / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for app settings."""
    return Settings()
