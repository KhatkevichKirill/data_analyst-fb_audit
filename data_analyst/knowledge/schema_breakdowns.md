# Schema: demographic and placement breakdowns

## Not included in core fb_audit

The [fb_audit](https://github.com/KhatkevichKirill/fb_audit) ETL loads:

- entity attributes (`property_*`)
- daily insights (`insights`)
- intraday snapshot (`intraday_insights`)
- change log (`actions`)

It does **not** load demographic (age × gender) or placement breakdowns. Those require a separate Meta Insights API call with `breakdowns` parameters and additional tables.

If you only run fb_audit, answer account-level and ad-level questions from `insights` + `property_*`. Do not query breakdown tables unless you added them yourself.

---

## Optional extension tables

If you extend your warehouse with a breakdowns pipeline, these are the usual shapes (based on common Meta Ads warehouse patterns):

### insights_breakdowns_demographic

**Granularity:** One row per `(ad_id, date_start, age, gender)`.

**Key columns:**
- `ad_id`, `account_id`, `campaign_id`, `adset_id`
- `age` — e.g. `'18-24'`, `'25-34'`, …
- `gender` — `'male'`, `'female'`, `'unknown'`
- `spend`, `impressions`, `clicks` — often **TEXT** in raw tables; cast before arithmetic
- `purchases` — sometimes pre-extracted as numeric
- `actions` — text-encoded JSON in raw storage

**Gotchas:** Meta does not provide a single API call that combines age×gender×placement — demographic and placement breakdowns are separate fetches.

### insights_breakdowns_placement

**Granularity:** One row per `(ad_id, date_start, publisher_platform, platform_position, impression_device)`.

**Key columns:**
- `publisher_platform` — `facebook`, `instagram`, `audience_network`, `messenger`
- `platform_position` — `feed`, `reels`, `story`, etc.
- `impression_device` — `mobile_app`, `desktop`, `mobile_web`

### Materialized views (production pattern)

Full production stacks sometimes add pre-aggregated matviews such as `mv_bd_demo` (account×day×age×gender) and `mv_bd_plac` (account×day×placement). fb_audit does not create these — add them only if you build a breakdown ETL and refresh job.

---

## When users ask for breakdowns without tables present

1. Check `information_schema.tables` or the schema crib for `insights_breakdowns_*`.
2. If absent, tell the user breakdown data is not loaded yet and suggest extending fb_audit with a breakdown fetch script.
3. Do not invent breakdown numbers from `insights` alone — that table has no age/gender/placement dimensions.
