# Onboarding

## Mental model

This analyst connects to the same PostgreSQL database that [fb_audit](https://github.com/KhatkevichKirill/fb_audit) fills:

```text
Meta API → fb_audit notebooks → Postgres → Data Analyst (NL→SQL)
```

Three layers:
1. **Attributes** — `property_*` (what entities exist and how they are configured)
2. **Performance** — `insights` (daily ad×day metrics)
3. **Operations** — `actions` (change log), `intraday_insights` (today snapshot)

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

1. Run fb_audit ETL into your Postgres database.
2. Point `.env` `DB_*` at that database with a read-only user.
3. Keep or extend `data_analyst/knowledge/` — defaults match fb_audit table names.

See `docs/fb_audit_integration.md` in the repo root.
