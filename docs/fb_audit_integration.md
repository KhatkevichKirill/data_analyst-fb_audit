# fb_audit integration

This starter kit is designed as the **analysis layer** on top of [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

## Architecture

```text
fb_audit (ETL notebooks)  →  PostgreSQL  →  data_analyst-fb_audit (notebook UI)
```

## Out-of-the-box paths

### Path A — Demo warehouse (no Meta token)

```bash
cp .env.example .env          # add LLM API key only
docker compose up -d postgres # loads fb_audit-compatible schema + seed data
pip install -e .
data-analyst adduser admin --admin
data-analyst serve
```

The docker seed creates fb_audit table names, seed data, and the `v_insights_daily` view.

### Path B — Your real fb_audit database

1. Run fb_audit ETL into Postgres (see fb_audit `PIPELINE_GUIDE_RU_EN.md`).
2. Create a read-only DB user:

```sql
CREATE USER data_analyst_ro WITH PASSWORD '...';
GRANT CONNECT ON DATABASE your_db TO data_analyst_ro;
GRANT USAGE ON SCHEMA public TO data_analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO data_analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO data_analyst_ro;
```

3. Point `.env` at the warehouse (`DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`).

4. Apply the analyst view (once per warehouse):

```bash
data-analyst init-view
# or: psql ... -f schema/v_insights_daily.sql
```

5. Start the analyst app.

## What works without customization

- Table names and relationships match fb_audit output
- `v_insights_daily` view with pre-extracted purchases, video_views, trials
- Knowledge base documents fb_audit tables and query patterns

## Optional extensions (minimal extra work)

| Extension | Effort | Benefit |
|---|---|---|
| Add `mv_insights_daily` matview | Run `schema/mv_insights_daily.sql.example` + refresh cron | Faster queries on large warehouses |
| Breakdown ETL | New fetch script | Age/gender and placement analysis — see `schema_breakdowns` |
| Custom campaign tags | View or column on `property_campaigns` | Test/BAU segmentation without name heuristics |
| nginx + `URL_PREFIX=/analyst` | Copy `deploy/nginx-analyst.conf.example` | Subpath hosting behind reverse proxy |

## Recommended ETL order (from fb_audit)

1. `actions`
2. `account_atribute` → `campaign_atribute` → `adset_atribute` → `ad_atribute` → `creative_atribute`
3. `insights_update` (or `insights` for backfill)
4. `intraday_insights.py` on a schedule

## Environment parity

| fb_audit | data analyst starter |
|---|---|
| `DB_*` (read/write ETL user) | `DB_*` (read-only analyst user) |
| `FB_ACCESS_TOKEN` | not required for analyst |
| `ACCOUNT_IDS` | not required for analyst (filter in SQL) |
| — | `DEEPSEEK_API_KEY` or other LLM key |

Keep the analyst read-only user separate from the ETL write user.
