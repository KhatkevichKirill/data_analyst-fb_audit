"""Auth-gated file serving for notebook plots."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from config import workspace_root as _workspace_root

from ..auth import current_user
from ..db import pool

router = APIRouter(prefix="/plots", tags=["plots"])


@router.get("/{notebook_id}/{filename}")
async def get_plot(
    notebook_id: int, filename: str, user: dict = Depends(current_user)
):
    # Reject path traversal
    if "/" in filename or filename.startswith(".") or "\\" in filename:
        raise HTTPException(400, "invalid filename")

    async with pool().acquire() as conn:
        nb = await conn.fetchrow(
            "SELECT n.workspace_dir FROM notebooks n "
            "WHERE n.id = $1 AND n.archived_at IS NULL AND ("
            "  n.user_id = $2 OR EXISTS ("
            "    SELECT 1 FROM notebook_shares ns "
            "    WHERE ns.notebook_id = n.id AND ns.user_id = $2 AND ns.revoked_at IS NULL"
            "  )"
            ")",
            notebook_id, user["id"],
        )
    if not nb:
        raise HTTPException(404, "notebook not found")

    workspace_root = _workspace_root().resolve()
    target = (Path(nb["workspace_dir"]) / "plots" / filename).resolve()

    # Belt-and-suspenders: target must be under WORKSPACE_ROOT
    try:
        target.relative_to(workspace_root)
    except ValueError:
        raise HTTPException(400, "invalid path")

    if not target.is_file():
        raise HTTPException(404, "file not found")

    return FileResponse(str(target))
