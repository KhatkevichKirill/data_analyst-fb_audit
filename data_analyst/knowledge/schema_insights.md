# Schema: daily and intraday insights

**Pipeline:** Meta Ads API → `insights_update.py` (daily), `insights.py` (backfill), `intraday_insights.py` (intraday).

> **Default surface for fb_audit:** query `v_insights_daily` for ad×day performance.
> It pre-extracts `purchases`, `trials`, and `video_views` from `insights` JSONB.
> Use raw `insights` only when you need a non-standard action type or attribution window.

`insights_update.py` skips days already in `insights_log` but **always re-fetches the last 7 days** for late attribution. That refetch is atomic per `(account, day)` — a failed API call leaves the previous snapshot intact.

Attribution windows: `1d_view`, `1d_click`, `7d_click`, `28d_click` (from `FB_GRAPH_API_VERSION`, default `v23.0`).

---

## v_insights_daily (view)

**Purpose:** Analyst-friendly daily metrics. Created by `schema/v_insights_daily.sql` in this starter kit.

**Granularity:** One row per `(ad_id, date_start)` — same as `insights`.

**Key columns:**
- `account_id`, `campaign_id`, `adset_id`, `ad_id`, `date_start`
- `spend`, `impressions`, `clicks`, `reach` — numeric (cast from TEXT upstream)
- `purchases`, `trials`, `video_views` — pre-extracted numeric columns
- `p25`, `p50`, `p75`, `p95` — video retention quartile sums

**Join keys:** same as `insights`.

**Gotchas:**
- Regular VIEW — always current, no refresh job. For large warehouses, optionally materialize (`schema/mv_insights_daily.sql.example`).
- Hook rate = `SUM(video_views) / NULLIF(SUM(impressions), 0)`.

---

## insights

**Purpose:** Raw daily ad performance from Meta API.

**Granularity:** One row per `(account_id, campaign_id, adset_id, ad_id, date_start)`.

**Key columns:**
- `account_id`, `campaign_id`, `adset_id`, `ad_id` — VARCHAR(50). Always quote in WHERE.
- `date_start`, `date_stop` — DATE
- `spend`, `impressions`, `clicks`, `reach` — **TEXT** from Meta API. Cast: `spend::numeric`, `impressions::bigint`.
- `actions`, `action_values`, `outbound_clicks`, `unique_actions`, `unique_outbound_clicks` — JSONB
- `results`, `cost_per_result` — JSONB (app installs / trials)
- `video_p25_watched_actions` … `video_p95_watched_actions` — JSONB

**Join keys:**
- `ad_id` → `property_ads.id`
- `campaign_id` → `property_campaigns.id`
- `adset_id` → `property_adsets.id`
- `account_id` → `property_accounts.id` or `property_accounts.account_id`

**Writer:** `insights.py` (backfill) or `insights_update.py` (incremental daily).

**Purchases extraction (when `v_insights_daily` unavailable):**

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
- No native `purchases` column — use `v_insights_daily` or extract from `actions`.
- Default attribution window: `7d_click`.
- FK to `insights_log` — deleting a log row cascades to insights for that account×date.

---

## insights_log

**Purpose:** Fetch audit log — which `(account_id, date)` pairs were successfully loaded.

**Granularity:** One row per `(account_id, date)`.

**Key columns:** `account_id`, `date`, `with_data`, `recording_date`.

**Writer:** `insights_update.py` / `insights.py`.

**Gotchas:** ETL uses this to skip already-loaded days. Analysts query it for freshness checks ("do we have yesterday loaded?").

---

## intraday_insights

**Purpose:** Current-day ad performance snapshot. Full delete+insert per account on each run (only after a complete fetch).

**Granularity:** One row per ad per run (no primary key — table is replaced per account).

**Key columns:**
- `account_id`, `campaign_id`, `adset_id`, `ad_id` — VARCHAR/TEXT
- `date_start`, `date_stop` — DATE
- `spend`, `impressions`, `clicks`, `reach` — **TEXT**. Cast before arithmetic.
- `actions`, `results`, `cost_per_result`, video JSONB columns — JSONB (not TEXT in current fb_audit)
- `collected_at` — timestamp of the snapshot (DEFAULT `now()`)

**Writer:** `intraday_insights.py`.

**Gotchas:**
- Cast TEXT metrics before SUM/ORDER BY.
- Filter to latest snapshot: `WHERE collected_at = (SELECT MAX(collected_at) FROM intraday_insights)`.
- Use for "today so far"; use `insights` / `v_insights_daily` for completed prior days.

---

## actions

**Purpose:** Meta activity log — budget changes, pauses, launches. Drives incremental attribute refreshes.

**Granularity:** One row per activity event.

**Key columns:**
- `object_id` — Meta ID of changed entity (ad, campaign, adset).
- `account_id`, `date` — lookup keys.
- `actor_name`, `event_type`, `translated_event_type`.
- `extra_data` — JSONB with before/after values.

**Join keys:** `object_id` → `property_ads.id` / `property_campaigns.id` / `property_adsets.id`.

**Writer:** `actions.py`.

**Gotchas:** Not for performance metrics — use `v_insights_daily`. Useful for "when was this ad paused?" or "who changed the budget?".

---

## actions_log

**Purpose:** Fetch audit log for the actions pipeline.

**Granularity:** One row per `(id, date)` where `id` is account_id in practice.

**Writer:** `actions.py`. Rarely queried by analysts.
