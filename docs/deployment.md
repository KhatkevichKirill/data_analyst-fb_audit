# Deployment

## Local development

```bash
cp .env.example .env
docker compose up -d postgres
python -m venv .venv && . .venv/bin/activate
pip install -e .
data-analyst adduser admin --admin
data-analyst serve
```

The demo Postgres listens on host port `5433` to avoid clashing with an existing local Postgres.

## Environment layout

| Path | Purpose |
|---|---|
| `.env` | secrets and connection settings |
| `workspace/` | per-notebook files, plots, CSV exports |
| `.sandbox_venv/` | optional analytics-only venv for `python_exec` |

Production deployments often split code and runtime:

- code in a git checkout or package install
- `.env`, `workspace/`, and sandbox venv outside the web-readable tree

## systemd example

See [deploy/data-analyst.service.example](deploy/data-analyst.service.example).

Typical pattern:

- dedicated OS user
- `WorkingDirectory` pointing at the installed package checkout
- `EnvironmentFile` for `.env`
- uvicorn bound to loopback only

## nginx example

See [deploy/nginx-analyst.conf.example](deploy/nginx-analyst.conf.example).

For subpath hosting:

```env
URL_PREFIX=/analyst
```

Proxy `/analyst/` to uvicorn and keep `proxy_buffering off` for SSE notebook streams.

## python_exec hardening

Only enable after:

1. bubblewrap is installed
2. `.sandbox_venv` exists and contains **no** DB/LLM packages
3. `PYTHON_EXEC_ENABLED=true`

The sandbox strips parent environment variables, unshares the network namespace, and scopes filesystem mounts to the notebook workspace.

## First admin user

```bash
data-analyst adduser alice --admin
```

The first user created is promoted to admin automatically if `--admin` is omitted.

## Health check

`GET /healthz` returns `{"ok": true}`.
