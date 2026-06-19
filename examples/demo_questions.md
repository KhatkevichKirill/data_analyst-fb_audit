# Demo starter questions (fb_audit warehouse)

| Label | Prompt |
|---|---|
| Top ads by spend | Top 5 ads by spend in the last 7 days with campaign name, CPA |
| Daily spend trend | Daily account spend for the last 14 days |
| Zero-purchase spenders | Ads with spend > 0 and zero purchases in the last 7 days |
| Spend by gender | Spend and impressions by gender over the last 7 days from breakdown tables |
| Spend by platform | Compare facebook vs instagram spend from placement breakdowns |
| Data freshness | Latest date in insights_log — is yesterday loaded? |
| Last week summary | Account-level spend, impressions, clicks, purchases, CPA for last week |

Purchases come from `v_insights_daily.purchases` (or `insights.actions` JSONB). Breakdown metrics are TEXT — cast before aggregating. See `data_analyst/knowledge/reference.md`.
