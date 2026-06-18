-- fb_audit-compatible warehouse schema + synthetic seed data.
-- Matches tables created by https://github.com/KhatkevichKirill/fb_audit notebooks.

GRANT USAGE ON SCHEMA public TO data_analyst_ro;

-- ── Entity attributes (property_*) ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS property_accounts (
  id                          VARCHAR(50) PRIMARY KEY,
  account_id                  VARCHAR(50),
  name                        VARCHAR(200),
  timezone_name               VARCHAR(50),
  timezone_offset_hours_utc   INT,
  currency                    VARCHAR(5),
  account_status              INT,
  recording_date              TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS property_campaigns (
  id                VARCHAR(50) PRIMARY KEY,
  account_id        VARCHAR(50),
  name              VARCHAR(200),
  objective         VARCHAR(50),
  effective_status  VARCHAR(20),
  status            VARCHAR(20),
  daily_budget      BIGINT,
  lifetime_budget   BIGINT,
  recording_date    TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS property_adsets (
  id                  VARCHAR(50) PRIMARY KEY,
  account_id          VARCHAR(50),
  campaign_id         VARCHAR(50),
  name                VARCHAR(200),
  campaign            JSONB,
  optimization_goal   VARCHAR(50),
  effective_status    VARCHAR(20),
  daily_budget        BIGINT,
  targeting           JSONB,
  recording_date      TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS property_ads (
  id                VARCHAR(50) PRIMARY KEY,
  account_id        VARCHAR(50),
  campaign_id       VARCHAR(50),
  adset_id          VARCHAR(50),
  name              VARCHAR(200),
  creative          JSONB,
  effective_status  VARCHAR(20),
  status            VARCHAR(20),
  recording_date    TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS property_creatives (
  id                 VARCHAR(50) PRIMARY KEY,
  account_id         VARCHAR(50),
  video_id           VARCHAR(50),
  image_hash         VARCHAR(100),
  thumbnail_url      TEXT,
  object_story_spec  JSONB,
  recording_date     TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS deleted_objects (
  object_id       VARCHAR(50) PRIMARY KEY,
  account_id      VARCHAR(50),
  object_type     VARCHAR(20),
  recording_date  TIMESTAMP WITHOUT TIME ZONE
);

-- ── Insights ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insights_log (
  account_id      VARCHAR(50),
  date            DATE,
  with_data       BOOLEAN,
  recording_date  TIMESTAMP WITHOUT TIME ZONE,
  PRIMARY KEY (account_id, date)
);

CREATE TABLE IF NOT EXISTS insights (
  account_id       VARCHAR(50),
  campaign_id      VARCHAR(50),
  adset_id         VARCHAR(50),
  ad_id            VARCHAR(50),
  date_start       DATE,
  impressions      BIGINT,
  clicks           BIGINT,
  spend            NUMERIC,
  reach            BIGINT,
  actions          JSONB,
  results          JSONB,
  cost_per_result  JSONB,
  video_p25_watched_actions JSONB,
  video_p50_watched_actions JSONB,
  video_p75_watched_actions JSONB,
  video_p95_watched_actions JSONB,
  PRIMARY KEY (account_id, campaign_id, adset_id, ad_id, date_start),
  FOREIGN KEY (account_id, date_start)
    REFERENCES insights_log(account_id, date) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS intraday_insights (
  account_id      TEXT,
  campaign_id     TEXT,
  adset_id        TEXT,
  ad_id           TEXT,
  date_start      DATE,
  spend           TEXT,
  impressions     TEXT,
  clicks          TEXT,
  actions         TEXT,
  collected_at    TIMESTAMP WITHOUT TIME ZONE
);

-- ── Actions ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS actions_log (
  id              VARCHAR(50),
  date            DATE,
  with_data       BOOLEAN,
  recording_date  TIMESTAMP WITHOUT TIME ZONE,
  PRIMARY KEY (id, date)
);

CREATE TABLE IF NOT EXISTS actions (
  account_id               VARCHAR(50),
  date                     DATE,
  actor_id                 VARCHAR(100),
  actor_name               VARCHAR(100),
  event_time               TIMESTAMP,
  event_type               VARCHAR(100),
  translated_event_type    VARCHAR(100),
  object_id                VARCHAR(100),
  object_name              VARCHAR(200),
  object_type              VARCHAR(100),
  extra_data               JSONB,
  id                       VARCHAR(100),
  FOREIGN KEY (account_id, date) REFERENCES actions_log(id, date) ON UPDATE CASCADE
);

GRANT SELECT ON ALL TABLES IN SCHEMA public TO data_analyst_ro;

-- ── Seed data ────────────────────────────────────────────────────────────────

INSERT INTO property_accounts (id, account_id, name, timezone_name, timezone_offset_hours_utc, currency, account_status, recording_date)
VALUES ('1000000001', '1000000001', 'Demo Ad Account', 'America/Los_Angeles', -8, 'USD', 1, now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO property_campaigns (id, account_id, name, objective, effective_status, status, daily_budget, recording_date) VALUES
  ('2000000001', '1000000001', 'Demo Prospecting', 'OUTCOME_SALES', 'ACTIVE', 'ACTIVE', 50000, now()),
  ('2000000002', '1000000001', 'Demo Retargeting', 'OUTCOME_SALES', 'ACTIVE', 'ACTIVE', 30000, now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO property_adsets (id, account_id, campaign_id, name, optimization_goal, effective_status, daily_budget, recording_date) VALUES
  ('3000000001', '1000000001', '2000000001', 'Broad US', 'OFFSITE_CONVERSIONS', 'ACTIVE', 25000, now()),
  ('3000000002', '1000000001', '2000000002', 'Site visitors 30d', 'OFFSITE_CONVERSIONS', 'ACTIVE', 15000, now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO property_creatives (id, account_id, video_id, thumbnail_url, object_story_spec, recording_date) VALUES
  ('5000000001', '1000000001', 'v001', 'https://example.com/thumb1.jpg', '{"link_data":{"message":"Try the app"}}'::jsonb, now()),
  ('5000000002', '1000000001', 'v002', 'https://example.com/thumb2.jpg', '{"link_data":{"message":"Listen on the go"}}'::jsonb, now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO property_ads (id, account_id, campaign_id, adset_id, name, creative, effective_status, status, recording_date) VALUES
  ('4000000001', '1000000001', '2000000001', '3000000001', 'Hook A', '{"id":"5000000001"}'::jsonb, 'ACTIVE', 'ACTIVE', now()),
  ('4000000002', '1000000001', '2000000001', '3000000001', 'Hook B', '{"id":"5000000002"}'::jsonb, 'ACTIVE', 'ACTIVE', now()),
  ('4000000003', '1000000001', '2000000002', '3000000002', 'Retarget v1', '{"id":"5000000001"}'::jsonb, 'ACTIVE', 'ACTIVE', now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO insights_log (account_id, date, with_data, recording_date)
SELECT '1000000001', (current_date - offs)::date, true, now()
FROM generate_series(0, 13) AS offs
ON CONFLICT DO NOTHING;

INSERT INTO insights (account_id, campaign_id, adset_id, ad_id, date_start, impressions, clicks, spend, reach, actions)
SELECT
  '1000000001',
  a.campaign_id,
  a.adset_id,
  a.ad_id,
  (current_date - offs)::date,
  (1000 + random() * 4000)::bigint,
  (20 + random() * 90)::bigint,
  round((40 + random() * 120)::numeric, 2),
  (800 + random() * 3000)::bigint,
  jsonb_build_array(
    jsonb_build_object('action_type', 'omni_purchase', '7d_click', (CASE WHEN random() < 0.3 THEN 0 ELSE (1 + random() * 4)::int END)::text),
    jsonb_build_object('action_type', 'video_view', '7d_click', (50 + random() * 200)::int::text)
  )
FROM (
  SELECT id AS ad_id, campaign_id, adset_id FROM property_ads
) a
CROSS JOIN generate_series(0, 13) AS offs
ON CONFLICT DO NOTHING;

INSERT INTO intraday_insights (account_id, campaign_id, adset_id, ad_id, date_start, spend, impressions, clicks, actions, collected_at)
SELECT
  i.account_id,
  i.campaign_id,
  i.adset_id,
  i.ad_id,
  current_date,
  i.spend::text,
  i.impressions::text,
  i.clicks::text,
  i.actions::text,
  now()
FROM insights i
WHERE i.date_start = current_date - 1
LIMIT 3
ON CONFLICT DO NOTHING;

INSERT INTO actions_log (id, date, with_data, recording_date)
VALUES ('1000000001', current_date - 1, true, now())
ON CONFLICT DO NOTHING;

INSERT INTO actions (account_id, date, actor_id, actor_name, event_time, event_type, translated_event_type, object_id, object_name, object_type, extra_data, id)
VALUES (
  '1000000001', current_date - 1, 'user1', 'Demo User', now() - interval '1 day',
  'update_ad_set_budget', 'Updated ad set budget', '3000000001', 'Broad US', 'ADSET',
  '{"old_value":20000,"new_value":25000}'::jsonb, 'evt_001'
)
ON CONFLICT DO NOTHING;
