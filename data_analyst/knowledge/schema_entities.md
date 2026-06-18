# Schema: entity attributes

**Pipeline:** Meta Ads API → `*_atribute.ipynb` scripts.

**Refresh cadence:** incremental — entities with recent `actions` events or new rows in `insights` get re-fetched. Idle paused entities may stay stale.

> For "is this ad delivering now?" filter on recent `insights.date_start`, not only `effective_status`.

---

## property_accounts

**Purpose:** Ad account metadata — currency, timezone, status.

**PK:** `id` (same value as `account_id` in most rows).

**Key columns:**
- `timezone_name` — e.g. `America/Los_Angeles`. Use for date-window interpretation.
- `currency` — e.g. `USD`. All `insights.spend` is in this currency.
- `name` — human-readable account label.

**Join:** `id` → `insights.account_id`, `property_campaigns.account_id`.

**Writer:** `account_atribute.ipynb`.

---

## property_campaigns

**Purpose:** Campaign metadata — objective, status, budget.

**PK:** `id` (Meta campaign ID).

**Key columns:**
- `account_id`, `name`, `objective`
- `effective_status` — `ACTIVE`, `PAUSED`, `ARCHIVED`, etc. May be stale for idle campaigns.
- `daily_budget`, `lifetime_budget` — in **cents** (Meta API convention). Divide by 100 for dollars.

**Join:** `id` → `insights.campaign_id`.

**Writer:** `campaign_atribute.ipynb`.

---

## property_adsets

**Purpose:** Ad set metadata — targeting, optimization, budget.

**PK:** `id`.

**Key columns:**
- `campaign_id` — direct column (prefer over `campaign` JSONB for joins).
- `campaign` — JSONB backup; `campaign->>'id'` if `campaign_id` is null.
- `optimization_goal`, `targeting` (JSONB), `effective_status`
- `daily_budget` — cents

**Join:** `id` → `insights.adset_id`.

**Writer:** `adset_atribute.ipynb`.

---

## property_ads

**Purpose:** Ad-level metadata — name, status, creative link.

**PK:** `id` (Meta ad ID — primary join key to `insights.ad_id`).

**Key columns:**
- `campaign_id`, `adset_id`, `name`
- `creative` — JSONB; `creative->>'id'` = Meta creative entity ID (different namespace from `ad_id`).
- `effective_status`, `status`

**Join:** `id` → `insights.ad_id`; `creative->>'id'` → `property_creatives.id`.

**Writer:** `ad_atribute.ipynb` (upsert on `id`).

---

## property_creatives

**Purpose:** Creative entity metadata — video/image assets, story spec.

**PK:** `id` (Meta creative entity ID).

**Key columns:**
- `video_id`, `image_hash`, `thumbnail_url`
- `object_story_spec` — JSONB with ad copy, CTA, link

**Join:** `id` ← `property_ads.creative->>'id'`.

**Writer:** `creative_atribute.ipynb`.

---

## deleted_objects

**Purpose:** Tombstone for Meta objects that returned delete/not-accessible errors (codes 100/33, 100/1487221).

**PK:** `object_id`.

**Columns:** `object_id`, `account_id`, `object_type`, `recording_date`.

**Use:** explain missing attribute rows; exclude from refresh candidate sets in ETL.
