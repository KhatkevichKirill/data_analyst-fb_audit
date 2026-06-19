# Data catalog — fb_audit warehouse

Read this first when the question is about performance, entity metadata, breakdowns, or change history loaded by [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

## Domains

| Domain | What you can answer | Deep-dive |
|---|---|---|
| Entity attributes | Account, campaign, adset, ad, creative metadata | `schema_entities` |
| Daily insights | Spend, impressions, clicks, purchases at ad×day | `schema_insights` |
| Breakdowns | Age×gender or placement splits | `schema_breakdowns` |
| Intraday | Today-so-far snapshot | `schema_insights` |
| Change log | Who paused/changed budget and when | `schema_insights` (actions) |
| Tombstones | Deleted/inaccessible Meta objects | `schema_entities` (deleted_objects) |

## Quick lookup

| Question | Page | Primary table |
|---|---|---|
| Daily spend / purchases / CPA trend | `schema_insights` | `v_insights_daily` |
| Spend by age × gender | `schema_breakdowns` | `insights_breakdowns_demographic` |
| Spend by placement / device | `schema_breakdowns` | `insights_breakdowns_placement` |
| Hourly / today spend | `schema_insights` | `intraday_insights` |
| Campaign or ad names / status | `schema_entities` | `property_campaigns`, `property_ads` |
| Who changed a budget yesterday | `schema_insights` | `actions` |
| Account timezone / currency | `schema_entities` | `property_accounts` |

## Cross-cutting conventions

- **IDs are VARCHAR/TEXT.** Always quote: `WHERE ad_id = '4000000001'`.
- **Default performance surface:** `v_insights_daily` view — numeric `purchases`, `video_views`, `trials` pre-extracted from `insights`. Fall back to raw `insights` only for non-standard action types.
- **Raw metric columns are often TEXT** on `insights`, breakdown tables, and `property_*` budgets. Cast before arithmetic: `spend::numeric`, `daily_budget::numeric / 100`.
- **Purchases:** default `omni_purchase` with `7d_click` attribution — already in `v_insights_daily.purchases`.
- **Timezone:** read `property_accounts.timezone_name` (often `America/Los_Angeles`). See `concepts`.
- **Staleness:** `property_*.effective_status` may lag for idle ads. Prefer recent `insights.date_start` with spend > 0.
- **Multi-account:** filter `account_id` explicitly when more than one account is loaded.

## fb_audit scripts → tables

DDL: `schema_properties.sql` (entity tables), `schema_breakdowns.sql` (breakdown tables). Insights/actions tables are created at runtime by the loaders.

| Script | Tables written |
|---|---|
| `actions.py` | `actions`, `actions_log` |
| `account_atribute.py` | `property_accounts` |
| `campaign_atribute.py` | `property_campaigns` |
| `adset_atribute.py` | `property_adsets` |
| `ad_atribute.py` | `property_ads` |
| `creative_atribute.py` | `property_creatives` |
| `insights.py` | `insights`, `insights_log` (date-range backfill) |
| `insights_update.py` | `insights`, `insights_log` (incremental + atomic last-7-day refetch) |
| `insights_breakdowns_update.py` | `insights_breakdowns_demographic`, `insights_breakdowns_placement`, `*_log` |
| `intraday_insights.py` | `intraday_insights` |
| *(analyst starter)* | `v_insights_daily` view over `insights` |

Backfill wrappers: `backfill/backfill_insights.sh`, `backfill_actions.sh`, `backfill_insights_breakdowns.sh`.
