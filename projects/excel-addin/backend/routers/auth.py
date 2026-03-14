"""OAuth authentication endpoints.

Handles the server-side of the OAuth flow:
1. GET  /api/auth/config/{provider_type} — returns OAuth config for frontend
2. POST /api/auth/callback               — exchanges auth code for tokens
3. POST /api/auth/logout                  — revokes the current session

The flow is provider-agnostic: PROVIDER_CONFIGS maps provider types
to their OAuth endpoints and credentials. Adding Visma or another
provider requires only a new entry in the config dict.
"""

import base64
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_session_jwt, decode_jwt
from config import get_settings
from crypto import encrypt_token
from db import get_db
from models import OAuthToken, Tenant, UserSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

_settings = get_settings()


# --- Provider OAuth configs ---

PROVIDER_CONFIGS: dict[str, dict] = {
    "fortnox": {
        "auth_url": "https://apps.fortnox.se/oauth-v1/auth",
        "token_url": "https://apps.fortnox.se/oauth-v1/token",
        "client_id": lambda: _settings.fortnox_client_id,
        "client_secret": lambda: _settings.fortnox_client_secret,
        "scopes": "companyinformation+salary+bookkeeping+invoice+payment",
    },
    # Future: "visma": { ... }
}


# --- Request/response models ---


class AuthConfigResponse(BaseModel):
    auth_url: str
    client_id: str
    scopes: str
    provider_type: str


class CallbackRequest(BaseModel):
    code: str
    state: str  # Contains provider_type + nonce (e.g. "fortnox:uuid")
    redirect_uri: str


class SessionResponse(BaseModel):
    token: str
    company_name: str | None
    provider_type: str
    expires_in: int


class LogoutRequest(BaseModel):
    """Typed request body for logout (S15: replaces raw dict)."""

    token: str


# --- Endpoints ---


@router.get("/config/{provider_type}")
@limiter.limit("20/minute")
async def get_auth_config(request: Request, provider_type: str) -> AuthConfigResponse:
    """Return OAuth configuration for the frontend dialog.

    The frontend uses this to build the OAuth authorization URL
    without needing to know provider-specific details.
    """
    config = PROVIDER_CONFIGS.get(provider_type)
    if not config:
        # S7: Don't echo the user-supplied provider_type back.
        raise HTTPException(status_code=400, detail="Unknown provider type")

    return AuthConfigResponse(
        auth_url=config["auth_url"],
        client_id=config["client_id"](),
        scopes=config["scopes"],
        provider_type=provider_type,
    )


@router.post("/callback")
@limiter.limit("5/minute")
async def oauth_callback(
    request: Request,
    body: CallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Exchange authorization code for tokens and create a session.

    This is called by the frontend after the OAuth dialog completes.
    The flow:
    1. Validate redirect_uri against whitelist
    2. Exchange the auth code for access + refresh tokens
    3. Find or create the tenant record
    4. Encrypt and store tokens (with tenant_id as AAD)
    5. Create a session and return a JWT
    """
    # S5: State contains "provider_type:nonce" — extract provider_type.
    # Accept both "fortnox" (legacy) and "fortnox:uuid" (new) formats.
    state_parts = body.state.split(":", 1)
    provider_type = state_parts[0]

    config = PROVIDER_CONFIGS.get(provider_type)
    if not config:
        raise HTTPException(status_code=400, detail="Unknown provider")

    # S6: Validate redirect_uri against server-side whitelist.
    if body.redirect_uri not in _settings.redirect_uri_whitelist:
        logger.warning(
            "Rejected redirect_uri not in whitelist: %s", body.redirect_uri
        )
        raise HTTPException(status_code=400, detail="Invalid redirect URI")

    client_id = config["client_id"]()
    client_secret = config["client_secret"]()

    # Exchange code for tokens at the provider's token endpoint.
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    async with httpx.AsyncClient() as http:
        token_response = await http.post(
            config["token_url"],
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
            },
            data={
                "grant_type": "authorization_code",
                "code": body.code,
                "redirect_uri": body.redirect_uri,
            },
        )

    if token_response.status_code != 200:
        # S7: Log raw response server-side, return generic error to client.
        logger.error(
            "Token exchange failed (status=%d): %s",
            token_response.status_code,
            token_response.text,
        )
        raise HTTPException(status_code=502, detail="Token exchange failed")

    token_data = token_response.json()
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]
    expires_in = token_data.get("expires_in", 3600)
    tenant_id_external = token_data.get("tenant_id", "")

    # Find or create tenant.
    result = await db.execute(
        select(Tenant).where(
            Tenant.provider_type == provider_type,
            Tenant.external_tenant_id == tenant_id_external,
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        tenant = Tenant(
            provider_type=provider_type,
            external_tenant_id=tenant_id_external,
        )
        db.add(tenant)
        await db.flush()

    # Upsert encrypted tokens (S16: tenant_id as AAD).
    tenant_id_str = str(tenant.id)
    token_result = await db.execute(
        select(OAuthToken).where(OAuthToken.tenant_id == tenant.id)
    )
    oauth_token = token_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    encrypted_access = encrypt_token(access_token, tenant_id_str)
    encrypted_refresh = encrypt_token(refresh_token, tenant_id_str)

    if oauth_token:
        oauth_token.access_token_encrypted = encrypted_access
        oauth_token.refresh_token_encrypted = encrypted_refresh
        oauth_token.token_expires_at = now + timedelta(seconds=expires_in)
    else:
        oauth_token = OAuthToken(
            tenant_id=tenant.id,
            access_token_encrypted=encrypted_access,
            refresh_token_encrypted=encrypted_refresh,
            token_expires_at=now + timedelta(seconds=expires_in),
        )
        db.add(oauth_token)

    # Create session.
    session_id = str(uuid.uuid4())
    jwt_token = create_session_jwt(str(tenant.id), session_id)

    user_session = UserSession(
        tenant_id=tenant.id,
        jwt_id=session_id,
        expires_at=now + timedelta(hours=24),
    )
    db.add(user_session)

    await db.commit()

    return SessionResponse(
        token=jwt_token,
        company_name=tenant.company_name,
        provider_type=provider_type,
        expires_in=24 * 3600,
    )


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current session.

    SECURITY (S15): Uses the Authorization header to identify the caller
    and only revokes the session belonging to the authenticated JWT.
    Falls back to body-based token for backward compatibility.
    """
    # Prefer Authorization header (S15), fall back to body.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        try:
            body = await request.json()
            token = body.get("token", "")
        except Exception:
            token = ""

    if not token:
        raise HTTPException(status_code=400, detail="Missing token")

    try:
        claims = decode_jwt(token)
    except HTTPException:
        # Token already invalid/expired — nothing to revoke.
        return {"status": "ok"}

    # Only revoke the session matching this JWT's jti.
    result = await db.execute(
        select(UserSession).where(
            UserSession.jwt_id == claims["jti"],
            UserSession.tenant_id == claims["sub"],
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.revoked = True
        await db.commit()

    return {"status": "ok"}
