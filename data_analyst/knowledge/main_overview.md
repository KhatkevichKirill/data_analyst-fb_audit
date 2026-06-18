# Main overview — fb_audit warehouse analysis

Use this page for **account KPIs, spend trends, ad performance, intraday snapshots, and change history** over data loaded by [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

For table-level detail see `schema`, `schema_insights`, `schema_entities`.

## Primary tables

### `insights` — start here for performance

One row per `(ad_id, date_start)` (plus hierarchy IDs). Aggregate directly:

```sql
SELECT date_start, SUM(spend) AS spend, SUM(impressions) AS impressions
FROM insights
WHERE account_id = '1000000001'
  AND date_start >= current_date - 7
GROUP BY 1
ORDER BY 1;
```

Join to names:

```sql
FROM insights i
JOIN property_ads a ON a.id = i.ad_id
JOIN property_campaigns c ON c.id = i.campaign_id
```

### `property_*` — metadata

Use for names, statuses, budgets, targeting. Join on `id` = insights hierarchy IDs.

### `intraday_insights` — today so far

TEXT columns — cast before math. Latest snapshot only:

```sql
WHERE collected_at = (SELECT MAX(collected_at) FROM intraday_insights)
```

### `actions` — audit trail

Who changed what. Not for spend/CPA questions.

## Purchases and CPA

Extract purchases from `insights.actions` (see `schema_insights`), then:

```sql
CPA = SUM(spend) / NULLIF(SUM(purchases), 0)
```

## What fb_audit does NOT include

- Materialized views (`mv_insights_daily`, `mv_bd_*`) — add yourself if needed
- Breakdown tables — see `schema_breakdowns`
- Creative upload pipelines, rules engines, automated launch — out of scope

## Recommended read order

1. `concepts` — IDs, timezones, metrics
2. `schema_insights` — insights + intraday + actions
3. `schema_entities` — property tables
4. `reference` — copy-paste query patterns
