# Schema: daily and intraday insights

**Pipeline:** Meta Ads API → `insights_update.ipynb` (daily), `intraday_insights.py` (intraday).

> **Default surface for fb_audit:** query `insights` directly at ad×day grain.
> Unlike full production stacks, fb_audit does **not** ship a pre-built
> `mv_insights_daily` materialized view. Aggregate `spend`, `impressions`,
> `clicks`, and extracted purchases in SQL.

---

## insights

**Purpose:** Raw daily ad performance from Meta API. Primary analyst table after fb_audit ETL.

**Granularity:** One row per `(account_id, campaign_id, adset_id, ad_id, date_start)`.

**Key columns:**
- `account_id`, `campaign_id`, `adset_id`, `ad_id` — VARCHAR(50). Always quote in WHERE.
- `date_start` — calendar date (UTC date column from Meta API).
- `spend` — NUMERIC, account currency (usually USD).
- `impressions`, `clicks`, `reach` — BIGINT.
- `actions` — JSONB array. Each element has `action_type` and attribution keys like `7d_click`, `1d_click`, `1d_view`.
- `results`, `cost_per_result` — JSONB for app-install / trial style outcomes (added in fb_audit 2026-04 refresh).

**Join keys:**
- `ad_id` → `property_ads.id`
- `campaign_id` → `property_campaigns.id`
- `adset_id` → `property_adsets.id`
- `account_id` → `property_accounts.id`

**Writer:** `insights.ipynb` (backfill) or `insights_update.ipynb` (incremental daily).

**Purchases extraction (canonical for dashboards):**

```sql
SELECT
  i.ad_id,
  i.date_start,
  SUM((elem->>'7d_click')::numeric) AS purchases
FROM insights i
CROSS JOIN LATERAL jsonb_array_elements(i.actions) AS elem
WHERE elem->>'action_type' = 'omni_purchase'
  AND elem->>'7d_click' IS NOT NULL
GROUP BY 1, 2;
```

**Gotchas:**
- Do not assume a `purchases` column exists — extract from `actions` or pre-aggregate in a CTE.
- Multiple attribution windows may exist on the same action; default to `7d_click` unless the user specifies otherwise.
- `insights` has a foreign key to `insights_log` — deleting a log row cascades to insights for that account×date.

---

## insights_log

**Purpose:** Fetch audit log — which `(account_id, date)` pairs were successfully loaded.

**Granularity:** One row per `(account_id, date)`.

**Key columns:** `account_id`, `date`, `with_data`, `recording_date`.

**Writer:** `insights_update.ipynb`.

**Gotchas:** Used by the ETL to decide which dates to re-fetch. Analysts rarely query it except for data-quality checks ("do we have yesterday loaded?").

---

## intraday_insights

**Purpose:** Current-day ad performance snapshot. Full delete+insert per account on each run.

**Granularity:** One row per ad per run (no primary key — table is replaced).

**Key columns:**
- `account_id`, `campaign_id`, `adset_id`, `ad_id` — **TEXT** (not VARCHAR).
- `date_start` — DATE.
- `spend`, `impressions`, `clicks` — **TEXT**. Cast before arithmetic: `spend::numeric`, `impressions::bigint`.
- `actions` — **TEXT** (JSON string). Cast: `actions::jsonb` before `jsonb_array_elements`.
- `collected_at` — timestamp of the snapshot.

**Writer:** `intraday_insights.py`.

**Gotchas:**
- Always cast TEXT metrics before SUM/ORDER BY.
- Filter to latest snapshot: `WHERE collected_at = (SELECT MAX(collected_at) FROM intraday_insights)`.
- Use for "today so far" questions; use `insights` for completed prior days.

---

## actions

**Purpose:** Meta activity log — budget changes, pauses, launches. Also drives incremental attribute refreshes.

**Granularity:** One row per activity event.

**Key columns:**
- `object_id` — Meta ID of changed entity (ad, campaign, adset).
- `account_id`, `date` — lookup keys.
- `actor_name`, `event_type`, `translated_event_type`.
- `extra_data` — JSONB with before/after values.

**Join keys:** `object_id` → `property_ads.id` / `property_campaigns.id` / `property_adsets.id`.

**Writer:** `actions.ipynb`.

**Gotchas:** Not for performance metrics — use `insights`. Useful for "when was this ad paused?" or "who changed the budget?".

---

## actions_log

**Purpose:** Fetch audit log for the actions pipeline. Same role as `insights_log` for actions.

**Granularity:** One row per `(id, date)` where `id` is account_id in practice.

**Writer:** `actions.ipynb`. Rarely queried by analysts.
