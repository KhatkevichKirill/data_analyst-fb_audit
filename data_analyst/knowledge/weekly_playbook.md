# Weekly Playbook

Use these checks when the user asks for a weekly summary or recurring analytics.

## Check 1 — account test summary (7d)
Total spend, purchases, CPA, impressions, clicks for `campaign_class = 'test'`.

## Check 2 — top test ads
Top ads by spend in test campaigns over the last 7 complete days.

## Check 3 — zero-purchase spenders
Ads with spend > 0 and purchases = 0 in the last 7 days, sorted by spend.

## Check 4 — active test campaigns
Campaigns with any spend or impressions yesterday in the test class.

## SQL pattern for test scope
```sql
FROM demo_insights_daily i
JOIN demo_ads a ON a.ad_id = i.ad_id
JOIN demo_campaigns c ON c.campaign_id = a.campaign_id
WHERE c.campaign_class = 'test'
```

Always state the exact date range used in the answer.
