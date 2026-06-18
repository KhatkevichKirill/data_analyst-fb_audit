"""FastAPI app: lifespan, routes, static, schema crib bootstrap."""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from config import load_env, prefixed

# Load env BEFORE anything else imports it
load_env()

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

# Ensure we can import the CLI's tools.py
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from .agent import set_schema_crib  # noqa: E402
from .auth import current_user, lookup_session, SESSION_COOKIE  # noqa: E402
from .db import close_pool, init_pool, run_migrations  # noqa: E402
from .routes import auth_routes, notebooks, outputs, plots  # noqa: E402
from .routes.notebooks import config_router as _config_router  # noqa: E402

# Reuse the CLI's schema crib loader (sync function)
sys.path.insert(0, str(_ROOT))
from analyst import load_schema_crib  # noqa: E402

templates = Jinja2Templates(directory=str(_ROOT / "web" / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    applied = await run_migrations()
    if applied:
        print(f"[migrations] applied: {', '.join(applied)}")
    crib = load_schema_crib()
    set_schema_crib(crib)
    print(f"[schema crib] {crib.count(chr(10) + '- **')} tables loaded")
    yield
    await close_pool()


app = FastAPI(lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(_ROOT / "web" / "static")),
    name="static",
)

app.include_router(auth_routes.router)
app.include_router(_config_router)
app.include_router(notebooks.router)
app.include_router(plots.router)
app.include_router(outputs.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Notebook UI — redirect to login if not authenticated."""
    token = request.cookies.get(SESSION_COOKIE)
    user = await lookup_session(token) if token else None
    if not user:
        return RedirectResponse(url=prefixed("/login"), status_code=303)
    return templates.TemplateResponse(
        request, "notebook.html", {"username": user["username"]}
    )


_LIVE_ACTION_USERS: set = {
    u.strip()
    for u in os.environ.get("LIVE_ACTION_USERS", "").split(",")
    if u.strip()
}


@app.get("/api/me")
async def me(user: dict = Depends(current_user)):
    return {
        "username": user["username"],
        "is_admin": user["is_admin"],
        "is_live_operator": user["username"] in _LIVE_ACTION_USERS,
    }


@app.get("/healthz")
async def health():
    return {"ok": True}
