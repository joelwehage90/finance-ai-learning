"""Application configuration — Pydantic settings with env/.env support.

All configuration is read from environment variables (or a .env file).
Import ``settings`` from this module to access config values.

Security: dev_mode defaults to False (fail-secure). Production secrets
(jwt_secret, token_encryption_key) are validated at startup when
dev_mode is off — see ``validate_production_settings()``.
"""

import base64
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

_INSECURE_JWT_DEFAULT = "dev-secret-change-in-production"


class Settings(BaseSettings):
    """Central config for the Excel add-in backend."""

    # --- Database ---
    database_url: str = "postgresql+asyncpg://localhost/excel_addin"

    # --- JWT ---
    jwt_secret: str = _INSECURE_JWT_DEFAULT
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

    # --- Redirect URI whitelist ---
    # Comma-separated list of allowed OAuth redirect URIs.
    # In production, set to your deployed callback URL(s).
    allowed_redirect_uris: str = ""

    # --- Dev mode ---
    # SECURITY: Defaults to False (fail-secure). Set DEV_MODE=true
    # explicitly in your local .env for development.
    dev_mode: bool = False

    @property
    def cors_origins(self) -> list[str]:
        """Compute the full list of allowed CORS origins."""
        defaults = [
            "https://localhost:3000",
            "https://localhost:3001",
            "http://localhost:3000",
            "http://localhost:3001",
            # Office taskpane in desktop Excel may send origin: null
            # because it runs in a local webview (not a normal browser tab).
            # This is required for the add-in to function in Excel desktop.
            "null",
        ]
        if self.allowed_origins:
            extras = [o.strip() for o in self.allowed_origins.split(",") if o.strip()]
            defaults.extend(extras)
        return defaults

    @property
    def redirect_uri_whitelist(self) -> list[str]:
        """Allowed OAuth redirect URIs (always includes localhost dev URIs)."""
        defaults = [
            "https://localhost:3000/callback.html",
            "https://localhost:3001/callback.html",
        ]
        if self.allowed_redirect_uris:
            extras = [u.strip() for u in self.allowed_redirect_uris.split(",") if u.strip()]
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


def validate_production_settings(settings: Settings) -> None:
    """Validate that production-critical settings are properly configured.

    Called during app startup (lifespan). Raises RuntimeError if
    dev_mode is off and required secrets are missing or insecure.
    """
    if settings.dev_mode:
        return  # In dev mode, no strict validation needed.

    errors: list[str] = []

    if not settings.jwt_secret or settings.jwt_secret == _INSECURE_JWT_DEFAULT:
        errors.append(
            "JWT_SECRET must be set to a strong random value in production. "
            "Generate with: python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    if not settings.token_encryption_key:
        errors.append(
            "TOKEN_ENCRYPTION_KEY must be set in production. "
            "Generate with: python3 -c \"import base64,os; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    else:
        # Validate key length eagerly instead of at first encrypt call.
        try:
            key_bytes = base64.b64decode(settings.token_encryption_key)
            if len(key_bytes) != 32:
                errors.append(
                    f"TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(key_bytes)}"
                )
        except Exception:
            errors.append("TOKEN_ENCRYPTION_KEY is not valid base64")

    if errors:
        raise RuntimeError(
            "Production configuration errors:\n  - " + "\n  - ".join(errors)
        )
