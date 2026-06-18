"""asyncpg pool + idempotent migration runner."""
from __future__ import annotations

import os
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    _pool = await asyncpg.create_pool(
        host=os.environ["APP_DB_HOST"],
        port=int(os.environ.get("APP_DB_PORT", "5432")),
        database=os.environ["APP_DB_NAME"],
        user=os.environ["APP_DB_USER"],
        password=os.environ["APP_DB_PASSWORD"],
        ssl=False,  # local loopback to docker postgres — no TLS
        min_size=1,
        max_size=10,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool


async def run_migrations() -> list[str]:
    """Apply any .sql files in migrations/ that haven't been applied yet."""
    p = await init_pool()
    applied: list[str] = []
    async with p.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        done = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}
        for sql_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if sql_path.name in done:
                continue
            sql = sql_path.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1) "
                    "ON CONFLICT (filename) DO NOTHING",
                    sql_path.name,
                )
            applied.append(sql_path.name)
    return applied
