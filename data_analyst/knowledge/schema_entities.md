# Schema: entity attributes

**Pipeline:** Meta Ads API → `*_atribute.py` scripts.

**DDL:** `schema_properties.sql` in [fb_audit](https://github.com/KhatkevichKirill/fb_audit).

**Refresh cadence:** incremental — entities with recent `actions` events or new rows in `insights` get re-fetched. Idle paused entities may stay stale. Objects in `deleted_objects` are skipped.

> For "is this ad delivering now?" filter on recent `insights.date_start` with spend > 0, not only `effective_status`.

**Column types:** fb_audit stores almost all API fields as **TEXT** (wide tables — 50–70+ columns per entity). Scripts insert only columns that exist (`get_table_columns` filter). The docker demo uses a **subset** of columns for readability; real warehouses match `schema_properties.sql`.

---

## property_accounts

**Purpose:** Ad account metadata — currency, timezone, status.

**Key columns:**
- `id`, `account_id` — TEXT (often the same numeric string)
- `timezone_name` — e.g. `America/Los_Angeles`. Use for date-window interpretation.
- `currency` — e.g. `USD`. All `insights.spend` is in this currency.
- `name` — human-readable account label.

**Join:** `id` or `account_id` → `insights.account_id`.

**Writer:** `account_atribute.py`.

---

## property_campaigns

**Purpose:** Campaign metadata — objective, status, budget.

**Key columns:**
- `id` — Meta campaign ID (TEXT)
- `account_id`, `name`, `objective`
- `effective_status` — `ACTIVE`, `PAUSED`, `ARCHIVED`, etc. May be stale for idle campaigns.
- `daily_budget`, `lifetime_budget` — TEXT, values in **cents**. `daily_budget::numeric / 100` for dollars.

**Join:** `id` → `insights.campaign_id`.

**Writer:** `campaign_atribute.py` (delete-then-insert on refresh).

---

## property_adsets

**Purpose:** Ad set metadata — targeting, optimization, budget.

**Key columns:**
- `id` — TEXT
- `campaign_id` — direct column (prefer over `campaign` TEXT blob for joins).
- `campaign` — TEXT JSON backup; parse if `campaign_id` is null.
- `optimization_goal`, `targeting` (TEXT), `effective_status`
- `daily_budget` — TEXT, cents

**Join:** `id` → `insights.adset_id`.

**Writer:** `adset_atribute.py`.

---

## property_ads

**Purpose:** Ad-level metadata — name, status, creative link.

**PK:** `id` (TEXT PRIMARY KEY — only property table with explicit PK in fb_audit DDL).

**Key columns:**
- `campaign_id`, `adset_id`, `name`
- `creative` — JSONB; `creative->>'id'` = Meta creative entity ID.
- `effective_status`, `status`

**Join:** `id` → `insights.ad_id`; `creative->>'id'` → `property_creatives.id`.

**Writer:** `ad_atribute.py` (upsert on `id`).

---

## property_creatives

**Purpose:** Creative entity metadata — video/image assets, copy, CTA, UTM.

**Key columns:**
- `id` — TEXT
- `video_id`, `image_hash`, `thumbnail_url`, `body`, `title`, `call_to_action_type`, `url_tags`
- `object_story_spec` — TEXT (JSON string from API)

**Join:** `id` ← `property_ads.creative->>'id'`.

**Writer:** `creative_atribute.py`.

---

## deleted_objects

**Purpose:** Tombstone for Meta objects that returned delete/not-accessible errors (codes 100/33, 100/1487221).

**Columns:** `object_id`, `account_id`, `object_type`, `updated_at` (TIMESTAMP).

**Use:** explain missing attribute rows; ETL skips these in future candidate sets.

**Writer:** any `*_atribute.py` on 404-style Meta errors via `store_deleted_object` in `utils.py`.
