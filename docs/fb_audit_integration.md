# fb_audit integration

This starter kit is the **analysis layer** on top of [fb_audit](https://github.com/KhatkevichKirill/fb_audit) — standalone Python ETL scripts that load Meta Ads data into PostgreSQL.

## Architecture

```text
fb_audit (*.py loaders)  →  PostgreSQL  →  data_analyst-fb_audit (notebook UI)
         ↑
  schema_properties.sql
  schema_breakdowns.sql
```

## Out-of-the-box paths

### Path A — Demo warehouse (no Meta token)

```bash
cp .env.example .env          # add LLM API key only
docker compose up -d postgres # fb_audit-compatible tables + seed + v_insights_daily
pip install -e .
data-analyst adduser admin --admin
data-analyst serve
```

### Path B — Your real fb_audit database

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
