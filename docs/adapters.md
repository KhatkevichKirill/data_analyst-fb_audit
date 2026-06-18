# Adapters

The starter kit is designed to be extended without forking the agent loop.

## 1. Warehouse Adapter

Point the read-only connection at your analytics database:

```env
DB_HOST=...
DB_PORT=5432
DB_NAME=meta_ads
DB_USER=svc_analyst_ro
DB_PASSWORD=...
```

Then replace or extend `data_analyst/knowledge/` with your own schema docs, metric definitions, and example queries. The `read_wiki` tool reads from `KNOWLEDGE_DIR`.

Recommended pages:

- `readme.md` — navigation
- `onboarding.md` — conventions and mental model
- `reference.md` — canonical views and example SQL
- `schema.md` — table catalog
- `weekly_playbook.md` — recurring checks

If you already maintain a wiki, set:

```env
KNOWLEDGE_DIR=/path/to/your/knowledge
```

## 2. LLM Adapter

Profiles live in `data_analyst/analyst.py::PROFILES`. Each profile maps to a LiteLLM model string and an env var for its API key.

```env
WEB_MODEL=deepseek
DEEPSEEK_API_KEY=...
```

The notebook UI exposes visible profiles only. Hidden profiles remain available for escalation or replay of older cells.

Optional routing:

```env
ROUTING_ENABLED=true
PRIMARY_MODEL_PROFILE=deepseek
ESCALATION_MODEL_PROFILE=openai_gpt41
HIGH_STAKES_KEYWORDS=budget,launch,approve
```

## 3. Deployment Adapter

### Standalone mode (default)

Run at repo root with empty `URL_PREFIX`:

```bash
data-analyst serve --host 127.0.0.1 --port 8000
```

### nginx subpath mode

Set `URL_PREFIX=/analyst` and proxy `/analyst/` to uvicorn. See [deploy/nginx-analyst.conf.example](deploy/nginx-analyst.conf.example).

If you also gate a larger dashboard with nginx `auth_request`, expose `/auth/check` from this app and forward `X-Username` / `X-Is-Admin` to your internal APIs.

## 4. python_exec Adapter

The starter disables `python_exec` unless explicitly enabled:

```env
PYTHON_EXEC_ENABLED=true
SANDBOX_PYTHON=./.sandbox_venv/bin/python
```

Install the sandbox venv:

```bash
python -m venv .sandbox_venv
.sandbox_venv/bin/pip install -r data_analyst/sandbox-requirements.txt
```

Linux production deployments should keep bubblewrap (`bwrap`) isolation. macOS local dev can enable the tool for experimentation, but bubblewrap is not available by default on macOS.

## 5. Ingestion Adapter

This repo does not pull Meta Marketing API data. Use [fb_audit](https://github.com/KhatkevichKirill/fb_audit) or your own ETL to populate the warehouse, then point `DB_*` at that database.
