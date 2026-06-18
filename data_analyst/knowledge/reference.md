# Reference — query catalog (fb_audit)

Example queries for the warehouse tables created by fb_audit.

## Top ads by spend (7 days)

```sql
SELECT
  a.id AS ad_id,
  a.name AS ad_name,
  c.name AS campaign_name,
  round(sum(i.spend), 2) AS spend,
  sum(i.impressions) AS impressions,
  sum(i.clicks) AS clicks
FROM insights i
JOIN property_ads a ON a.id = i.ad_id
JOIN property_campaigns c ON c.id = i.campaign_id
WHERE i.date_start >= current_date - 7
GROUP BY 1, 2, 3
ORDER BY spend DESC
LIMIT 10;
```

## Daily account trend

```sql
SELECT
  date_start,
  round(sum(spend), 2) AS spend,
  sum(impressions) AS impressions,
  sum(clicks) AS clicks
FROM insights
WHERE account_id = '1000000001'
  AND date_start >= current_date - 14
GROUP BY 1
ORDER BY 1;
```

## CPA with purchases from actions JSONB

```sql
WITH daily AS (
  SELECT
    i.ad_id,
    i.date_start,
    i.spend,
    coalesce((
      SELECT sum((elem->>'7d_click')::numeric)
      FROM jsonb_array_elements(i.actions) elem
      WHERE elem->>'action_type' = 'omni_purchase'
    ), 0) AS purchases
  FROM insights i
  WHERE i.date_start >= current_date - 7
)
SELECT
  ad_id,
  round(sum(spend), 2) AS spend,
  sum(purchases) AS purchases,
  round(sum(spend) / nullif(sum(purchases), 0), 2) AS cpa
FROM daily
GROUP BY 1
HAVING sum(spend) > 0
ORDER BY spend DESC
LIMIT 20;
```

## Zero-purchase spenders

```sql
WITH daily AS (
  SELECT
    i.ad_id,
    i.spend,
    coalesce((
      SELECT sum((elem->>'7d_click')::numeric)
      FROM jsonb_array_elements(i.actions) elem
      WHERE elem->>'action_type' = 'omni_purchase'
    ), 0) AS purchases
  FROM insights i
  WHERE i.date_start >= current_date - 7
)
SELECT ad_id, round(sum(spend), 2) AS spend
FROM daily
GROUP BY 1
HAVING sum(purchases) = 0 AND sum(spend) > 0
ORDER BY spend DESC;
```

## Intraday snapshot (today)

```sql
SELECT
  ad_id,
  spend::numeric AS spend,
  impressions::bigint AS impressions,
  clicks::bigint AS clicks
FROM intraday_insights
WHERE collected_at = (SELECT max(collected_at) FROM intraday_insights);
```

## Recent budget changes

```sql
SELECT event_time, object_name, translated_event_type, extra_data
FROM actions
WHERE translated_event_type ILIKE '%budget%'
ORDER BY event_time DESC
LIMIT 20;
```

## Footguns

- Quote all Meta IDs.
- Cast `intraday_insights` TEXT metrics before aggregating.
- Do not query breakdown tables unless they exist — see `schema_breakdowns`.
- Budget fields on `property_campaigns` / `property_adsets` are in **cents**.
