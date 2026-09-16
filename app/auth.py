import base64
import hashlib
import hmac
import os
from secrets import token_bytes
from typing import Optional

from fastapi import HTTPException, Request


ADMIN_PASSWORD_HASH_ENV = "BATTLE_MARCH_ADMIN_PASSWORD_HASH"
SESSION_SECRET_ENV = "BATTLE_MARCH_SESSION_SECRET"
SESSION_KEY = "admin_authenticated"
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    encoded_salt = base64.urlsafe_b64encode(salt).decode("ascii")
    encoded_digest = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{PASSWORD_HASH_ALGORITHM}${PASSWORD_HASH_ITERATIONS}${encoded_salt}${encoded_digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, encoded_salt, encoded_digest = password_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
    except (ValueError, TypeError):
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def authenticate_admin(password: str) -> bool:
    password_hash = os.environ.get(ADMIN_PASSWORD_HASH_ENV)
    if password_hash is None:
        return False
    return verify_password(password, password_hash)


def session_secret() -> str:
    secret = os.environ.get(SESSION_SECRET_ENV)
    if secret:
        return secret
    if os.environ.get("BATTLE_MARCH_ENV") == "production":
        raise RuntimeError(f"{SESSION_SECRET_ENV} must be set in production.")
    return "development-session-secret-change-before-deployment"


def secure_cookies_enabled() -> bool:
    explicit_value = os.environ.get("BATTLE_MARCH_SECURE_COOKIES")
    if explicit_value is not None:
        return explicit_value.lower() in {"1", "true", "yes", "on"}
    return os.environ.get("BATTLE_MARCH_ENV") == "production"


def require_admin(request: Request) -> None:
    if request.session.get(SESSION_KEY) is True:
        return
    raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
