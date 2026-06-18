"""manage.py — admin CLI for data_analyst web app.

Usage:
    data-analyst <command> [args]
"""
from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from config import load_env

load_env()

# Make `web` importable
sys.path.insert(0, str(Path(__file__).parent))

from web.auth import hash_password
from web.db import close_pool, init_pool, run_migrations


async def cmd_migrate() -> int:
    applied = await run_migrations()
    if applied:
        print("applied:", ", ".join(applied))
    else:
        print("no pending migrations")
    await close_pool()
    return 0


async def cmd_adduser(username: str, is_admin_flag: bool) -> int:
    pw = getpass.getpass(f"Password for {username}: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw != pw2:
        print("error: passwords don't match", file=sys.stderr)
        return 1
    if len(pw) < 8:
        print("error: password too short (min 8)", file=sys.stderr)
        return 1
    p = await init_pool()
    try:
        async with p.acquire() as conn:
            count = await conn.fetchval("SELECT count(*) FROM users")
            admin = is_admin_flag or count == 0  # first user gets admin
            try:
                uid = await conn.fetchval(
                    "INSERT INTO users (username, password_hash, is_admin) "
                    "VALUES ($1, $2, $3) RETURNING id",
                    username, hash_password(pw), admin,
                )
            except Exception as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
        print(f"created user id={uid} username={username} is_admin={admin}")
    finally:
        await close_pool()
    return 0


async def cmd_listusers() -> int:
    p = await init_pool()
    try:
        async with p.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, username, is_active, is_admin, created_at "
                "FROM users ORDER BY id"
            )
    finally:
        await close_pool()
    if not rows:
        print("(no users)")
        return 0
    for r in rows:
        print(
            f"  {r['id']:>3}  {r['username']:<20}"
            f"  active={r['is_active']}  admin={r['is_admin']}"
            f"  created={r['created_at']:%Y-%m-%d}"
        )
    return 0


async def cmd_resetpw(username: str) -> int:
    pw = getpass.getpass(f"New password for {username}: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw != pw2:
        print("error: passwords don't match", file=sys.stderr)
        return 1
    if len(pw) < 8:
        print("error: password too short (min 8)", file=sys.stderr)
        return 1
    p = await init_pool()
    try:
        async with p.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET password_hash = $1 WHERE username = $2",
                hash_password(pw), username,
            )
        # asyncpg execute returns "UPDATE n"
        n = int(result.rsplit(" ", 1)[-1])
        if n == 0:
            print(f"error: user '{username}' not found", file=sys.stderr)
            return 1
        print(f"password updated for {username}")
    finally:
        await close_pool()
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == "migrate":
        return asyncio.run(cmd_migrate())
    if cmd == "adduser" and args:
        return asyncio.run(cmd_adduser(args[0], "--admin" in args[1:]))
    if cmd == "listusers":
        return asyncio.run(cmd_listusers())
    if cmd == "resetpw" and args:
        return asyncio.run(cmd_resetpw(args[0]))
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
