# Onboarding

## Mental model

This analyst connects to the same PostgreSQL database that [fb_audit](https://github.com/KhatkevichKirill/fb_audit) fills:

```text
Meta API → fb_audit Python loaders → Postgres → Data Analyst (NL→SQL)
```

Layers:
1. **Attributes** — `property_*` (entity metadata from `schema_properties.sql`)
2. **Performance** — `v_insights_daily` / `insights` (daily ad×day metrics)
3. **Breakdowns** — `insights_breakdowns_demographic`, `insights_breakdowns_placement`
4. **Operations** — `actions` (change log), `intraday_insights` (today snapshot)

## First questions to ask yourself

- Account scope — one or many `account_id` values?
- Time window — last 7 days, yesterday, today intraday?
- Grain — account, campaign, adset, or ad?
- Metric — spend, CPA, CTR, purchases?

## Before writing SQL

1. Call `read_wiki(page="concepts")` for ID quoting and date rules.
2. Call `read_wiki(page="schema_insights")` for purchases extraction.
3. Call `read_wiki(page="reference")` for ready-made query patterns.

## Connecting real fb_audit data

1. Run fb_audit ETL (`schema_properties.sql`, `schema_breakdowns.sql`, then `*.py` loaders).
2. Point `.env` `DB_*` at that database with a read-only user.
3. Run `data-analyst init-view` to create `v_insights_daily`.

See `docs/fb_audit_integration.md` in the repo root.
