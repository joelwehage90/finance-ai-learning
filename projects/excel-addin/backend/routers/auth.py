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
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_session_jwt, decode_jwt
from config import get_settings
from crypto import encrypt_token
from db import get_db
from models import OAuthToken, Tenant, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])

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
    state: str  # Contains provider_type
    redirect_uri: str


class SessionResponse(BaseModel):
    token: str
    company_name: str | None
    provider_type: str
    expires_in: int


# --- Endpoints ---


@router.get("/config/{provider_type}")
async def get_auth_config(provider_type: str) -> AuthConfigResponse:
    """Return OAuth configuration for the frontend dialog.

    The frontend uses this to build the OAuth authorization URL
    without needing to know provider-specific details.
    """
    config = PROVIDER_CONFIGS.get(provider_type)
    if not config:
        raise HTTPException(
            status_code=400, detail=f"Unknown provider: {provider_type}",
        )

    return AuthConfigResponse(
        auth_url=config["auth_url"],
        client_id=config["client_id"](),
        scopes=config["scopes"],
        provider_type=provider_type,
    )


@router.post("/callback")
async def oauth_callback(
    body: CallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Exchange authorization code for tokens and create a session.

    This is called by the frontend after the OAuth dialog completes.
    The flow:
    1. Exchange the auth code for access + refresh tokens
    2. Find or create the tenant record
    3. Encrypt and store tokens
    4. Create a session and return a JWT
    """
    provider_type = body.state
    config = PROVIDER_CONFIGS.get(provider_type)
    if not config:
        raise HTTPException(status_code=400, detail="Unknown provider")

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
        raise HTTPException(
            status_code=502,
            detail=f"Token exchange failed: {token_response.text}",
        )

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

    # Upsert encrypted tokens.
    token_result = await db.execute(
        select(OAuthToken).where(OAuthToken.tenant_id == tenant.id)
    )
    oauth_token = token_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token)

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
    body: dict,
    db: AsyncSession = Depends(get_db),
):
    """Revoke the current session.

    Expects { "token": "<jwt>" } in the body.
    """
    token = body.get("token", "")
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")

    try:
        claims = decode_jwt(token)
    except HTTPException:
        # Token already invalid/expired — nothing to revoke.
        return {"status": "ok"}

    result = await db.execute(
        select(UserSession).where(UserSession.jwt_id == claims["jti"])
    )
    session = result.scalar_one_or_none()
    if session:
        session.revoked = True
        await db.commit()

    return {"status": "ok"}
