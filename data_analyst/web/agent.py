"""Async agent loop. Yields events; the route layer persists + streams them."""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import litellm

# Ensure parent dir on sys.path so `tools` (the CLI module) imports cleanly
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tools import TOOL_SPECS, dispatch  # noqa: E402

from .db import pool

PROMPT_PATH = _ROOT / "system_prompt.md"
_schema_crib: str = "(schema not loaded)"

# Production cap: high enough that normal agent loops always complete.
# The benchmark script has its own separate MAX_AGENT_TURNS=6 for controlled comparison.
_MAX_AGENT_TURNS = 20
_MIN_FINAL_LEN = 10  # min chars for a meaningful final answer

# LLM-facing python_exec output budget. The UI/event payload keeps up to 8000
# chars of stdout; the model used to see only the first 500, which caused
# "output is being cut off" retry loops that burned the whole turn budget
# (audit 2026-06-04: 43 of 48 successful python_exec runs exceeded 500 chars).
_PYEXEC_STDOUT_LLM_LIMIT = 3000
# Python puts the exception line at the END of a traceback — show the model
# the tail of stderr, not the head, so it can read `KeyError: 'purchases'`.
_PYEXEC_STDERR_LLM_LIMIT = 700

# After this many consecutive failures of the SAME tool in one cell, append a
# stop-retrying instruction to the tool result fed to the model.
_CONSECUTIVE_TOOL_ERROR_LIMIT = 3
# Inject a wrap-up notice when this many turns remain after the current one.
_TURNS_LEFT_WARNING = 2


def set_schema_crib(crib: str) -> None:
    global _schema_crib
    _schema_crib = crib


def build_system_prompt() -> str:
    # Use literal replacement, not `str.format`: the prompt body contains
    # JSON-style tool-call examples like `python_exec({load: ["q3"], ...})`
    # whose `{load:`/`{code:` etc. would be misread as format slots and
    # raise KeyError. Only the two real placeholders need substituting.
    base = PROMPT_PATH.read_text()
    return (
        base
        .replace("{schema_crib}", _schema_crib)
        .replace("{today_utc}", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    )


@dataclass
class Event:
    type: str
    payload: dict


def _decode_jsonb(v):
    return json.loads(v) if isinstance(v, str) else v


def _tool_result_for_llm(result) -> str:
    """Render a (possibly structured) tool result as a string for LLM history."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        kind = result.get("kind")
        if kind == "chart":
            spec = result.get("vega_lite_spec") or {}
            mark = spec.get("mark")
            if isinstance(mark, dict):
                mark = mark.get("type")
            return (
                f"{result.get('summary', 'chart rendered')} "
                f"(chart rendered: {mark or 'chart'} chart, "
                f"{result.get('row_count', 0)} rows)"
            )
        if kind == "chart_error":
            return f"chart error: {result.get('error', 'unknown error')}"
        if kind == "python_exec":
            stdout = result.get("stdout") or ""
            stderr = result.get("stderr") or ""
            status = result.get("exit_status", "ok")
            parts = [f"python_exec: {status}."]
            if status == "error":
                parts.append(
                    "The sandbox ran your code; the error below was raised by "
                    "the submitted Python code itself (NOT a sandbox/permission "
                    "failure — do not change tools, fix the code)."
                )
            parts.append(
                f"Stdout (first {min(len(stdout), _PYEXEC_STDOUT_LLM_LIMIT)} chars): "
                f"{stdout[:_PYEXEC_STDOUT_LLM_LIMIT]}"
            )
            if len(stdout) > _PYEXEC_STDOUT_LLM_LIMIT:
                parts.append(
                    f"[stdout truncated for the model at {_PYEXEC_STDOUT_LLM_LIMIT} "
                    f"of {len(stdout)} chars — the user already sees the full output "
                    "in the notebook. Do NOT re-run the same code to see more; "
                    "print only key numbers, or summarize.]"
                )
            if stderr:
                parts.append(
                    f"Stderr (last {min(len(stderr), _PYEXEC_STDERR_LLM_LIMIT)} chars): "
                    f"{stderr[-_PYEXEC_STDERR_LLM_LIMIT:]}"
                )
            parts.append(
                f"{len(result.get('plots') or [])} plot(s), "
                f"{len(result.get('vega_specs') or [])} chart spec(s), "
                f"{len(result.get('tables') or [])} table(s)."
            )
            return "\n".join(parts)
        if kind == "python_exec_error":
            return "python_exec error: " + str(result.get("error", "unknown error"))
        if kind == "csv":
            return (
                f"CSV export: {result.get('filename', '')} · "
                f"{result.get('row_count', 0)} rows · "
                f"url: {result.get('url', '')}"
                + (" (truncated)" if result.get("truncated") else "")
            )
        if kind == "csv_error":
            return "export_csv error: " + str(result.get("error", "unknown error"))
        return json.dumps(result)
    return str(result)


def _is_tool_error(result) -> bool:
    """True when a tool result represents a failure (tool-layer or user-code)."""
    if isinstance(result, str):
        s = result.lstrip().lower()
        return (
            s.startswith("error:")
            or s.startswith("sql error")
            or s.startswith("connection error")
            or s.startswith("error reading")
            or (s.startswith("tool ") and "crashed" in s[:60])
        )
    if isinstance(result, dict):
        if str(result.get("kind", "")).endswith("_error"):
            return True
        return result.get("exit_status") in ("error", "timeout")
    return False


def _repeated_error_note(tool_name: str, n: int) -> str:
    return (
        f"\n\n[NOTE: `{tool_name}` has now failed {n} times in a row in this cell. "
        "Stop re-running variations of the same code/query. First inspect the "
        "inputs (after a pandas KeyError, print df.columns.tolist(); after a SQL "
        "error, re-check column names against the schema), or change approach. "
        "If you cannot fix it quickly, summarize the partial findings you "
        "already have as your final answer.]"
    )


async def build_history(notebook_id: int) -> list[dict]:
    """Reconstruct LLM messages from prior done cells in this notebook."""
    messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]
    async with pool().acquire() as conn:
        cells = await conn.fetch(
            "SELECT id, prompt FROM cells WHERE notebook_id = $1 AND status = 'done' "
            "ORDER BY position",
            notebook_id,
        )
        for cell in cells:
            messages.append({"role": "user", "content": cell["prompt"]})
            events = await conn.fetch(
                "SELECT type, payload FROM events WHERE cell_id = $1 ORDER BY seq",
                cell["id"],
            )
            for e in events:
                payload = _decode_jsonb(e["payload"])
                if e["type"] == "assistant_message":
                    msg: dict = {"role": "assistant", "content": payload.get("text") or ""}
                    if payload.get("tool_calls"):
                        msg["tool_calls"] = payload["tool_calls"]
                    messages.append(msg)
                elif e["type"] == "tool_result":
                    messages.append({
                        "role": "tool",
                        "tool_call_id": payload["id"],
                        "content": _tool_result_for_llm(payload["result"]),
                    })
    return messages


def _is_high_stakes_prompt(prompt: str, keywords: list[str] | None) -> bool:
    if not keywords:
        return False
    p = prompt.lower()
    return any(kw.lower() in p for kw in keywords)


async def _run_agent_loop(
    messages: list[dict],
    model: str,
    workspace: Path,
) -> AsyncIterator[tuple[str, Event, dict | None]]:
    """
    Inner agent loop. Yields (phase, event, routing_meta_update).

    routing_meta_update is populated on completion with:
      {"final_text": str, "invalid_json": int, "max_turns_hit": bool, "error": str|None}
    """
    invalid_json_failures = 0
    final_text = ""
    turns = 0
    error = None
    consecutive_tool_errors: dict[str, int] = {}

    while turns < _MAX_AGENT_TURNS:
        turns += 1
        # Wrap-up notice near the cap: without it, models (DeepSeek especially)
        # keep opening new lines of investigation until the hard cap kills the
        # cell with no final answer. Ephemeral — injected into the LLM message
        # list only, not persisted as an event.
        if _MAX_AGENT_TURNS - turns == _TURNS_LEFT_WARNING:
            messages.append({
                "role": "system",
                "content": (
                    f"Turn budget warning: this is turn {turns} of "
                    f"{_MAX_AGENT_TURNS}; only {_MAX_AGENT_TURNS - turns} more "
                    "turns remain after this one. Stop exploring and write your "
                    "final answer summarizing the findings you already have. A "
                    "partial answer is better than running out of turns with no "
                    "answer."
                ),
            })
        try:
            resp = await litellm.acompletion(
                model=model,
                messages=messages,
                tools=TOOL_SPECS,
                tool_choice="auto",
            )
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            yield "error", Event("error", {"error": f"LLM error: {error}"}), None
            return

        msg = resp.choices[0].message
        text = msg.content or ""
        tool_calls = []
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        yield "event", Event("assistant_message", {"text": text, "tool_calls": tool_calls}), None

        asst_msg: dict = {"role": "assistant", "content": text}
        if tool_calls:
            asst_msg["tool_calls"] = tool_calls
        messages.append(asst_msg)

        if not tool_calls:
            final_text = text
            break

        for tc in tool_calls:
            name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError as e:
                invalid_json_failures += 1
                result = f"error: invalid JSON args: {e}"
                yield "event", Event("tool_call", {"id": tc["id"], "name": name, "args_raw": raw_args}), None
            else:
                yield "event", Event("tool_call", {"id": tc["id"], "name": name, "args": args}), None
                result = await asyncio.to_thread(
                    dispatch, name, args, workspace=workspace
                )

            yield "event", Event("tool_result", {"id": tc["id"], "result": result}), None
            content = _tool_result_for_llm(result)
            # Repeated-error guard: after N consecutive failures of the same
            # tool, tell the model to stop retrying and summarize. Appended to
            # the LLM-facing content only — the persisted event keeps the raw
            # result.
            if _is_tool_error(result):
                n = consecutive_tool_errors.get(name, 0) + 1
                consecutive_tool_errors[name] = n
                if n >= _CONSECUTIVE_TOOL_ERROR_LIMIT:
                    content += _repeated_error_note(name, n)
            else:
                consecutive_tool_errors[name] = 0
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": content,
            })
    else:
        error = "max_turns_exceeded"

    yield "done", Event("done", {}), {
        "final_text": final_text,
        "invalid_json": invalid_json_failures,
        "max_turns_hit": error == "max_turns_exceeded",
        "error": error,
    }


async def run_cell(
    notebook_id: int,
    prompt: str,
    model: str,
    workspace: Path,
    profile: str = "deepseek",
    routing_enabled: bool = False,
    escalation_model: str | None = None,
    escalation_profile: str | None = None,
    high_stakes: bool = False,
    high_stakes_keywords: list[str] | None = None,
) -> AsyncIterator[Event]:
    """Run an agent loop for one cell. Yields events as they occur.

    When routing_enabled=True and escalation triggers fire, escalates to
    escalation_model, preserving successful tool results from the primary run.
    All routing decisions are recorded via routing_info events.
    """

    # ── Pre-routing check ───────────────────────────────────────────────────
    pre_route_escalate = (
        routing_enabled and
        escalation_model and
        (high_stakes or _is_high_stakes_prompt(prompt, high_stakes_keywords))
    )

    if pre_route_escalate:
        yield Event("routing_info", {
            "requested_profile": profile,
            "actual_profile": escalation_profile or escalation_model,
            "routing_enabled": True,
            "escalated": True,
            "escalation_reason": "high_stakes_pre_route",
            "phase": "pre_route",
        })
        effective_model = escalation_model
        actual_profile = escalation_profile or escalation_model
    else:
        effective_model = model
        actual_profile = profile

    # ── Primary (or pre-routed) run ─────────────────────────────────────────
    messages = await build_history(notebook_id)
    messages.append({"role": "user", "content": prompt})

    # Track valid exchanges (assistant_msg + tool_results) for escalation reuse
    primary_valid_exchanges: list[tuple[dict, list[dict]]] = []
    _current_asst_msg: dict | None = None
    _current_tool_results: list[dict] = []

    primary_meta: dict | None = None

    async for phase, event, meta in _run_agent_loop(messages, effective_model, workspace):
        if phase == "done":
            primary_meta = meta
            # Don't yield done yet; routing may need to add escalation
            break
        elif phase == "error":
            # If routing enabled and primary errored, attempt escalation
            if routing_enabled and not pre_route_escalate and escalation_model:
                primary_meta = {"final_text": "", "invalid_json": 0, "max_turns_hit": False,
                                 "error": event.payload.get("error", "provider_error")}
                break
            yield event
            return
        else:
            yield event
            # Track for escalation: collect assistant/tool messages
            if event.type == "assistant_message" and event.payload.get("tool_calls"):
                if _current_asst_msg is not None and _current_tool_results:
                    primary_valid_exchanges.append((_current_asst_msg, list(_current_tool_results)))
                _current_asst_msg = {
                    "role": "assistant",
                    "content": event.payload.get("text") or "",
                    "tool_calls": event.payload["tool_calls"],
                }
                _current_tool_results = []
            elif event.type == "tool_result":
                if _current_asst_msg is not None:
                    _current_tool_results.append({
                        "role": "tool",
                        "tool_call_id": event.payload["id"],
                        "content": _tool_result_for_llm(event.payload["result"]),
                    })

    if _current_asst_msg is not None and _current_tool_results:
        primary_valid_exchanges.append((_current_asst_msg, list(_current_tool_results)))

    if primary_meta is None:
        primary_meta = {"final_text": "", "invalid_json": 0, "max_turns_hit": False, "error": None}

    # ── Post-run escalation check ───────────────────────────────────────────
    should_escalate = False
    escalation_reason: str | None = None

    if routing_enabled and not pre_route_escalate and escalation_model:
        ft = primary_meta.get("final_text", "")
        ij = primary_meta.get("invalid_json", 0)
        mt = primary_meta.get("max_turns_hit", False)
        err = primary_meta.get("error")

        if err and err != "max_turns_exceeded":
            should_escalate = True
            escalation_reason = f"provider_error:{err}"
        elif mt:
            should_escalate = True
            escalation_reason = "primary_max_turns"
        elif ij >= 2:
            should_escalate = True
            escalation_reason = f"invalid_json_failures:{ij}"
        elif not ft or len(ft.strip()) <= _MIN_FINAL_LEN:
            should_escalate = True
            escalation_reason = "empty_or_short_final_answer"

    if should_escalate and escalation_model:
        actual_profile = escalation_profile or escalation_model
        yield Event("routing_info", {
            "requested_profile": profile,
            "actual_profile": actual_profile,
            "routing_enabled": True,
            "escalated": True,
            "escalation_reason": escalation_reason,
            "phase": "post_primary_escalation",
        })

        # Build escalation context: notebook history + user prompt + primary successes
        esc_messages = await build_history(notebook_id)
        esc_messages.append({"role": "user", "content": prompt})
        for asst_msg, tool_results in primary_valid_exchanges:
            esc_messages.append(asst_msg)
            esc_messages.extend(tool_results)

        esc_meta: dict | None = None
        async for phase, event, meta in _run_agent_loop(esc_messages, escalation_model, workspace):
            if phase == "done":
                esc_meta = meta
                break
            elif phase == "error":
                yield event
                return
            else:
                yield event

        if esc_meta is None:
            esc_meta = {}
        final_meta = esc_meta
    else:
        actual_profile = escalation_profile if pre_route_escalate else profile
        escalation_reason = "high_stakes_pre_route" if pre_route_escalate else None
        final_meta = primary_meta

    yield Event("done", {
        "actual_profile": actual_profile,
        "escalated": pre_route_escalate or should_escalate,
        "escalation_reason": escalation_reason,
        "max_turns_hit": final_meta.get("max_turns_hit", False),
        "final_text": final_meta.get("final_text", ""),
    })
