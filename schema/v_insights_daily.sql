-- Analyst-friendly view over fb_audit insights.
-- Regular VIEW (not materialized) — always in sync with insights, no refresh job.
-- Production stacks often use mv_insights_daily (materialized); see schema/mv_insights_daily.sql.example.

CREATE OR REPLACE VIEW v_insights_daily AS
SELECT
    i.account_id,
    i.campaign_id,
    i.adset_id,
    i.ad_id,
    i.date_start,
    i.impressions,
    i.clicks,
    i.spend,
    i.reach,
    -- purchases: omni_purchase, 7d_click window (matches production mv_insights_daily)
    COALESCE((
        SELECT SUM((elem->>'7d_click')::numeric)
        FROM jsonb_array_elements(COALESCE(i.actions, '[]'::jsonb)) elem
        WHERE elem->>'action_type' = 'omni_purchase'
          AND elem->>'7d_click' IS NOT NULL
    ), 0)::numeric AS purchases,
    -- trials: from results JSONB when present (fb_audit 2026-04+)
    COALESCE((
        SELECT SUM((v->>'value')::numeric)
        FROM jsonb_array_elements(COALESCE(i.results, '[]'::jsonb)) r_elem,
             jsonb_array_elements(COALESCE(r_elem->'values', '[]'::jsonb)) v
        WHERE r_elem->>'indicator' IN (
            'conversions:start_trial_mobile_app',
            'conversions:start_trial_website'
        )
          AND v->'attribution_windows' @> '["default"]'
    ), 0)::numeric AS trials,
    -- video_views: Meta 3-second views
    COALESCE((
        SELECT SUM(COALESCE(elem->>'value', elem->>'7d_click')::numeric)
        FROM jsonb_array_elements(COALESCE(i.actions, '[]'::jsonb)) elem
        WHERE elem->>'action_type' = 'video_view'
    ), 0)::numeric AS video_views,
    -- hook rate helper: video_views / impressions (compute at query time with NULLIF)
    COALESCE((
        SELECT SUM((e->>'value')::numeric)
        FROM jsonb_array_elements(COALESCE(i.video_p25_watched_actions, '[]'::jsonb)) e
    ), 0)::numeric AS p25,
    COALESCE((
        SELECT SUM((e->>'value')::numeric)
        FROM jsonb_array_elements(COALESCE(i.video_p50_watched_actions, '[]'::jsonb)) e
    ), 0)::numeric AS p50,
    COALESCE((
        SELECT SUM((e->>'value')::numeric)
        FROM jsonb_array_elements(COALESCE(i.video_p75_watched_actions, '[]'::jsonb)) e
    ), 0)::numeric AS p75,
    COALESCE((
        SELECT SUM((e->>'value')::numeric)
        FROM jsonb_array_elements(COALESCE(i.video_p95_watched_actions, '[]'::jsonb)) e
    ), 0)::numeric AS p95
FROM insights i;

GRANT SELECT ON v_insights_daily TO data_analyst_ro;

COMMENT ON VIEW v_insights_daily IS
  'Pre-extracted daily ad metrics from insights.actions/results. Prefer over raw insights for analyst queries.';
