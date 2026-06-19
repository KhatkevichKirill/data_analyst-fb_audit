# Reference — query catalog (fb_audit)

Prefer `v_insights_daily` over raw `insights` — purchases and video_views are already numeric.

## Top ads by spend (7 days)

```sql
SELECT
  a.id AS ad_id,
  a.name AS ad_name,
  c.name AS campaign_name,
  round(sum(v.spend), 2) AS spend,
  sum(v.impressions) AS impressions,
  sum(v.clicks) AS clicks,
  sum(v.purchases) AS purchases,
  round(sum(v.spend) / nullif(sum(v.purchases), 0), 2) AS cpa
FROM v_insights_daily v
JOIN property_ads a ON a.id = v.ad_id
JOIN property_campaigns c ON c.id = v.campaign_id
WHERE v.date_start >= current_date - 7
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
  sum(clicks) AS clicks,
  sum(purchases) AS purchases
FROM v_insights_daily
WHERE account_id = '1000000001'
  AND date_start >= current_date - 14
GROUP BY 1
ORDER BY 1;
```

## CPA and hook rate by ad

```sql
SELECT
  ad_id,
  round(sum(spend), 2) AS spend,
  sum(purchases) AS purchases,
  round(sum(spend) / nullif(sum(purchases), 0), 2) AS cpa,
  round(sum(video_views)::numeric / nullif(sum(impressions), 0), 4) AS hook_rate
FROM v_insights_daily
WHERE date_start >= current_date - 7
GROUP BY 1
HAVING sum(spend) > 0
ORDER BY spend DESC
LIMIT 20;
```

## Zero-purchase spenders

```sql
SELECT ad_id, round(sum(spend), 2) AS spend
FROM v_insights_daily
WHERE date_start >= current_date - 7
GROUP BY 1
HAVING sum(purchases) = 0 AND sum(spend) > 0
ORDER BY spend DESC;
```

## Raw insights — non-standard action type

Use when `v_insights_daily` does not expose the metric:

```sql
SELECT
  ad_id,
  date_start,
  SUM((elem->>'7d_click')::numeric) AS link_clicks
FROM insights i,
     LATERAL jsonb_array_elements(i.actions) elem
WHERE elem->>'action_type' = 'link_click'
  AND date_start >= current_date - 7
GROUP BY 1, 2;
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

## Spend by gender (breakdowns)

```sql
SELECT
  gender,
  round(sum(spend::numeric), 2) AS spend,
  sum(impressions::bigint) AS impressions
FROM insights_breakdowns_demographic
WHERE account_id = '1000000001'
  AND date_start >= current_date - 7
GROUP BY 1
ORDER BY spend DESC;
```

## Spend by platform (breakdowns)

```sql
SELECT
  publisher_platform,
  round(sum(spend::numeric), 2) AS spend
FROM insights_breakdowns_placement
WHERE date_start >= current_date - 7
GROUP BY 1
ORDER BY spend DESC;
```

## Footguns

- Quote all Meta IDs.
- Cast TEXT metrics on `insights`, breakdown tables, and `intraday_insights` before aggregating.
- Budget fields on `property_*` are TEXT in **cents**: `daily_budget::numeric / 100`.
