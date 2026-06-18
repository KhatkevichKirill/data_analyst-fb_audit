# Domain concepts

Canonical definitions for metrics, IDs, and date windows in a fb_audit warehouse.

## Account scope

fb_audit can load one or many ad accounts. Set `ACCOUNT_IDS` in the ETL environment to restrict which accounts are fetched.

**Always filter by `account_id` in SQL** when multiple accounts exist. If the user does not specify an account and only one account is present in `property_accounts`, use that one and mention it in the answer.

Read timezone from `property_accounts.timezone_name` rather than assuming UTC.

## Meta entity IDs

All Meta IDs (`account_id`, `campaign_id`, `adset_id`, `ad_id`, creative IDs) are stored as VARCHAR/TEXT.

Always quote in WHERE clauses: `WHERE ad_id = '4000000001'`.

Unquoted numeric literals cause: `operator does not exist: character varying = bigint`.

## Default metrics

| Metric | Definition |
|---|---|
| Spend | `SUM(spend)` from `insights` |
| Impressions | `SUM(impressions)` |
| Clicks | `SUM(clicks)` |
| CTR | `SUM(clicks)::float / NULLIF(SUM(impressions), 0)` |
| CPA | `SUM(spend) / NULLIF(purchases, 0)` where purchases come from `actions` JSONB |
| Hook rate | video views / impressions — extract `video_view` from `actions` JSONB |

Purchases are **not** a native column on `insights`. Extract:

```sql
SUM((elem->>'7d_click')::numeric)
FROM jsonb_array_elements(actions) elem
WHERE elem->>'action_type' = 'omni_purchase'
```

Default attribution window: `7d_click`.

## Date windows

Insights use `date_start` as a calendar date. For account timezone `"America/Los_Angeles"`:

```sql
WITH la_today AS (
  SELECT (CURRENT_TIMESTAMP AT TIME ZONE pa.timezone_name)::date AS d
  FROM property_accounts pa
  LIMIT 1
)
```

| Phrase | Meaning |
|---|---|
| Last 7 days | rolling 7 complete days before `la_today.d` |
| Last week | previous Mon–Sun in account timezone |
| Yesterday | `la_today.d - 1` |
| Today (intraday) | use `intraday_insights`, not `insights` |

Always state the exact date range in the answer.

## Active vs idle ads

`property_ads.effective_status = 'ACTIVE'` does not guarantee recent delivery. Prefer:

```sql
EXISTS (
  SELECT 1 FROM insights i
  WHERE i.ad_id = property_ads.id
    AND i.date_start >= current_date - 3
    AND i.spend > 0
)
```

## Campaign naming conventions

fb_audit does not encode test/BAU semantics in the schema. Users may tag campaigns in `property_campaigns.name` (e.g. `%prospecting%`, `%retarget%`). Do not invent a test/BAU registry unless the user created one.
