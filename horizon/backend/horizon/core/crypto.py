"""Primitives cryptographiques : hachage des mots de passe, TOTP (RFC 6238),
chiffrement des secrets au repos et signatures HMAC."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.fernet import Fernet

from horizon.core.config import get_settings

# --- mots de passe (scrypt, bibliothèque standard) ---------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:  # noqa: BLE001
        return False


# --- jetons ------------------------------------------------------------------

def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _derive(purpose: str) -> bytes:
    return hashlib.sha256(f"{get_settings().secret_key}|{purpose}".encode()).digest()


def fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive("secrets-at-rest")))


def encrypt(value: str) -> str:
    return fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return fernet().decrypt(value.encode()).decode()


def sign(purpose: str, message: str) -> str:
    return hmac.new(_derive(purpose), message.encode(), hashlib.sha256).hexdigest()


def verify_signature(purpose: str, message: str, signature: str) -> bool:
    return hmac.compare_digest(sign(purpose, message), signature)


def hmac_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# --- TOTP RFC 6238 (SHA-1, 6 chiffres, pas de 30 s) -------------------------

def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_at(secret_b32: str, for_time: float, step: int = 30, digits: int = 6) -> str:
    padded = secret_b32 + "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int(for_time // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def totp_now(secret_b32: str) -> str:
    return totp_at(secret_b32, time.time())


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    now = time.time()
    code = (code or "").strip()
    return any(hmac.compare_digest(totp_at(secret_b32, now + i * 30), code) for i in range(-window, window + 1))
