-- Reference copy of the analyst_app schema.
-- The web app normally applies data_analyst/migrations/*.sql automatically on boot.

\connect analyst_app

CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    TEXT PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
