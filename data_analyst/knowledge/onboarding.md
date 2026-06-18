# Onboarding

## Mental model
The demo warehouse models a simplified Meta Ads analytics stack:
- campaigns roll up to `campaign_class` (`test` or `bau`)
- ads belong to campaigns
- daily performance lives in `demo_insights_daily`

## Conventions
- IDs are TEXT — always quote them in SQL.
- CPA = `SUM(spend) / NULLIF(SUM(purchases), 0)`.
- CTR = `SUM(clicks)::float / NULLIF(SUM(impressions), 0)`.
- Filter recent data with `date_start >= current_date - 7` unless the user asks otherwise.

## Starter workflow
1. Clarify whether the question is campaign-level, ad-level, or time-series.
2. Aggregate in SQL before charting or exporting.
3. State the exact date window in the answer.
