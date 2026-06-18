-- analyst_app schema (run as svc_analyst_app, owner of the database).

CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    TEXT PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id            BIGSERIAL PRIMARY KEY,
  username      TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  is_admin      BOOLEAN NOT NULL DEFAULT FALSE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
  token       TEXT PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS notebooks (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title          TEXT NOT NULL DEFAULT 'Untitled',
  workspace_dir  TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notebooks_user ON notebooks(user_id, archived_at, updated_at DESC);

CREATE TABLE IF NOT EXISTS cells (
  id            BIGSERIAL PRIMARY KEY,
  notebook_id   BIGINT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
  position      INT NOT NULL,
  prompt        TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('pending','running','done','error','cancelled')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at  TIMESTAMPTZ,
  UNIQUE (notebook_id, position)
);
CREATE INDEX IF NOT EXISTS idx_cells_notebook ON cells(notebook_id, position);

CREATE TABLE IF NOT EXISTS events (
  id          BIGSERIAL PRIMARY KEY,
  cell_id     BIGINT NOT NULL REFERENCES cells(id) ON DELETE CASCADE,
  seq         INT NOT NULL,
  type        TEXT NOT NULL,
  payload     JSONB NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (cell_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_events_cell ON events(cell_id, seq);
