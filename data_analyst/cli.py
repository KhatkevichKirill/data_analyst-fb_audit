"""CLI entrypoint for the public Data Analyst starter kit."""
from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import argparse
import subprocess

from config import REPO_ROOT, load_env

load_env()


def _manage(argv: list[str]) -> int:
    from manage import main as manage_main

    old = sys.argv
    sys.argv = ["manage.py", *argv]
    try:
        return manage_main()
    finally:
        sys.argv = old


def cmd_serve(args: argparse.Namespace) -> int:
    host = args.host
    port = args.port
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "web.app:app",
        "--app-dir",
        str(Path(__file__).parent),
        "--host",
        host,
        "--port",
        str(port),
    ]
    return subprocess.call(cmd)


def cmd_repl(_: argparse.Namespace) -> int:
    from analyst import main as repl_main

    return repl_main() or 0


def cmd_init_demo(_: argparse.Namespace) -> int:
    import psycopg2

    schema_path = REPO_ROOT / "schema" / "demo_meta_ads.sql"
    sql = schema_path.read_text()
    conn = psycopg2.connect(
        host=_env("DB_HOST"),
        port=_env("DB_PORT", "5432"),
        dbname=_env("DB_NAME"),
        user=_env("DB_USER"),
        password=_env("DB_PASSWORD"),
    )
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()
    print(f"Applied demo schema: {schema_path}")
    return 0


def _env(key: str, default: str | None = None) -> str:
    import os

    val = os.environ.get(key, default)
    if val is None:
        raise SystemExit(f"Missing required env var: {key}")
    return val


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="data-analyst",
        description="Meta Ads Data Analyst starter kit",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the notebook web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    sub.add_parser("repl", help="run the terminal REPL").set_defaults(func=cmd_repl)
    sub.add_parser("init-demo", help="apply demo analytics schema/seed").set_defaults(
        func=cmd_init_demo
    )

    migrate = sub.add_parser("migrate", help="run analyst_app DB migrations")
    migrate.set_defaults(func=lambda _: _manage(["migrate"]))

    adduser = sub.add_parser("adduser", help="create a web user")
    adduser.add_argument("username")
    adduser.add_argument("--admin", action="store_true")
    adduser.set_defaults(
        func=lambda args: _manage(["adduser", args.username] + (["--admin"] if args.admin else []))
    )

    listusers = sub.add_parser("listusers", help="list web users")
    listusers.set_defaults(func=lambda _: _manage(["listusers"]))

    resetpw = sub.add_parser("resetpw", help="reset a web user's password")
    resetpw.add_argument("username")
    resetpw.set_defaults(func=lambda args: _manage(["resetpw", args.username]))

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
