# Main overview — fb_audit warehouse analysis

Use this page for **account KPIs, spend trends, ad performance, intraday snapshots, and change history** over data loaded by [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

For table-level detail see `schema`, `schema_insights`, `schema_entities`.

## Primary tables

### `v_insights_daily` — start here for performance

One row per `(ad_id, date_start)`. Numeric columns including pre-extracted `purchases`:

```sql
SELECT date_start, SUM(spend) AS spend, SUM(purchases) AS purchases
FROM v_insights_daily
WHERE account_id = '1000000001'
  AND date_start >= current_date - 7
GROUP BY 1
ORDER BY 1;
```

Join to names via `property_ads` / `property_campaigns`.

### `insights` — raw upstream

Same grain as `v_insights_daily` but metrics live in JSONB (`actions`, `results`, `video_*`). Use only for non-standard action types.

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

Extract purchases from `insights.actions` only when `v_insights_daily` is not available:

```sql
-- prefer: SELECT SUM(purchases) FROM v_insights_daily
```

## What fb_audit does NOT include by default

- `mv_insights_daily` materialized view — optional; see `schema/mv_insights_daily.sql.example`
- Breakdown tables — see `schema_breakdowns`
- Creative upload pipelines, rules engines, automated launch — out of scope

## Recommended read order

1. `concepts` — IDs, timezones, metrics
2. `schema_insights` — insights + intraday + actions
3. `schema_entities` — property tables
4. `reference` — copy-paste query patterns
