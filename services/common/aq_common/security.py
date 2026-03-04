from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

import jwt
from passlib.context import CryptContext

from aq_common.settings import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_api_key(raw_key: str) -> str:
    return pwd_context.hash(raw_key)


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    return pwd_context.verify(raw_key, hashed_key)


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

