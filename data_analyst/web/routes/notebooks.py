"""Notebook CRUD + SSE-streamed cell execution + sharing."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..agent import run_cell, _MAX_AGENT_TURNS, _MIN_FINAL_LEN
from ..auth import current_user
from ..db import pool

from config import workspace_root as _workspace_root
import sys as _sys
from pathlib import Path as _Path
_analyst_root = _Path(__file__).parent.parent.parent
if str(_analyst_root) not in _sys.path:
    _sys.path.insert(0, str(_analyst_root))
from analyst import (
    PROFILES as _PROFILES,
    list_model_profiles as _list_model_profiles,
    default_web_profile as _default_web_profile,
    validate_profile_available as _validate_profile_available,
    resolve_model_profile as _resolve_model_profile,
)


def _get_web_model_and_profile(override: str | None = None) -> tuple[str, str]:
    """Return (litellm_model_str, profile_name) for a given override or WEB_MODEL default."""
    name = override if override else _default_web_profile()
    profile = _resolve_model_profile(name)
    if profile:
        return profile["model"], name
    # Legacy fallback: raw LiteLLM string (no profile metadata)
    return name, name


def _routing_env() -> dict:
    """Read routing control env vars. Returns safe defaults."""
    routing_enabled = os.environ.get("ROUTING_ENABLED", "false").lower() == "true"
    esc_profile_name = os.environ.get("ESCALATION_MODEL_PROFILE", "openai_gpt41")
    esc_profile = _resolve_model_profile(esc_profile_name)
    esc_model = esc_profile["model"] if esc_profile else None
    keywords = [
        k.strip()
        for k in os.environ.get("HIGH_STAKES_KEYWORDS", "").split(",")
        if k.strip()
    ]
    return {
        "routing_enabled": routing_enabled,
        "escalation_profile_name": esc_profile_name,
        "escalation_model": esc_model,
        "high_stakes_keywords": keywords or None,
    }


# ── Routers ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/notebooks", tags=["notebooks"])

# Second router at /api level (model profiles endpoint)
config_router = APIRouter(prefix="/api", tags=["config"])


# ── Model profiles endpoint ──────────────────────────────────────────────────

@config_router.get("/model-profiles")
async def get_model_profiles(user: dict = Depends(current_user)):
    """Return safe metadata for all configured model profiles.

    Never returns API key values — only whether each key is configured.
    """
    profiles = _list_model_profiles()
    renv = _routing_env()
    default_name = _default_web_profile()
    return {
        "profiles": profiles,
        "default_profile": default_name,
        "routing_enabled": renv["routing_enabled"],
        "primary_profile_env": os.environ.get("PRIMARY_MODEL_PROFILE", default_name),
        "escalation_profile_env": renv["escalation_profile_name"],
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class NewNotebook(BaseModel):
    title: str | None = None


class NewCell(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    model_profile: str | None = None
    high_stakes: bool = False


class ShareRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    permission: str = "view"


_VALID_PERMISSIONS = ("view", "edit")


# ── Access helpers ────────────────────────────────────────────────────────────

# Notebook-level access values exposed in API/UI responses:
#   owner  — notebook creator, full control
#   editor — shared user with permission='edit' (view + add/run new cells)
#   shared — shared user with permission='view' (read-only)

async def _get_notebook_with_access(conn, notebook_id: int, user_id: int):
    """Return (notebook_row, access_type) or (None, None) if inaccessible.

    access_type is one of 'owner', 'editor', or 'shared'.
    """
    nb = await conn.fetchrow(
        "SELECT n.id, n.title, n.workspace_dir, n.user_id, u.username AS owner_username "
        "FROM notebooks n JOIN users u ON u.id = n.user_id "
        "WHERE n.id = $1 AND n.archived_at IS NULL",
        notebook_id,
    )
    if not nb:
        return None, None
    if nb["user_id"] == user_id:
        return nb, "owner"
    share = await conn.fetchrow(
        "SELECT permission FROM notebook_shares "
        "WHERE notebook_id = $1 AND user_id = $2 AND revoked_at IS NULL",
        notebook_id, user_id,
    )
    if share:
        return nb, ("editor" if share["permission"] == "edit" else "shared")
    return None, None


# ── List / create notebooks ───────────────────────────────────────────────────

@router.get("")
async def list_notebooks(user: dict = Depends(current_user)):
    async with pool().acquire() as conn:
        owned = await conn.fetch(
            "SELECT n.id, n.title, n.created_at, n.updated_at, "
            "u.username AS owner_username, 'owner' AS access "
            "FROM notebooks n JOIN users u ON u.id = n.user_id "
            "WHERE n.user_id = $1 AND n.archived_at IS NULL ORDER BY n.updated_at DESC",
            user["id"],
        )
        shared = await conn.fetch(
            "SELECT n.id, n.title, n.created_at, n.updated_at, "
            "u.username AS owner_username, "
            "CASE WHEN ns.permission = 'edit' THEN 'editor' ELSE 'shared' END AS access "
            "FROM notebook_shares ns "
            "JOIN notebooks n ON n.id = ns.notebook_id "
            "JOIN users u ON u.id = n.user_id "
            "WHERE ns.user_id = $1 AND ns.revoked_at IS NULL AND n.archived_at IS NULL "
            "ORDER BY n.updated_at DESC",
            user["id"],
        )
    return [dict(r) for r in owned] + [dict(r) for r in shared]


@router.post("")
async def create_notebook(body: NewNotebook, user: dict = Depends(current_user)):
    title = (body.title or "Untitled").strip() or "Untitled"
    ws_root = _workspace_root() / "web" / str(user["id"])
    ws_root.mkdir(parents=True, exist_ok=True)
    async with pool().acquire() as conn:
        nb_id = await conn.fetchval(
            "INSERT INTO notebooks (user_id, title, workspace_dir) "
            "VALUES ($1, $2, '') RETURNING id",
            user["id"], title,
        )
        wdir = ws_root / str(nb_id)
        (wdir / "plots").mkdir(parents=True, exist_ok=True)
        (wdir / "results").mkdir(parents=True, exist_ok=True)
        (wdir / "outputs").mkdir(parents=True, exist_ok=True)
        await conn.execute(
            "UPDATE notebooks SET workspace_dir = $1 WHERE id = $2",
            str(wdir), nb_id,
        )
    return {"id": nb_id, "title": title}


# ── Get / archive notebook ────────────────────────────────────────────────────

@router.get("/{notebook_id}")
async def get_notebook(notebook_id: int, user: dict = Depends(current_user)):
    async with pool().acquire() as conn:
        nb, access = await _get_notebook_with_access(conn, notebook_id, user["id"])
        if not nb:
            raise HTTPException(404, "notebook not found")
        cells = await conn.fetch(
            "SELECT c.id, c.position, c.prompt, c.status, c.created_at, c.completed_at, "
            "c.model_profile, c.actual_model_profile, c.routing_enabled, c.escalated, "
            "c.escalation_reason, c.created_by_user_id, u.username AS created_by_username "
            "FROM cells c LEFT JOIN users u ON u.id = c.created_by_user_id "
            "WHERE c.notebook_id = $1 ORDER BY c.position",
            notebook_id,
        )
        out_cells = []
        for c in cells:
            evs = await conn.fetch(
                "SELECT type, payload FROM events WHERE cell_id = $1 ORDER BY seq",
                c["id"],
            )
            out_cells.append({
                **dict(c),
                "events": [
                    {"type": e["type"], "payload": json.loads(e["payload"]) if isinstance(e["payload"], str) else e["payload"]}
                    for e in evs
                ],
            })
    return {
        "id": nb["id"],
        "title": nb["title"],
        "access": access,
        "owner_username": nb["owner_username"],
        "cells": out_cells,
    }


# ── Markdown export ───────────────────────────────────────────────────────────

def _fence(content: str, lang: str = "") -> str:
    """Wrap content in a fenced code block, escaping any internal backtick fences."""
    text = content if isinstance(content, str) else str(content)
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}{lang}\n{text}\n{fence}"


def _compact_json(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        return str(obj)


def _render_tool_result_md(result) -> list[str]:
    """Render a persisted tool_result payload as Markdown lines."""
    lines: list[str] = []
    if isinstance(result, str):
        lines.append("**Tool result:**")
        lines.append("")
        lines.append(result if result.strip() else "_(empty)_")
        return lines

    if not isinstance(result, dict):
        lines.append("**Tool result:**")
        lines.append("")
        lines.append(str(result))
        return lines

    kind = result.get("kind")
    if kind == "chart":
        lines.append("**Tool result — chart:**")
        lines.append("")
        if result.get("summary"):
            lines.append(result["summary"])
        lines.append(
            f"- rows: {result.get('row_count', 0)} · truncated: {bool(result.get('truncated'))}"
        )
        lines.append("")
        lines.append("Vega-Lite spec:")
        lines.append(_fence(_compact_json(result.get("vega_lite_spec") or {}), "json"))
    elif kind == "python_exec":
        lines.append(f"**Tool result — python_exec ({result.get('exit_status', 'ok')}):**")
        lines.append("")
        if result.get("summary"):
            lines.append(result["summary"])
            lines.append("")
        if (result.get("stdout") or "").strip():
            lines.append("stdout:")
            lines.append(_fence(result["stdout"]))
        if (result.get("stderr") or "").strip():
            lines.append("stderr:")
            lines.append(_fence(result["stderr"]))
        for t in (result.get("tables") or []):
            title = t.get("title") or "table"
            cols = t.get("columns") or []
            rows = t.get("rows") or []
            lines.append(f"table — {title} ({len(rows)} rows × {len(cols)} cols):")
            lines.append(_fence(_compact_json({"columns": cols, "rows": rows}), "json"))
        for spec in (result.get("vega_specs") or []):
            lines.append("chart spec:")
            lines.append(_fence(_compact_json(spec), "json"))
        for p in (result.get("plots") or []):
            lines.append(f"- plot: {p.get('filename', '')} → {p.get('url', '')}")
    elif kind == "csv":
        lines.append("**Tool result — csv:**")
        lines.append("")
        lines.append(f"- filename: {result.get('filename', '')}")
        lines.append(f"- url: {result.get('url', '')}")
        lines.append(f"- rows: {result.get('row_count', 0)} · truncated: {bool(result.get('truncated'))}")
        cols = result.get("columns") or []
        if cols:
            lines.append(f"- columns: {', '.join(str(c) for c in cols)}")
    elif kind in ("chart_error", "python_exec_error", "csv_error"):
        lines.append(f"**Tool result — {kind}:**")
        lines.append("")
        lines.append(_fence(str(result.get("error") or result.get("summary") or "error")))
    else:
        lines.append("**Tool result:**")
        lines.append("")
        lines.append(_fence(_compact_json(result), "json"))
    return lines


def _build_notebook_markdown(meta: dict, cells: list[dict]) -> str:
    """Build a full Markdown transcript from persisted cells + events.

    Includes only visible persisted events (assistant messages, tool calls,
    tool results, errors, routing metadata) — never hidden provider reasoning.
    """
    out: list[str] = []
    out.append(f"# {meta['title']}")
    out.append("")
    out.append(f"- **Notebook id:** {meta['id']}")
    out.append(f"- **Owner:** {meta['owner_username']}")
    out.append(f"- **Exported by:** {meta['exporter']}")
    out.append(f"- **Export timestamp (UTC):** {meta['exported_at']}")
    out.append("")
    out.append(
        "_Transcript of persisted, visible notebook events (prompts, assistant "
        "messages, tool calls, tool results, errors, model metadata). Hidden "
        "provider reasoning is not persisted and is not included._"
    )
    out.append("")

    for c in cells:
        out.append("---")
        out.append("")
        out.append(f"## Cell [{c['position'] + 1}] · id {c['id']} · {c['status']}")
        out.append("")
        out.append(f"- **Author:** {c.get('created_by_username') or 'unknown'}")
        if c.get("created_at"):
            out.append(f"- **Created:** {c['created_at']}")
        if c.get("completed_at"):
            out.append(f"- **Completed:** {c['completed_at']}")
        req = c.get("model_profile")
        act = c.get("actual_model_profile")
        if req or act:
            out.append(f"- **Requested model:** {req or '(default)'} · **Actual model:** {act or req or '(unknown)'}")
        if c.get("routing_enabled") is not None:
            out.append(f"- **Routing enabled:** {bool(c.get('routing_enabled'))}")
        if c.get("escalated"):
            out.append(f"- **Escalated:** true · reason: {c.get('escalation_reason') or '(none)'}")
        out.append("")
        out.append("### Prompt")
        out.append("")
        out.append(_fence(c["prompt"]))
        out.append("")

        events = c.get("events") or []
        if events:
            out.append("### Transcript")
            out.append("")
        for ev in events:
            etype = ev["type"]
            payload = ev["payload"]
            if etype == "assistant_message":
                text = (payload.get("text") or "").strip()
                if text:
                    out.append("**Assistant:**")
                    out.append("")
                    out.append(text)
                    out.append("")
            elif etype == "tool_call":
                name = payload.get("name", "tool")
                if "args" in payload:
                    out.append(f"**Tool call:** `{name}`")
                    out.append("")
                    out.append(_fence(json.dumps(payload.get("args"), ensure_ascii=False, indent=2, default=str), "json"))
                else:
                    out.append(f"**Tool call:** `{name}` (raw / unparsed args)")
                    out.append("")
                    out.append(_fence(payload.get("args_raw") or ""))
                out.append("")
            elif etype == "tool_result":
                out.extend(_render_tool_result_md(payload.get("result")))
                out.append("")
            elif etype == "routing_info":
                if payload.get("escalated"):
                    out.append(
                        f"**Routing:** escalated {payload.get('requested_profile', '?')} → "
                        f"{payload.get('actual_profile', '?')} "
                        f"({payload.get('escalation_reason', '')})"
                    )
                else:
                    out.append(f"**Routing:** model {payload.get('actual_profile') or payload.get('requested_profile', '')}")
                out.append("")
            elif etype == "error":
                out.append("**Error:**")
                out.append("")
                out.append(_fence(str(payload.get("error") or payload)))
                out.append("")
            # 'done' carries only completion metadata already shown in the header.

    out.append("")
    return "\n".join(out)


@router.get("/{notebook_id}/export")
async def export_notebook(
    notebook_id: int, format: str = "markdown", user: dict = Depends(current_user)
):
    """Download a full Markdown transcript of the notebook.

    Accessible to owner, editor, and read-only shared users. Built entirely
    from persisted cells + events — never re-runs any LLM/SQL/Python/chart/CSV.
    """
    if format != "markdown":
        raise HTTPException(400, "unsupported format: only 'markdown' is supported")

    async with pool().acquire() as conn:
        nb, access = await _get_notebook_with_access(conn, notebook_id, user["id"])
        if not nb:
            raise HTTPException(404, "notebook not found")
        cells = await conn.fetch(
            "SELECT c.id, c.position, c.prompt, c.status, c.created_at, c.completed_at, "
            "c.model_profile, c.actual_model_profile, c.routing_enabled, c.escalated, "
            "c.escalation_reason, u.username AS created_by_username "
            "FROM cells c LEFT JOIN users u ON u.id = c.created_by_user_id "
            "WHERE c.notebook_id = $1 ORDER BY c.position",
            notebook_id,
        )
        out_cells = []
        for c in cells:
            evs = await conn.fetch(
                "SELECT type, payload FROM events WHERE cell_id = $1 ORDER BY seq",
                c["id"],
            )
            out_cells.append({
                **dict(c),
                "events": [
                    {"type": e["type"], "payload": json.loads(e["payload"]) if isinstance(e["payload"], str) else e["payload"]}
                    for e in evs
                ],
            })

    now = datetime.now(timezone.utc)
    md = _build_notebook_markdown(
        {
            "id": nb["id"],
            "title": nb["title"],
            "owner_username": nb["owner_username"],
            "exporter": user["username"],
            "exported_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        },
        out_cells,
    )

    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "-", (nb["title"] or "notebook")).strip("-") or "notebook"
    filename = f"{safe_title}-{now.strftime('%Y%m%d-%H%M%S')}.md"

    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{notebook_id}")
async def delete_notebook(notebook_id: int, user: dict = Depends(current_user)):
    async with pool().acquire() as conn:
        result = await conn.execute(
            "UPDATE notebooks SET archived_at = now() "
            "WHERE id = $1 AND user_id = $2 AND archived_at IS NULL",
            notebook_id, user["id"],
        )
    if result == "UPDATE 0":
        raise HTTPException(403, "not the owner")
    return {"ok": True}


# ── Cell operations (owner only) ──────────────────────────────────────────────

@router.delete("/{notebook_id}/cells/{cell_id}")
async def delete_cell(
    notebook_id: int, cell_id: int, user: dict = Depends(current_user)
):
    """Delete this cell and all subsequent cells (keeps context coherent)."""
    async with pool().acquire() as conn:
        cell = await conn.fetchrow(
            "SELECT c.position FROM cells c "
            "JOIN notebooks n ON n.id = c.notebook_id "
            "WHERE c.id = $1 AND c.notebook_id = $2 AND n.user_id = $3",
            cell_id, notebook_id, user["id"],
        )
        if not cell:
            raise HTTPException(404, "cell not found")
        await conn.execute(
            "DELETE FROM cells WHERE notebook_id = $1 AND position >= $2",
            notebook_id, cell["position"],
        )
    return {"ok": True}


@router.post("/{notebook_id}/cells")
async def create_cell(
    notebook_id: int, body: NewCell, user: dict = Depends(current_user)
):
    """Create a cell, run the agent, and stream events back as SSE."""

    # ── Resolve model profile ────────────────────────────────────────────────
    if body.model_profile is not None:
        ok, reason = _validate_profile_available(body.model_profile)
        if not ok:
            raise HTTPException(400, reason)
        profile_name = body.model_profile
    else:
        profile_name = _default_web_profile()
        ok, _ = _validate_profile_available(profile_name)
        if not ok:
            # Default profile unavailable: fall back to deepseek
            profile_name = "deepseek"

    model, _ = _get_web_model_and_profile(profile_name)

    # ── Routing env ──────────────────────────────────────────────────────────
    renv = _routing_env()
    routing_enabled = renv["routing_enabled"]
    esc_model = renv["escalation_model"]
    esc_profile_name = renv["escalation_profile_name"]
    keywords = renv["high_stakes_keywords"]

    # ── Access check + execution lock + cell creation ────────────────────────
    # Owners and editors may add cells; read-only viewers may not. A
    # notebook-scoped row lock (SELECT ... FOR UPDATE) serializes concurrent
    # create-cell requests so only one cell can be running/pending at a time.
    async with pool().acquire() as conn:
        async with conn.transaction():
            nb = await conn.fetchrow(
                "SELECT id, workspace_dir, user_id FROM notebooks "
                "WHERE id = $1 AND archived_at IS NULL FOR UPDATE",
                notebook_id,
            )
            if not nb:
                raise HTTPException(404, "notebook not found")

            if nb["user_id"] != user["id"]:
                share = await conn.fetchrow(
                    "SELECT permission FROM notebook_shares "
                    "WHERE notebook_id = $1 AND user_id = $2 AND revoked_at IS NULL",
                    notebook_id, user["id"],
                )
                if not share:
                    raise HTTPException(404, "notebook not found")
                if share["permission"] != "edit":
                    raise HTTPException(403, "read-only share: you cannot run cells in this notebook")

            # Sequential execution lock: one running/pending cell per notebook.
            busy = await conn.fetchval(
                "SELECT 1 FROM cells WHERE notebook_id = $1 "
                "AND status IN ('running', 'pending') LIMIT 1",
                notebook_id,
            )
            if busy:
                raise HTTPException(
                    409, "another cell is already running in this notebook; wait for it to finish"
                )

            pos = await conn.fetchval(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM cells WHERE notebook_id = $1",
                notebook_id,
            )
            cell_id = await conn.fetchval(
                "INSERT INTO cells "
                "(notebook_id, position, prompt, status, model_profile, routing_enabled, created_by_user_id) "
                "VALUES ($1, $2, $3, 'running', $4, $5, $6) RETURNING id",
                notebook_id, pos, body.prompt, profile_name, routing_enabled, user["id"],
            )

    workspace = Path(nb["workspace_dir"])

    async def stream():
        seq = 0
        meta = {
            "cell_id": cell_id,
            "position": pos,
            "model_profile": profile_name,
            "routing_enabled": routing_enabled,
        }
        yield f"event: cell_created\ndata: {json.dumps(meta)}\n\n"

        # Track routing outcome for DB update
        actual_profile = profile_name
        escalated = False
        escalation_reason = None
        _max_turns_hit = False
        _final_text = ""

        try:
            async for event in run_cell(
                notebook_id,
                body.prompt,
                model=model,
                workspace=workspace,
                profile=profile_name,
                routing_enabled=routing_enabled,
                escalation_model=esc_model if routing_enabled else None,
                escalation_profile=esc_profile_name if routing_enabled else None,
                high_stakes=body.high_stakes,
                high_stakes_keywords=keywords if routing_enabled else None,
            ):
                if event.type == "done":
                    actual_profile = event.payload.get("actual_profile", profile_name)
                    escalated = event.payload.get("escalated", False)
                    escalation_reason = event.payload.get("escalation_reason")
                    _max_turns_hit = event.payload.get("max_turns_hit", False)
                    _final_text = event.payload.get("final_text", "")

                async with pool().acquire() as conn:
                    await conn.execute(
                        "INSERT INTO events (cell_id, seq, type, payload) "
                        "VALUES ($1, $2, $3, $4::jsonb)",
                        cell_id, seq, event.type, json.dumps(event.payload),
                    )
                yield f"event: {event.type}\ndata: {json.dumps(event.payload)}\n\n"
                seq += 1

            # Determine final cell status.
            # Max-turns with no meaningful answer must not be saved as 'done'.
            if _max_turns_hit and not escalated and len((_final_text or "").strip()) <= _MIN_FINAL_LEN:
                final_status = "error"
                err_payload = {"error": f"max_turns_exceeded ({_MAX_AGENT_TURNS}) with no final answer"}
                async with pool().acquire() as conn:
                    await conn.execute(
                        "INSERT INTO events (cell_id, seq, type, payload) "
                        "VALUES ($1, $2, $3, $4::jsonb)",
                        cell_id, seq, "error", json.dumps(err_payload),
                    )
                yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"
            else:
                final_status = "done"

            async with pool().acquire() as conn:
                await conn.execute(
                    "UPDATE cells SET status=$1, completed_at=now(), "
                    "actual_model_profile=$2, escalated=$3, escalation_reason=$4 "
                    "WHERE id=$5",
                    final_status, actual_profile, escalated, escalation_reason, cell_id,
                )
                await conn.execute(
                    "UPDATE notebooks SET updated_at=now() WHERE id=$1",
                    notebook_id,
                )
        except asyncio.CancelledError:
            async with pool().acquire() as conn:
                await conn.execute(
                    "UPDATE cells SET status='cancelled', completed_at=now() WHERE id=$1",
                    cell_id,
                )
            raise
        except Exception as e:
            err = {"error": f"{type(e).__name__}: {e}"}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"
            async with pool().acquire() as conn:
                await conn.execute(
                    "UPDATE cells SET status='error', completed_at=now() WHERE id=$1",
                    cell_id,
                )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Share management (owner only) ─────────────────────────────────────────────

@router.get("/{notebook_id}/shares")
async def list_shares(notebook_id: int, user: dict = Depends(current_user)):
    async with pool().acquire() as conn:
        nb = await conn.fetchrow(
            "SELECT id FROM notebooks WHERE id = $1 AND user_id = $2 AND archived_at IS NULL",
            notebook_id, user["id"],
        )
        if not nb:
            raise HTTPException(404, "notebook not found")
        rows = await conn.fetch(
            "SELECT u.id AS user_id, u.username, ns.permission, ns.created_at "
            "FROM notebook_shares ns JOIN users u ON u.id = ns.user_id "
            "WHERE ns.notebook_id = $1 AND ns.revoked_at IS NULL "
            "ORDER BY ns.created_at",
            notebook_id,
        )
    return [dict(r) for r in rows]


@router.post("/{notebook_id}/shares")
async def add_share(
    notebook_id: int, body: ShareRequest, user: dict = Depends(current_user)
):
    permission = (body.permission or "view").strip().lower()
    if permission not in _VALID_PERMISSIONS:
        raise HTTPException(400, f"invalid permission: must be one of {', '.join(_VALID_PERMISSIONS)}")

    async with pool().acquire() as conn:
        nb = await conn.fetchrow(
            "SELECT id FROM notebooks WHERE id = $1 AND user_id = $2 AND archived_at IS NULL",
            notebook_id, user["id"],
        )
        if not nb:
            raise HTTPException(404, "notebook not found")

        target = await conn.fetchrow(
            "SELECT id, username FROM users WHERE username = $1 AND is_active = true",
            body.username,
        )
        if not target:
            raise HTTPException(400, "user not found")
        if target["id"] == user["id"]:
            raise HTTPException(400, "cannot share with yourself")

        await conn.execute(
            """
            INSERT INTO notebook_shares (notebook_id, user_id, permission, created_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (notebook_id, user_id) DO UPDATE
              SET revoked_at = NULL, created_at = now(),
                  permission = EXCLUDED.permission, created_by = EXCLUDED.created_by
            """,
            notebook_id, target["id"], permission, user["id"],
        )
    return {"ok": True, "shared_with": target["username"], "permission": permission}


@router.delete("/{notebook_id}/shares/{target_user_id}")
async def revoke_share(
    notebook_id: int, target_user_id: int, user: dict = Depends(current_user)
):
    async with pool().acquire() as conn:
        nb = await conn.fetchrow(
            "SELECT id FROM notebooks WHERE id = $1 AND user_id = $2 AND archived_at IS NULL",
            notebook_id, user["id"],
        )
        if not nb:
            raise HTTPException(404, "notebook not found")
        await conn.execute(
            "UPDATE notebook_shares SET revoked_at = now() "
            "WHERE notebook_id = $1 AND user_id = $2 AND revoked_at IS NULL",
            notebook_id, target_user_id,
        )
    return {"ok": True}


# ── Fork / copy ───────────────────────────────────────────────────────────────

@router.post("/{notebook_id}/fork")
async def fork_notebook(notebook_id: int, user: dict = Depends(current_user)):
    async with pool().acquire() as conn:
        src_nb, access = await _get_notebook_with_access(conn, notebook_id, user["id"])
        if not src_nb:
            raise HTTPException(404, "notebook not found")

        new_title = f"Copy of {src_nb['title']}"
        ws_root = _workspace_root() / "web" / str(user["id"])
        ws_root.mkdir(parents=True, exist_ok=True)

        new_nb_id = await conn.fetchval(
            "INSERT INTO notebooks (user_id, title, workspace_dir) "
            "VALUES ($1, $2, '') RETURNING id",
            user["id"], new_title,
        )
        new_wdir = ws_root / str(new_nb_id)
        (new_wdir / "plots").mkdir(parents=True, exist_ok=True)
        (new_wdir / "results").mkdir(parents=True, exist_ok=True)
        (new_wdir / "outputs").mkdir(parents=True, exist_ok=True)
        await conn.execute(
            "UPDATE notebooks SET workspace_dir = $1 WHERE id = $2",
            str(new_wdir), new_nb_id,
        )

        cells = await conn.fetch(
            "SELECT id, position, prompt, status, created_at, completed_at, "
            "model_profile, actual_model_profile, routing_enabled, escalated, escalation_reason, "
            "created_by_user_id "
            "FROM cells WHERE notebook_id = $1 ORDER BY position",
            notebook_id,
        )
        for cell in cells:
            # Cell authorship rule for forks: preserve the original cell's
            # author so provenance survives the copy (users are only soft-
            # deactivated, never hard-deleted, so an existing id remains a
            # valid users(id) FK). Only when the source author is NULL — e.g.
            # a legacy cell predating cell-authorship — do we attribute the
            # copied cell to the user performing the fork.
            author_id = cell["created_by_user_id"] or user["id"]
            new_cell_id = await conn.fetchval(
                "INSERT INTO cells "
                "(notebook_id, position, prompt, status, created_at, completed_at, "
                " model_profile, actual_model_profile, routing_enabled, escalated, escalation_reason, "
                " created_by_user_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING id",
                new_nb_id, cell["position"], cell["prompt"], cell["status"],
                cell["created_at"], cell["completed_at"],
                cell["model_profile"], cell["actual_model_profile"],
                cell["routing_enabled"], cell["escalated"], cell["escalation_reason"],
                author_id,
            )
            events = await conn.fetch(
                "SELECT seq, type, payload FROM events WHERE cell_id = $1 ORDER BY seq",
                cell["id"],
            )
            for ev in events:
                payload = ev["payload"]
                if isinstance(payload, str):
                    payload_str = payload
                else:
                    payload_str = json.dumps(payload)
                await conn.execute(
                    "INSERT INTO events (cell_id, seq, type, payload) VALUES ($1, $2, $3, $4::jsonb)",
                    new_cell_id, ev["seq"], ev["type"], payload_str,
                )

    src_wdir = Path(src_nb["workspace_dir"])
    for subdir in ("plots", "outputs", "results"):
        src_sub = src_wdir / subdir
        dst_sub = new_wdir / subdir
        if src_sub.is_dir():
            for f in src_sub.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(dst_sub / f.name))

    return {"id": new_nb_id, "title": new_title}
