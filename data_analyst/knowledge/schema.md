# Data catalog — fb_audit warehouse

Read this first when the question is about performance, entity metadata, or change history loaded by [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

## Domains

| Domain | What you can answer | Deep-dive |
|---|---|---|
| Entity attributes | Account, campaign, adset, ad, creative metadata | `schema_entities` |
| Daily insights | Spend, impressions, clicks, purchases at ad×day | `schema_insights` |
| Intraday | Today-so-far snapshot | `schema_insights` |
| Change log | Who paused/changed budget and when | `schema_insights` (actions) |
| Breakdowns | Age×gender or placement splits | `schema_breakdowns` (extension — not in core fb_audit) |
| Tombstones | Deleted/inaccessible Meta objects | `schema_entities` (deleted_objects) |

## Quick lookup

| Question | Page | Primary table |
|---|---|---|
| Daily spend / purchases / CPA trend | `schema_insights` | `insights` |
| Hourly / today spend | `schema_insights` | `intraday_insights` |
| Campaign or ad names / status | `schema_entities` | `property_campaigns`, `property_ads` |
| Who changed a budget yesterday | `schema_insights` | `actions` |
| Account timezone / currency | `schema_entities` | `property_accounts` |
| Demographic breakdown | `schema_breakdowns` | not loaded by default — see extension page |

## Cross-cutting conventions

- **IDs are VARCHAR/TEXT.** Always quote: `WHERE ad_id = '4000000001'`.
- **Default performance table:** `insights` (one row per ad×day). There is no materialized view in the fb_audit starter — aggregate from `insights` directly.
- **Purchases:** extract from `insights.actions` JSONB where `action_type = 'omni_purchase'` and use the `7d_click` attribution key unless the user asks otherwise. See `schema_insights`.
- **Timezone:** read `property_accounts.timezone_name` (often `America/Los_Angeles`). Convert vague phrases like "yesterday" to that timezone — see `concepts`.
- **Staleness:** `property_*.effective_status` may lag for idle ads. Prefer `insights.date_start >= current_date - 3` to detect recently delivering ads.
- **Multi-account:** filter `account_id` explicitly when more than one account is loaded.

## fb_audit scripts → tables

| Script | Tables written |
|---|---|
| `actions.ipynb` | `actions`, `actions_log` |
| `account_atribute.ipynb` | `property_accounts` |
| `campaign_atribute.ipynb` | `property_campaigns` |
| `adset_atribute.ipynb` | `property_adsets` |
| `ad_atribute.ipynb` | `property_ads` |
| `creative_atribute.ipynb` | `property_creatives` |
| `insights.ipynb` / `insights_update.ipynb` | `insights`, `insights_log` |
| `intraday_insights.py` | `intraday_insights` |
