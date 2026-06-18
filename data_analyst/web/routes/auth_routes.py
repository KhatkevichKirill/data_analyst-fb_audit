"""Login / logout HTML routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from fastapi.responses import Response

from config import prefixed

from ..auth import (
    COOKIE_PATH,
    SESSION_COOKIE,
    SESSION_TTL_DAYS,
    authenticate,
    create_session,
    destroy_session,
    lookup_session,
)


def _safe_next(next_url: str | None) -> str:
    """Only allow same-site relative paths to prevent open-redirect."""
    if not next_url:
        return "/"
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"

router = APIRouter()
_templates_dir = str(Path(__file__).resolve().parent.parent / "templates")
templates = Jinja2Templates(directory=_templates_dir)


@router.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    error: str | None = None,
    next: str | None = None,
):
    return templates.TemplateResponse(
        request, "login.html", {"error": error, "next": _safe_next(next)}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str | None = Form(None),
):
    user = await authenticate(username, password)
    if not user:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "Invalid username or password", "next": _safe_next(next)},
            status_code=401,
        )
    token, expires = await create_session(user["id"])
    resp = RedirectResponse(url=_safe_next(next), status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        path=COOKIE_PATH,
    )
    return resp


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await destroy_session(token)
    resp = RedirectResponse(url=prefixed("/login"), status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path=COOKIE_PATH)
    return resp


@router.get("/auth/check")
async def auth_check(request: Request):
    """nginx auth_request endpoint. Returns 204 + identity headers, or 401."""
    token = request.cookies.get(SESSION_COOKIE)
    user = await lookup_session(token) if token else None
    if not user:
        return Response(status_code=401)
    return Response(
        status_code=204,
        headers={
            "X-Username": user["username"],
            "X-Is-Admin": "true" if user["is_admin"] else "false",
        },
    )
