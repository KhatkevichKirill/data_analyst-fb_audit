# Reference

## Canonical tables
| Table | Grain | Purpose |
|---|---|---|
| `demo_campaigns` | campaign | campaign metadata and class |
| `demo_ads` | ad | ad metadata |
| `demo_insights_daily` | ad × day | spend, impressions, clicks, purchases |

## Example — top ads by spend (7d)
```sql
SELECT a.ad_id,
       a.ad_name,
       c.campaign_name,
       round(sum(i.spend), 2) AS spend,
       sum(i.purchases) AS purchases,
       round(sum(i.spend) / NULLIF(sum(i.purchases), 0), 2) AS cpa
FROM demo_insights_daily i
JOIN demo_ads a ON a.ad_id = i.ad_id
JOIN demo_campaigns c ON c.campaign_id = a.campaign_id
WHERE i.date_start >= current_date - 7
GROUP BY 1, 2, 3
ORDER BY spend DESC
LIMIT 10;
```

## Example — test campaigns only
```sql
SELECT c.campaign_name,
       round(sum(i.spend), 2) AS spend,
       sum(i.purchases) AS purchases
FROM demo_insights_daily i
JOIN demo_ads a ON a.ad_id = i.ad_id
JOIN demo_campaigns c ON c.campaign_id = a.campaign_id
WHERE c.campaign_class = 'test'
  AND i.date_start >= current_date - 7
GROUP BY 1
ORDER BY spend DESC;
```

## Footguns
- Do not compare unquoted numeric literals to TEXT ids.
- Zero-purchase rows are valid — use `NULLIF` for CPA.
- Purchases are integers; spend is numeric.
