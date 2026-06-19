# Weekly playbook

Recurring checks for a fb_audit warehouse. Adapt account filters to your setup.

## Check 1 — account summary (7d)

Total spend, impressions, clicks, purchases, CPA for the last 7 complete days.

```sql
SELECT
  round(sum(spend), 2) AS spend,
  sum(impressions) AS impressions,
  sum(clicks) AS clicks,
  sum(purchases) AS purchases,
  round(sum(spend) / nullif(sum(purchases), 0), 2) AS cpa
FROM v_insights_daily
WHERE date_start >= current_date - 7;
```

## Check 2 — top ads by spend

Top 10 ads by spend in the last 7 days with campaign name.

## Check 3 — zero-purchase spenders

Ads with spend > 0 and zero extracted purchases in the last 7 days.

## Check 4 — data freshness

```sql
SELECT max(date) AS latest_insights_date
FROM insights_log
WHERE account_id = 'YOUR_ACCOUNT_ID';
```

Compare to yesterday in the account timezone.

## Check 5 — intraday sanity (optional)

If `intraday_insights.py` runs on schedule, confirm today's row count and latest `collected_at`.

## Check 6 — recent operational changes

Last 7 days of `actions` grouped by `translated_event_type` — pauses, budget updates, etc.

Always state the exact date range used in the answer.
