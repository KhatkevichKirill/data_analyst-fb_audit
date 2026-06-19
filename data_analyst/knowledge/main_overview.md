# Main overview — fb_audit warehouse analysis

Use this page for **account KPIs, spend trends, ad performance, demographic/placement splits, intraday snapshots, and change history** over data loaded by [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

For table-level detail see `schema`, `schema_insights`, `schema_entities`, `schema_breakdowns`.

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

### `insights_breakdowns_*` — age/gender and placement

Loaded by `insights_breakdowns_update.py`. TEXT metrics — cast before SUM. See `schema_breakdowns`.

### `insights` — raw upstream

Same grain as `v_insights_daily` but metrics in TEXT + JSONB. Use for non-standard action types or attribution windows.

### `property_*` — metadata

Wide TEXT tables from `schema_properties.sql`. Demo docker seed uses a subset. Join on `id` = hierarchy IDs.

### `intraday_insights` — today so far

TEXT metrics — cast before math. Latest snapshot:

```sql
WHERE collected_at = (SELECT MAX(collected_at) FROM intraday_insights)
```

### `actions` — audit trail

Who changed what. Not for spend/CPA questions.

## Purchases and CPA

Prefer `SUM(purchases)` from `v_insights_daily`. CPA = `SUM(spend) / NULLIF(SUM(purchases), 0)`.

## What is outside fb_audit

- `mv_insights_daily` materialized view — optional; see `schema/mv_insights_daily.sql.example`
- Creative upload pipelines, rules engines, automated launch — out of scope

## Recommended read order

1. `concepts` — IDs, timezones, metrics, TEXT casts
2. `schema_insights` — insights + intraday + actions + view
3. `schema_breakdowns` — demographic and placement tables
4. `schema_entities` — property tables
5. `reference` — copy-paste query patterns
