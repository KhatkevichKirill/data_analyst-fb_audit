-- Notebook sharing between authenticated users (read-only view access).

CREATE TABLE IF NOT EXISTS notebook_shares (
  notebook_id  BIGINT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  permission   TEXT NOT NULL DEFAULT 'view' CHECK (permission IN ('view')),
  created_by   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at   TIMESTAMPTZ,
  PRIMARY KEY (notebook_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_notebook_shares_user
  ON notebook_shares(user_id, revoked_at);

CREATE INDEX IF NOT EXISTS idx_notebook_shares_notebook
  ON notebook_shares(notebook_id, revoked_at);
