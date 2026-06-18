"""Central configuration for the public Data Analyst starter kit."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent

if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))


def load_env() -> None:
    """Load environment from DATA_ANALYST_ENV or repo-root .env."""
    env_file = os.environ.get("DATA_ANALYST_ENV")
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(REPO_ROOT / ".env", override=False)


def url_prefix() -> str:
    """Optional mount prefix, e.g. '/analyst' behind nginx."""
    return os.environ.get("URL_PREFIX", "").rstrip("/")


def prefixed(path: str) -> str:
    prefix = url_prefix()
    if not path.startswith("/"):
        path = "/" + path
    return f"{prefix}{path}" if prefix else path


def knowledge_dir() -> Path:
    raw = os.environ.get("KNOWLEDGE_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return PACKAGE_DIR / "knowledge"


def sandbox_python() -> Path:
    raw = os.environ.get("SANDBOX_PYTHON")
    if raw:
        return Path(raw).expanduser().resolve()
    return REPO_ROOT / ".sandbox_venv" / "bin" / "python"


def python_exec_enabled() -> bool:
    return os.environ.get("PYTHON_EXEC_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def workspace_root() -> Path:
    raw = os.environ.get("WORKSPACE_ROOT", str(REPO_ROOT / "workspace"))
    return Path(raw).expanduser().resolve()


def public_plot_root() -> Path:
    raw = os.environ.get("PUBLIC_PLOT_ROOT", str(workspace_root() / "plots"))
    return Path(raw).expanduser().resolve()


def public_plot_url_base() -> str:
    return os.environ.get("PUBLIC_PLOT_URL_BASE", prefixed("/plots")).rstrip("/")
