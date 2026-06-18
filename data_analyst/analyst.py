"""data_analyst — REPL agent over a read-only Postgres warehouse.

Run: data-analyst repl
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from rich.console import Console
from rich.markdown import Markdown

import litellm

from config import load_env, public_plot_root, public_plot_url_base, workspace_root
from tools import TOOL_SPECS, dispatch

load_env()

# litellm's moonshot provider reads MOONSHOT_API_KEY, but the key in .env is named
# KIMI_API_KEY (native Moonshot global-platform key, api.moonshot.ai — verified
# 2026-06-04). Alias it so profile resolution stays env-var driven; never log values.
if os.environ.get("KIMI_API_KEY") and not os.environ.get("MOONSHOT_API_KEY"):
    os.environ["MOONSHOT_API_KEY"] = os.environ["KIMI_API_KEY"]

# Visible profiles are the ones shown in the notebook model selector. Everything
# with "hidden": True is kept resolvable (for escalation, the benchmark runner, and
# replay of historical cells) but does NOT appear in the UI. After the 2026-05 model
# bake-off we kept exactly three: DeepSeek (fast, non-thinking — the default),
# DeepSeek in thinking/reasoning mode (via the deepseek-reasoner endpoint), and Haiku.
# 2026-06-04: three evaluation candidates added to the selector for Kirill's manual
# testing — OpenAI o3, Gemini 2.5 Pro (via OpenRouter; direct Google is geo-blocked
# from this VPS), and Kimi K2.6 (native Moonshot, see KIMI_API_KEY alias above).
PROFILES = {
    # ── Active (shown in the selector) ──────────────────────────────────────
    "deepseek": {
        "model": "deepseek/deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "provider": "deepseek",
        "role": "primary",
        "label": "DeepSeek",
    },
    "deepseek_thinking": {
        # deepseek-reasoner = DeepSeek's thinking/reasoning mode. litellm's static
        # model map flags it as no-function-calling, but the live API DOES support
        # tools (verified 2026-06-03); the agent ignores the returned
        # reasoning_content and rebuilds history without it, so multi-turn is safe.
        "model": "deepseek/deepseek-reasoner",
        "api_key_env": "DEEPSEEK_API_KEY",
        "provider": "deepseek",
        "role": "primary",
        "label": "DeepSeek (Thinking)",
        "thinking": True,
    },
    "haiku": {
        "model": "anthropic/claude-haiku-4-5-20251001",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "role": "primary",
        "label": "Haiku",
    },
    "openai_o3": {
        # Reasoning model on Chat Completions; tool calls verified live 2026-06-04.
        # litellm converts max_tokens → max_completion_tokens for o-series.
        "model": "openai/o3",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
        "role": "primary",
        "label": "OpenAI o3",
        "thinking": True,
    },
    "openrouter_gemini_25_pro": {
        # Via OpenRouter — direct Google AI Studio is geo-blocked from this VPS
        # (same as gemini_25_flash below). Tool calls verified live 2026-06-04.
        "model": "openrouter/google/gemini-2.5-pro",
        "api_key_env": "OPENROUTER_API_KEY",
        "provider": "openrouter",
        "role": "primary",
        "label": "Gemini 2.5 Pro",
        "thinking": True,
    },
    "kimi_k26": {
        # Native Moonshot global platform (api.moonshot.ai), NOT OpenRouter — the
        # configured KIMI_API_KEY is a Moonshot key (kimi-k2.6 listed in /v1/models,
        # verified 2026-06-04). litellm reads MOONSHOT_API_KEY (aliased at module
        # load above). kimi-k2.6 is a reasoning model; litellm injects a placeholder
        # reasoning_content on replayed tool-call turns — multi-turn verified live.
        "model": "moonshot/kimi-k2.6",
        "api_key_env": "KIMI_API_KEY",
        "provider": "moonshot",
        "role": "primary",
        "label": "Kimi K2.6",
        "thinking": True,
    },
    # ── Hidden (kept for escalation / benchmark / cell replay) ──────────────
    "openai_gpt41_mini": {
        "model": "openai/gpt-4.1-mini",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
        "role": "primary",
        "hidden": True,
    },
    "gemini_25_flash": {
        "model": "gemini/gemini-2.5-flash",
        "api_key_env": "GEMINI_API_KEY",
        "provider": "google",
        "role": "primary",
        "disabled": True,
        "hidden": True,
        "status_reason": "geo-blocked from this VPS (FAILED_PRECONDITION); use openrouter_gemini_25_flash",
    },
    "openrouter_gemini_25_flash": {
        "model": "openrouter/google/gemini-2.5-flash",
        "api_key_env": "OPENROUTER_API_KEY",
        "provider": "openrouter",
        "role": "primary",
        "hidden": True,
    },
    "openrouter_anthropic_haiku45": {
        "model": "openrouter/anthropic/claude-haiku-4.5",
        "api_key_env": "OPENROUTER_API_KEY",
        "provider": "openrouter",
        "role": "primary",
        "hidden": True,
    },
    "anthropic_sonnet4": {
        "model": "anthropic/claude-sonnet-4-6",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "role": "escalation",
        "hidden": True,
    },
    "openai_gpt41": {
        "model": "openai/gpt-4.1",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
        "role": "escalation",
        "hidden": True,
    },
    "anthropic": {
        "model": "anthropic/claude-haiku-4-5-20251001",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
        "role": "experimental",
        "hidden": True,
    },
    "openrouter_deepseek": {
        "model": "openrouter/deepseek/deepseek-chat",
        "api_key_env": "OPENROUTER_API_KEY",
        "provider": "openrouter",
        "role": "experimental",
        "hidden": True,
    },
    # ── Local (NO-GO on current VPS — context too small, CPU too slow) ──────
    "ollama_qwen25_3b": {
        "model": "ollama/qwen2.5:3b-instruct-q4_K_M",
        "api_key_env": None,
        "provider": "ollama",
        "role": "experimental",
        "hidden": True,
    },
    "ollama_llama32_3b": {
        "model": "ollama/llama3.2:3b-instruct-q4_K_M",
        "api_key_env": None,
        "provider": "ollama",
        "role": "experimental",
        "hidden": True,
    },
}


# ── Central profile resolver ─────────────────────────────────────────────────

def list_model_profiles() -> list[dict]:
    """Return safe metadata for all profiles. Never returns key values."""
    results = []
    for name, p in PROFILES.items():
        key_env = p.get("api_key_env")
        disabled = p.get("disabled", False)
        key_present = bool(os.environ.get(key_env)) if key_env else True
        available = key_present and not disabled
        entry: dict = {
            "profile": name,
            "model": p["model"],
            "provider": p.get("provider", "unknown"),
            "api_key_env": key_env,
            "key_configured": key_present,
            "available": available,
            "role": p.get("role", "experimental"),
            "disabled": disabled,
            "hidden": p.get("hidden", False),
            "label": p.get("label", name),
            "thinking": p.get("thinking", False),
        }
        if p.get("status_reason"):
            entry["status_reason"] = p["status_reason"]
        results.append(entry)
    return results


def resolve_model_profile(profile_name: str) -> dict | None:
    """Return the profile dict for profile_name, or None if unknown."""
    return PROFILES.get(profile_name)


def default_web_profile() -> str:
    """Return the profile name from WEB_MODEL env, falling back to 'deepseek'."""
    return os.environ.get("WEB_MODEL", "deepseek")


def validate_profile_available(profile_name: str) -> tuple[bool, str]:
    """Return (available, reason_if_not_available)."""
    p = PROFILES.get(profile_name)
    if p is None:
        return False, f"unknown profile '{profile_name}'"
    if p.get("disabled"):
        reason = p.get("status_reason") or f"profile '{profile_name}' is disabled"
        return False, reason
    key_env = p.get("api_key_env")
    if key_env and not os.environ.get(key_env):
        return False, f"missing env var {key_env} for profile '{profile_name}'"
    return True, ""

PROMPT_PATH = Path(__file__).parent / "system_prompt.md"
console = Console()


def load_schema_crib() -> str:
    """List tables + columns the analyst role can SELECT."""
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
    except psycopg2.Error as e:
        return f"(schema unavailable: {e})"
    try:
        with conn.cursor() as cur:
            # pg_class / pg_attribute is the only source that includes
            # materialized views (relkind='m'); information_schema.columns omits them.
            cur.execute("""
                SELECT c.relname AS table_name,
                       a.attname AS column_name,
                       format_type(a.atttypid, a.atttypmod) AS data_type,
                       c.relkind
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('r','v','m','p')
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                  AND has_table_privilege(current_user, c.oid, 'SELECT')
                ORDER BY c.relname, a.attnum
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return "(no tables visible)"

    by_table: dict[str, tuple[str, list[tuple[str, str]]]] = {}
    kind_label = {"r": "table", "v": "view", "m": "matview", "p": "partition"}
    for tbl, col, dtype, kind in rows:
        if tbl not in by_table:
            by_table[tbl] = (kind_label.get(kind, kind), [])
        by_table[tbl][1].append((col, dtype))
    lines = []
    for tbl in sorted(by_table):
        kind, cols = by_table[tbl]
        col_str = ", ".join(f"{c}:{t}" for c, t in cols)
        lines.append(f"- **{tbl}** ({kind}) — {col_str}")
    return "\n".join(lines)


def build_system_prompt() -> str:
    # Use literal replacement, not str.format: the prompt body contains
    # JSON-style examples like `python_exec({load: ["q3"], ...})` whose
    # braces would be misread as format slots and raise KeyError.
    base = PROMPT_PATH.read_text()
    return (
        base
        .replace("{schema_crib}", load_schema_crib())
        .replace("{today_utc}", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    )


def make_session_dir() -> Path:
    sid = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    root = workspace_root()
    plots_root = public_plot_root()
    workspace = root / sid
    public_plots = plots_root / sid
    workspace.mkdir(parents=True, exist_ok=False)
    public_plots.mkdir(parents=True, exist_ok=False)
    (workspace / "plots").symlink_to(public_plots)
    return workspace


def _serializable(obj):
    """Coerce a LiteLLM message to JSON-serializable dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return str(obj)


def main() -> int:
    profile_name = os.environ.get("LLM_PROFILE", "deepseek")
    ok, reason = validate_profile_available(profile_name)
    if not ok:
        console.print(f"[red]{reason}. Available: {list(PROFILES)}[/red]")
        return 1
    profile = PROFILES[profile_name]
    model = profile["model"]

    workspace = make_session_dir()
    transcript = workspace / "transcript.jsonl"
    plot_url_base = f"{public_plot_url_base()}/{workspace.name}"

    console.print(f"[bold cyan]data_analyst[/bold cyan]  model=[green]{model}[/green]  session=[yellow]{workspace.name}[/yellow]")
    console.print(f"[dim]workspace: {workspace}[/dim]")
    console.print(f"[dim]plots URL: {plot_url_base}/[/dim]")
    console.print("[dim]Type a question and press Enter. Ctrl-D to exit.[/dim]\n")

    sys_prompt = build_system_prompt()
    messages: list[dict] = [{"role": "system", "content": sys_prompt}]

    def append(msg: dict) -> None:
        messages.append(msg)
        with transcript.open("a") as f:
            f.write(json.dumps(msg, default=str) + "\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]exit[/dim]")
            return 0
        if not line:
            continue
        append({"role": "user", "content": line})

        # Inner agent loop — keep calling until model returns no tool calls
        while True:
            try:
                resp = litellm.completion(
                    model=model,
                    messages=messages,
                    tools=TOOL_SPECS,
                    tool_choice="auto",
                )
            except Exception as e:
                console.print(f"[red]LLM error: {type(e).__name__}: {e}[/red]")
                break

            msg = resp.choices[0].message
            asst: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                asst["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            append(asst)

            if not msg.tool_calls:
                if msg.content:
                    console.print(Markdown(msg.content))
                break

            for tc in msg.tool_calls:
                name = tc.function.name
                raw_args = tc.function.arguments
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError as e:
                    result = f"error: invalid JSON args ({e}): {raw_args[:200]}"
                else:
                    preview = json.dumps(args, default=str)
                    if len(preview) > 200:
                        preview = preview[:200] + "…"
                    console.print(f"[dim]→ {name}({preview})[/dim]")
                    result = dispatch(name, args, workspace=workspace)
                append({"role": "tool", "tool_call_id": tc.id, "content": result})


if __name__ == "__main__":
    sys.exit(main() or 0)
