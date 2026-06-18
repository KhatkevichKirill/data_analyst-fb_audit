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

The docker seed creates the same table **names** as fb_audit with synthetic rows.

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

3. Point `.env`:

```env
DB_HOST=...
DB_NAME=your_db
DB_USER=data_analyst_ro
DB_PASSWORD=...
```

4. Start the analyst app — knowledge pages already document fb_audit tables.

## What works without customization

- Table names and relationships match fb_audit output
- Knowledge base (`data_analyst/knowledge/`) documents insights, property_*, actions
- System prompt knows purchases extraction from `actions` JSONB
- Example queries in `reference.md` and starter chips in the notebook UI

## Optional extensions (minimal extra work)

| Extension | Effort | Benefit |
|---|---|---|
| Add `mv_insights_daily` matview | SQL migration + refresh cron | Faster queries, pre-extracted purchases column |
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
