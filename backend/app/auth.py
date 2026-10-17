"""Password hashing and cookie sessions, stdlib only.

Passwords: scrypt with a per-user salt. Sessions: a random token in an httpOnly, SameSite=Lax
cookie; only its sha256 is stored, so a leaked database can't be replayed as live sessions.
"""

import base64
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuthSession, User

SESSION_COOKIE = "pitchlab_session"
SESSION_TTL = timedelta(days=30)
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"  # true behind HTTPS
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


def utcnow() -> datetime:
    # naive UTC: SQLite doesn't keep timezones, so store everything the same way
    return datetime.now(UTC).replace(tzinfo=None)


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                   n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, base64.b64decode(digest))


# verified against when the email doesn't exist, so response time doesn't reveal which emails do
DUMMY_HASH = hash_password(secrets.token_hex(16))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))  # tidy expired
    db.add(AuthSession(user_id=user.id, token_hash=_token_hash(token),
                       expires_at=utcnow() + SESSION_TTL))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()),
                        httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/")


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """The signed-in user, or None for anonymous visitors."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if session is None or session.expires_at < utcnow():
        return None
    return session.user


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(401, "Sign in to do that")
    return user
