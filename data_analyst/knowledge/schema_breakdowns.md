# Schema: demographic and placement breakdowns

**Pipeline:** Meta Ads API → `insights_breakdowns_update.py`.

**DDL:** `schema_breakdowns.sql` in [fb_audit](https://github.com/KhatkevichKirill/fb_audit) (tables are also created at runtime by the loader).

> Meta does **not** allow age×gender and placement breakdowns in a single API call — fb_audit runs two separate fetches per day.

Same incremental + **atomic last-7-day refetch** logic as `insights_update.py`: old rows for an `(account, day)` are replaced only after a successful fetch, inside one transaction.

---

## insights_breakdowns_demographic

**Purpose:** Daily ad performance split by age and gender.

**Granularity:** One row per `(ad_id, date_start, age, gender)`.

**Key columns:**
- `account_id`, `campaign_id`, `adset_id`, `ad_id` — TEXT
- `date_start`, `date_stop` — DATE
- `age` — e.g. `'18-24'`, `'25-34'`, `'35-44'`, `'45-54'`, `'55-64'`, `'65+'`
- `gender` — `'male'`, `'female'`, `'unknown'`
- `spend`, `impressions`, `clicks`, `reach` — **TEXT**; cast: `spend::numeric`
- `actions`, `results`, `cost_per_result` — JSONB (same shape as `insights`)
- `video_p25_watched_actions` … `video_p95_watched_actions` — JSONB

**Join keys:** `ad_id` → `property_ads.id`; hierarchy IDs match `insights`.

**Writer:** `insights_breakdowns_update.py` (demographic pass).

**Purchases extraction:** same JSONB pattern as `insights` — `actions` where `action_type = 'omni_purchase'`, default window `7d_click`. No pre-built view; aggregate in SQL or use `v_insights_daily` for ad-level totals.

---

## insights_breakdowns_demographic_log

**Purpose:** Fetch audit log for demographic breakdowns — which `(account_id, date)` pairs were loaded.

**Granularity:** One row per `(account_id, date)`.

**Columns:** `account_id`, `date`, `with_data`, `recording_date`.

---

## insights_breakdowns_placement

**Purpose:** Daily ad performance split by publisher, position, and device.

**Granularity:** One row per `(ad_id, date_start, publisher_platform, platform_position, impression_device)`.

**Key columns:**
- `publisher_platform` — `facebook`, `instagram`, `audience_network`, `messenger`
- `platform_position` — `feed`, `reels`, `story`, `an_classic`, etc.
- `impression_device` — `mobile_app`, `desktop`, `mobile_web`
- Metrics — same TEXT + JSONB pattern as demographic table

**Writer:** `insights_breakdowns_update.py` (placement pass).

---

## insights_breakdowns_placement_log

**Purpose:** Fetch audit log for placement breakdowns.

Same shape as `insights_breakdowns_demographic_log`.

---

## Query patterns

### Spend by gender (7 days)

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

### Spend by platform (7 days)

```sql
SELECT
  publisher_platform,
  round(sum(spend::numeric), 2) AS spend
FROM insights_breakdowns_placement
WHERE date_start >= current_date - 7
GROUP BY 1
ORDER BY spend DESC;
```

---

## Gotchas

- Breakdown dimensions must **not** appear in API `fields` — they come from the `breakdowns` parameter only.
- Cast TEXT metrics before `SUM` / `ORDER BY`.
- Do not sum breakdown rows to reconcile account totals without deduplication — use `v_insights_daily` or `insights` for official ad×day totals.
- Optional `REFRESH_BREAKDOWN_MVS` env in fb_audit refreshes materialized views if you add them; the open-source repo ships base tables only.

## When tables are absent

1. Check `information_schema.tables` for `insights_breakdowns_*`.
2. If absent, tell the user to run `psql -f schema_breakdowns.sql` then `python insights_breakdowns_update.py`.
3. Do not invent age/gender/placement splits from `insights` alone — that table has no breakdown dimensions.
