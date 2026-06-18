# Demo starter questions (fb_audit warehouse)

| Label | Prompt |
|---|---|
| Top ads by spend | Top 5 ads by spend in the last 7 days with campaign name, CPA |
| Daily spend trend | Daily account spend for the last 14 days |
| Zero-purchase spenders | Ads with spend > 0 and zero purchases in the last 7 days |
| Campaign breakdown | Compare campaigns by spend and CPA over the last 7 days |
| Data freshness | Latest date in insights_log — is yesterday loaded? |
| Last week summary | Account-level spend, impressions, clicks, purchases, CPA for last week |

Purchases come from `insights.actions` JSONB (`omni_purchase`, `7d_click` window). See `data_analyst/knowledge/reference.md`.
