"""Token encryption using AES-256-GCM.

Uses envelope encryption: a master key (from env) encrypts data
directly. In production, consider using a KMS-backed approach.

The master key should be a 32-byte key, base64-encoded, stored
in the TOKEN_ENCRYPTION_KEY environment variable.

Generate a key with:
    python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
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
                "TOKEN_ENCRYPTION_KEY environment variable not set. "
                "Generate one with: python3 -c \"import base64, os; "
                "print(base64.b64encode(os.urandom(32)).decode())\""
            )
        _MASTER_KEY = base64.b64decode(key_b64)
        if len(_MASTER_KEY) != 32:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be exactly 32 bytes")
    return _MASTER_KEY


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string.

    Returns base64-encoded nonce + ciphertext.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a token string from base64-encoded nonce + ciphertext."""
    key = _get_key()
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ct = raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode()
