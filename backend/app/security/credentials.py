"""Password hashing, session JWTs, API tokens and secret encryption."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet

from app.config import get_settings

_hasher = PasswordHasher()
API_TOKEN_PREFIX = "bdna_"
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        # Still spend comparable time so missing users are not distinguishable by timing.
        _hasher.hash("timing-equaliser-password")
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# --- Session tokens --------------------------------------------------------------------------
def issue_session_jwt(user_id: uuid.UUID, session_id: uuid.UUID, expires_at: dt.datetime) -> str:
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": "session",
        "iat": int(dt.datetime.now(dt.UTC).timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm="HS256")


@dataclass(frozen=True)
class SessionClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID


def decode_session_jwt(token: str) -> SessionClaims | None:
    try:
        data = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"], options={"require": ["exp", "sub", "sid"]})
        if data.get("typ") != "session":
            return None
        return SessionClaims(uuid.UUID(data["sub"]), uuid.UUID(data["sid"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


# --- API tokens ------------------------------------------------------------------------------
def generate_api_token() -> tuple[str, str, str]:
    """Return (plaintext, prefix, sha256). Plaintext is shown to the user exactly once."""
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    plaintext = f"{API_TOKEN_PREFIX}{prefix}_{secret}"
    return plaintext, prefix, hash_api_token(plaintext)


def hash_api_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def is_api_token(value: str) -> bool:
    return value.startswith(API_TOKEN_PREFIX)


# --- Signed storage URLs (local storage adapter) -----------------------------------------------
def sign_payload(payload: str) -> str:
    mac = hmac.new(get_settings().secret_key.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def verify_signature(payload: str, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(payload), signature)


# --- Secret encryption at rest -----------------------------------------------------------------
def _fernet() -> Fernet:
    s = get_settings()
    key = s.encryption_key
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(("fernet:" + s.secret_key).encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
