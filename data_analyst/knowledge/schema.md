# Schema

## demo_campaigns
- `campaign_id` TEXT PK
- `campaign_name` TEXT
- `campaign_class` TEXT (`test` or `bau`)

## demo_ads
- `ad_id` TEXT PK
- `ad_name` TEXT
- `campaign_id` TEXT FK → `demo_campaigns`
- `creative_name` TEXT

## demo_insights_daily
- `ad_id` TEXT FK → `demo_ads`
- `date_start` DATE
- `spend` NUMERIC
- `impressions` BIGINT
- `clicks` BIGINT
- `purchases` INTEGER

Primary key: `(ad_id, date_start)`
