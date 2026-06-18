# Meta Ads Data Analyst Starter Kit

Natural-language SQL analyst for a Meta Ads-style PostgreSQL warehouse.

Repository: https://github.com/KhatkevichKirill/data_analyst-fb_audit

This repository is a **public starter kit**, not a production dump. It ships:

- FastAPI notebook web app with multi-user auth
- Read-only SQL, chart, CSV export, and optional sandboxed `python_exec`
- `analyst_app` state database for notebooks, cells, and events
- Demo Postgres schema with synthetic campaigns, ads, and daily insights
- Generic knowledge base for the `read_wiki` tool
- Adapter docs for plugging in your own warehouse, LLM providers, and nginx SSO

For ingestion reference notebooks, see [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

## Quick Start

```bash
cp .env.example .env
# add at least one LLM API key, e.g. DEEPSEEK_API_KEY

docker compose up -d postgres
python -m venv .venv
. .venv/bin/activate
pip install -e .

data-analyst adduser admin --admin
data-analyst serve
```

Open `http://127.0.0.1:8000`, log in, create a notebook, and ask:

> Top test ads by spend in the last 7 days

`python_exec` is **disabled by default**. Enable it only after installing bubblewrap and the sandbox venv — see [docs/deployment.md](docs/deployment.md).

## What Works Out Of The Box

- Login and notebook UI
- Natural-language questions over the demo warehouse
- Vega-Lite charts and CSV export
- Notebook sharing, export, and fork
- Model profile selector (any configured provider key)

## What You Customize

1. **Warehouse adapter** — point `DB_*` at your real `meta_ads` schema and replace `data_analyst/knowledge/`.
2. **LLM adapter** — configure provider keys and profiles in `.env`.
3. **Deployment adapter** — optional nginx mount at `/analyst` with `URL_PREFIX=/analyst`.

See [docs/adapters.md](docs/adapters.md).

## Repository Layout

```text
data_analyst/          Python package: agent, tools, web app, migrations
schema/                Postgres init scripts for docker compose
docs/                  Architecture, adapters, deployment, licensing
examples/              Starter prompts for the demo dataset
deploy/                Generic systemd + nginx examples
docker-compose.yml     Local Postgres with demo data
```

## Safety Defaults

- SQL tool allows only `SELECT` / `WITH`
- Analytics DB user is read-only
- `python_exec` disabled unless `PYTHON_EXEC_ENABLED=true`
- No Meta API credentials required for the demo flow
- Put the app behind your own auth/proxy before exposing it publicly

## License

MIT. See [LICENSE](LICENSE).

## Status

Public starter draft. Replace demo schema and knowledge pages before using against production data.
