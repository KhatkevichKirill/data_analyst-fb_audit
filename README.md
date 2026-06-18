# Meta Ads Data Analyst Starter Kit

Natural-language SQL analyst for a Meta Ads-style PostgreSQL warehouse.

Repository: https://github.com/KhatkevichKirill/data_analyst-fb_audit

This repository is a **public starter kit**, not a production dump. It ships:

- FastAPI notebook web app with multi-user auth
- Read-only SQL, chart, CSV export, and optional sandboxed `python_exec`
- `analyst_app` state database for notebooks, cells, and events
- Demo Postgres schema matching **fb_audit table names** (`insights`, `property_*`, `actions`, …)
- Knowledge base aligned with [fb_audit](https://github.com/KhatkevichKirill/fb_audit) — schema docs, query patterns, integration guide
- Adapter docs for plugging in your own warehouse, LLM providers, and nginx SSO

For ingestion reference notebooks, see [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

## Related repositories

| Repository | Role |
|---|---|
| [fb_audit](https://github.com/KhatkevichKirill/fb_audit) | Meta Marketing API → Postgres ETL notebooks and scripts |
| **this repo** | Natural-language notebook analyst over the warehouse |

Typical flow: run [fb_audit](https://github.com/KhatkevichKirill/fb_audit) ETL into Postgres, then point this repo at the same database. See [docs/fb_audit_integration.md](docs/fb_audit_integration.md).

## Notebook web app

Yes — the full multi-user **notebook UI** ships in this repo. After `data-analyst serve`, open `http://127.0.0.1:8000`, log in, create a notebook, and ask questions in natural language. The UI supports:

- streaming answers (SSE)
- Vega-Lite charts
- CSV export
- notebook sharing, fork, and Markdown export
- per-cell model selection

You need: Postgres (demo via `docker compose` or your own warehouse), one LLM API key in `.env`, and an app user from `data-analyst adduser`.

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

1. **Real data** — run fb_audit ETL and point `DB_*` at your warehouse ([integration guide](docs/fb_audit_integration.md)).
2. **LLM adapter** — configure provider keys and profiles in `.env`.
3. **Optional extensions** — matviews, breakdown ETL, nginx subpath — see [docs/adapters.md](docs/adapters.md).

## Repository Layout

```text
data_analyst/          Python package: agent, tools, web app, migrations
schema/                Postgres init scripts for docker compose
docs/                  Architecture, fb_audit integration, adapters, deployment
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

Public starter aligned with fb_audit. Demo docker seed uses the same table names; connect real ETL data with minimal `.env` changes.
