"""bcrypt password hashing + cookie session management."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import HTTPException, Request

from .db import pool

SESSION_COOKIE = "analyst_sess"
SESSION_TTL_DAYS = 7
COOKIE_PATH = "/"  # broad path so the cookie covers /analyst/* AND / (dashboard)
_BCRYPT_MAX = 72  # bcrypt input limit (bytes, not chars)


def hash_password(plain: str) -> str:
    pw = plain.encode("utf-8")[:_BCRYPT_MAX]
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:_BCRYPT_MAX], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


async def authenticate(username: str, password: str) -> Optional[dict]:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, password_hash, is_active, is_admin "
            "FROM users WHERE username = $1",
            username,
        )
    if not row or not row["is_active"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return dict(row)


async def create_session(user_id: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    async with pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES ($1, $2, $3)",
            token, user_id, expires,
        )
    return token, expires


async def destroy_session(token: str) -> None:
    async with pool().acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE token = $1", token)


async def lookup_session(token: str) -> Optional[dict]:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(
            """SELECT u.id, u.username, u.is_admin
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token = $1 AND s.expires_at > now() AND u.is_active""",
            token,
        )
    return dict(row) if row else None


async def current_user(request: Request) -> dict:
    """FastAPI dependency: returns the logged-in user or raises 401."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not logged in")
    user = await lookup_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="session expired")
    return user
