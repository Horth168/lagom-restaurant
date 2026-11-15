"""Password hashing and login tokens."""
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_settings
from app.models.base import utcnow

_hasher = PasswordHasher()  # Argon2id with safe defaults
ALGORITHM = "HS256"

# Used to make login timing the same whether or not the email exists
_DUMMY_HASH = _hasher.hash("lagom-dummy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("Password must be at least 10 characters")
    if password.lower() == password or password.upper() == password:
        problems.append("Use both upper- and lower-case letters")
    if not any(c.isdigit() for c in password):
        problems.append("Include at least one number")
    return problems


def create_access_token(user_id: int, token_version: int, minutes: int | None = None) -> str:
    s = get_settings()
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes or s.access_token_minutes)).timestamp()),
        "typ": "staff",
    }
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "staff":
        return None
    return payload
