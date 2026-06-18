-- Demo analytics warehouse for the public starter kit.

GRANT USAGE ON SCHEMA public TO data_analyst_ro;

CREATE TABLE IF NOT EXISTS demo_campaigns (
  campaign_id     TEXT PRIMARY KEY,
  campaign_name   TEXT NOT NULL,
  campaign_class  TEXT NOT NULL CHECK (campaign_class IN ('test', 'bau'))
);

CREATE TABLE IF NOT EXISTS demo_ads (
  ad_id          TEXT PRIMARY KEY,
  ad_name        TEXT NOT NULL,
  campaign_id    TEXT NOT NULL REFERENCES demo_campaigns(campaign_id),
  creative_name  TEXT
);

CREATE TABLE IF NOT EXISTS demo_insights_daily (
  ad_id         TEXT NOT NULL REFERENCES demo_ads(ad_id),
  date_start    DATE NOT NULL,
  spend         NUMERIC(12, 2) NOT NULL DEFAULT 0,
  impressions   BIGINT NOT NULL DEFAULT 0,
  clicks        BIGINT NOT NULL DEFAULT 0,
  purchases     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ad_id, date_start)
);

GRANT SELECT ON demo_campaigns, demo_ads, demo_insights_daily TO data_analyst_ro;

INSERT INTO demo_campaigns (campaign_id, campaign_name, campaign_class) VALUES
  ('cmp_test_01', 'Starter Test Alpha', 'test'),
  ('cmp_test_02', 'Starter Test Beta', 'test'),
  ('cmp_bau_01', 'Starter BAU Evergreen', 'bau')
ON CONFLICT (campaign_id) DO NOTHING;

INSERT INTO demo_ads (ad_id, ad_name, campaign_id, creative_name) VALUES
  ('ad_1001', 'Hook A - Reader', 'cmp_test_01', 'creative_reader_v1'),
  ('ad_1002', 'Hook B - Audiobook', 'cmp_test_01', 'creative_audio_v2'),
  ('ad_1003', 'Hook C - Productivity', 'cmp_test_02', 'creative_prod_v1'),
  ('ad_2001', 'Evergreen Main', 'cmp_bau_01', 'creative_evergreen_v3')
ON CONFLICT (ad_id) DO NOTHING;

INSERT INTO demo_insights_daily (ad_id, date_start, spend, impressions, clicks, purchases)
SELECT ad_id,
       (current_date - offs) AS date_start,
       round((50 + random() * 120)::numeric, 2) AS spend,
       (1000 + random() * 4000)::bigint AS impressions,
       (20 + random() * 90)::bigint AS clicks,
       CASE
         WHEN random() < 0.25 THEN 0
         ELSE (1 + random() * 4)::int
       END AS purchases
FROM demo_ads
CROSS JOIN generate_series(1, 14) AS offs
ON CONFLICT (ad_id, date_start) DO NOTHING;
