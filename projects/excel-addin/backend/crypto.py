"""Token encryption using AES-256-GCM.

Uses envelope encryption: a master key (from env) encrypts data
directly. In production, consider using a KMS-backed approach.

The master key should be a 32-byte key, base64-encoded, stored
in the TOKEN_ENCRYPTION_KEY environment variable.

Generate a key with:
    python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"

SECURITY (S16): AES-GCM uses Associated Authenticated Data (AAD) to
bind each ciphertext to its owning tenant_id. This prevents an attacker
with DB write access from moving encrypted tokens between tenants.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MASTER_KEY: bytes | None = None


def _get_key() -> bytes:
    """Load and validate the master encryption key from settings/env."""
    global _MASTER_KEY
    if _MASTER_KEY is None:
        from config import get_settings

        key_b64 = get_settings().token_encryption_key
        if not key_b64:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY not set — "
                "see .env.example for generation instructions"
            )
        _MASTER_KEY = base64.b64decode(key_b64)
        if len(_MASTER_KEY) != 32:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be exactly 32 bytes")
    return _MASTER_KEY


def encrypt_token(plaintext: str, tenant_id: str | None = None) -> str:
    """Encrypt a token string.

    Args:
        plaintext: The token value to encrypt.
        tenant_id: Optional tenant UUID string used as AAD to bind the
            ciphertext to a specific tenant. Pass None for backward
            compatibility with tokens encrypted before AAD was added.

    Returns:
        Base64-encoded nonce + ciphertext.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    aad = tenant_id.encode() if tenant_id else None
    ct = aesgcm.encrypt(nonce, plaintext.encode(), aad)
    return base64.b64encode(nonce + ct).decode()


def decrypt_token(encrypted: str, tenant_id: str | None = None) -> str:
    """Decrypt a token string from base64-encoded nonce + ciphertext.

    Args:
        encrypted: Base64-encoded nonce + ciphertext.
        tenant_id: Must match the AAD used during encryption. Pass None
            to decrypt tokens that were encrypted before AAD was added.

    Returns:
        Decrypted token string.
    """
    key = _get_key()
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ct = raw[12:]
    aesgcm = AESGCM(key)
    aad = tenant_id.encode() if tenant_id else None
    return aesgcm.decrypt(nonce, ct, aad).decode()
