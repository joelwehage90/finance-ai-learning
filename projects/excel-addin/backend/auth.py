"""JWT-based session authentication for the Excel add-in API.

Provides JWT creation/verification and the get_current_provider
FastAPI dependency that resolves an authenticated request into
an AccountingProvider instance.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from crypto import decrypt_token, encrypt_token
from db import get_db
from models import OAuthToken, Tenant, UserSession
from providers.base import AccountingProvider

_settings = get_settings()
JWT_SECRET = _settings.jwt_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = _settings.jwt_expiry_hours


def create_session_jwt(tenant_id: str, session_id: str) -> str:
    """Create a JWT for an authenticated session.

    Args:
        tenant_id: UUID string of the tenant.
        session_id: UUID string of the session (becomes the 'jti' claim).

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": tenant_id,
        "jti": session_id,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token")


async def get_current_provider(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AccountingProvider:
    """FastAPI dependency: extract JWT, load tenant, return provider.

    This is the key integration point. Every authenticated endpoint
    gets an AccountingProvider without knowing which accounting
    system is behind it.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = auth_header[7:]
    claims = decode_jwt(token)

    # Verify session is not revoked.
    session_result = await db.execute(
        select(UserSession).where(
            UserSession.jwt_id == claims["jti"],
            UserSession.revoked == False,  # noqa: E712
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=401, detail="Session revoked")

    # Load tenant and tokens.
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == session.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Tenant not found")

    token_result = await db.execute(
        select(OAuthToken).where(OAuthToken.tenant_id == tenant.id)
    )
    oauth_token = token_result.scalar_one_or_none()
    if not oauth_token:
        raise HTTPException(status_code=401, detail="No tokens found")

    # Decrypt tokens.
    access_token = decrypt_token(oauth_token.access_token_encrypted)
    refresh_token = decrypt_token(oauth_token.refresh_token_encrypted)

    # Create provider based on tenant type, with a callback that
    # persists rotated tokens to the database.
    return _create_provider(tenant, access_token, refresh_token, db)


def _create_provider(
    tenant: Tenant,
    access_token: str,
    refresh_token: str,
    db: AsyncSession,
) -> AccountingProvider:
    """Factory function: create the right provider for a tenant.

    Wires up an on_token_refresh callback that encrypts and persists
    rotated tokens to the database. This is critical for Fortnox which
    rotates refresh tokens on every use.
    """

    async def _persist_tokens(
        new_access: str, new_refresh: str, expires_in: int
    ) -> None:
        """Callback invoked when the provider refreshes its tokens."""
        result = await db.execute(
            select(OAuthToken).where(OAuthToken.tenant_id == tenant.id)
        )
        token_row = result.scalar_one_or_none()
        if token_row:
            token_row.access_token_encrypted = encrypt_token(new_access)
            token_row.refresh_token_encrypted = encrypt_token(new_refresh)
            token_row.token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=expires_in
            )
            await db.commit()

    if tenant.provider_type == "fortnox":
        from providers.fortnox import FortnoxProvider

        return FortnoxProvider(
            client_id=_settings.fortnox_client_id,
            client_secret=_settings.fortnox_client_secret,
            tenant_id=tenant.external_tenant_id,
            access_token=access_token,
            refresh_token=refresh_token,
            on_token_refresh=_persist_tokens,
        )
    # Future: elif tenant.provider_type == "visma": ...
    raise ValueError(f"Unknown provider type: {tenant.provider_type}")
