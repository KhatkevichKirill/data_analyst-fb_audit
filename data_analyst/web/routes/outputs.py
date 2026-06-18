"""Auth-gated file serving for notebook CSV exports."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from config import workspace_root as _workspace_root

from ..auth import current_user
from ..db import pool

router = APIRouter(prefix="/outputs", tags=["outputs"])

# Conservative allowlist: alphanumeric start, then alphanumeric / dot / dash / underscore.
# Forces the name to not start with `.` and excludes `/`, `\`, and other traversal chars.
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@router.get("/{notebook_id}/{filename}")
async def get_output(
    notebook_id: int, filename: str, user: dict = Depends(current_user)
):
    if not _SAFE_FILENAME_RE.match(filename) or "/" in filename or "\\" in filename:
        raise HTTPException(400, "invalid filename")
    if not filename.lower().endswith(".csv"):
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
    target = (Path(nb["workspace_dir"]) / "outputs" / filename).resolve()

    try:
        target.relative_to(workspace_root)
    except ValueError:
        raise HTTPException(400, "invalid path")

    if not target.is_file():
        raise HTTPException(404, "file not found")

    return FileResponse(
        str(target),
        media_type="text/csv",
        filename=filename,
    )
