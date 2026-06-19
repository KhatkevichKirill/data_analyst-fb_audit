# fb_audit integration

This starter kit is the **analysis layer** on top of [fb_audit](https://github.com/KhatkevichKirill/fb_audit) — standalone Python ETL scripts that load Meta Ads data into PostgreSQL.

## Architecture

```text
fb_audit (*.py loaders)  →  PostgreSQL  →  data_analyst-fb_audit (notebook UI)
         ↑
  schema_properties.sql
  schema_breakdowns.sql
```

## Quick path — fb_audit already running

Use this when [fb_audit](https://github.com/KhatkevichKirill/fb_audit) ETL is already loading into Postgres and you only need the notebook analyst on top. No knowledge-base or schema changes required.

### Prerequisites (one-time)

**Warehouse** — fb_audit has written at least once to your analytics database (`insights`, `property_*`, …). Breakdown tables are optional.

**Read-only user** on the warehouse (same DB as fb_audit `DB_NAME`):

```sql
CREATE USER data_analyst_ro WITH PASSWORD 'choose_a_password';
GRANT CONNECT ON DATABASE your_db TO data_analyst_ro;
GRANT USAGE ON SCHEMA public TO data_analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO data_analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO data_analyst_ro;
```

**App state database** — analyst keeps users and notebooks in a separate DB on the same Postgres instance:

```sql
CREATE DATABASE analyst_app;
CREATE USER data_analyst_app WITH PASSWORD 'choose_a_password';
GRANT ALL PRIVILEGES ON DATABASE analyst_app TO data_analyst_app;
```

### Five commands

```bash
# 1. Install
git clone https://github.com/KhatkevichKirill/data_analyst-fb_audit.git
cd data_analyst-fb_audit
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Configure — point DB_* at fb_audit warehouse, APP_DB_* at analyst_app, add an LLM key
cp .env.example .env

# 3. App DB migrations + first login user
data-analyst migrate
data-analyst adduser admin --admin

# 4. Analyst view over fb_audit insights (once per warehouse)
data-analyst init-view

# 5. Run
data-analyst serve
```

Open `http://127.0.0.1:8000`, log in, create a notebook.

`.env` minimum for a live fb_audit warehouse:

```env
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=meta_ads          # same as fb_audit DB_NAME
DB_USER=data_analyst_ro
DB_PASSWORD=...

APP_DB_HOST=127.0.0.1
APP_DB_PORT=5432
APP_DB_NAME=analyst_app
APP_DB_USER=data_analyst_app
APP_DB_PASSWORD=...

DEEPSEEK_API_KEY=...      # or another configured provider
```

After `init-view`, the agent prefers `v_insights_daily` (pre-extracted `purchases`, `video_views`, `trials`). Without step 4 it still works but falls back to raw `insights` JSONB.

## Out-of-the-box paths

### Path A — Demo warehouse (no Meta token)

```bash
cp .env.example .env          # add LLM API key only
docker compose up -d postgres # fb_audit-compatible tables + seed + v_insights_daily
pip install -e .
data-analyst adduser admin --admin
data-analyst serve
```

### Path B — Set up fb_audit from scratch

If fb_audit is **already running**, use [Quick path](#quick-path--fb_audit-already-running) above instead.

1. Set up fb_audit (see its README):

```bash
git clone https://github.com/KhatkevichKirill/fb_audit.git
cd fb_audit
cp .env.example .env          # FB_ACCESS_TOKEN + DB_*
psql "$DATABASE_URL" -f schema_properties.sql
psql "$DATABASE_URL" -f schema_breakdowns.sql
python insights_update.py
python insights_breakdowns_update.py   # optional but recommended
```

2. Create a read-only DB user for the analyst:

```sql
CREATE USER data_analyst_ro WITH PASSWORD '...';
GRANT CONNECT ON DATABASE your_db TO data_analyst_ro;
GRANT USAGE ON SCHEMA public TO data_analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO data_analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO data_analyst_ro;
```

3. Point analyst `.env` at the warehouse (`DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`).

4. Apply the analyst view (once per warehouse):

```bash
data-analyst init-view
```

5. Start the analyst app: `data-analyst serve`.

## What works without customization

- Table names and relationships match fb_audit output
- Knowledge base documents all fb_audit loaders (`.py` scripts, not notebooks)
- Breakdown tables (`insights_breakdowns_demographic`, `insights_breakdowns_placement`)
- `v_insights_daily` view with pre-extracted purchases, video_views, trials
- TEXT-metric casting conventions documented for raw tables

## Recommended ETL order (from fb_audit)

1. `actions.py`
2. `account_atribute.py` → `campaign_atribute.py` → `adset_atribute.py` → `ad_atribute.py` → `creative_atribute.py`
3. `insights_update.py` (or `insights.py` for historical backfill via `backfill/`)
4. `insights_breakdowns_update.py`
5. `intraday_insights.py` on a schedule throughout the day

`insights_update.py` and `insights_breakdowns_update.py` atomically re-fetch the **last 7 days** on each run to capture late attribution.

## Environment parity

| fb_audit | data analyst starter |
|---|---|
| `FB_ACCESS_TOKEN`, `FB_GRAPH_API_VERSION` | not required for analyst |
| `DB_*` (read/write ETL user) | `DB_*` (read-only analyst user) |
| `ACCOUNT_IDS` | not required (filter in SQL) |
| `INSIGHTS_START_DATE` / `INSIGHTS_END_DATE` | — |
| `REFRESH_BREAKDOWN_MVS` | — |
| — | `DEEPSEEK_API_KEY` or other LLM key |

Keep the analyst read-only user separate from the ETL write user.

## Optional extensions

| Extension | Effort | Benefit |
|---|---|---|
| `mv_insights_daily` matview | `schema/mv_insights_daily.sql.example` + refresh cron | Faster queries on large warehouses |
| nginx + `URL_PREFIX=/analyst` | `deploy/nginx-analyst.conf.example` | Subpath hosting behind reverse proxy |

See [docs/adapters.md](adapters.md) for LLM providers and deployment.
