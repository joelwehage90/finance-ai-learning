"""Database models for multi-tenant OAuth storage.

Three tables:
- tenants: one row per connected accounting company
- oauth_tokens: encrypted access/refresh tokens per tenant
- user_sessions: JWT session tracking with revocation support
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _utcnow() -> datetime:
    """Return timezone-aware UTC now (S18: replaces deprecated utcnow)."""
    return datetime.now(timezone.utc)


class Tenant(Base):
    """A connected accounting company (e.g. a Fortnox tenant)."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    provider_type: Mapped[str] = mapped_column(String(50))  # "fortnox", "visma"
    external_tenant_id: Mapped[str] = mapped_column(String(255))
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )

    tokens: Mapped[list["OAuthToken"]] = relationship(back_populates="tenant")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="tenant")

    __table_args__ = (
        Index(
            "ix_tenant_provider_external",
            "provider_type",
            "external_tenant_id",
            unique=True,
        ),
    )


class OAuthToken(Base):
    """Encrypted OAuth tokens for a tenant."""

    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"),
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="tokens")


class UserSession(Base):
    """Tracks active JWT sessions for revocation support."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"),
    )
    jwt_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    # S14: Index on expires_at for efficient session cleanup queries.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True,
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="sessions")
