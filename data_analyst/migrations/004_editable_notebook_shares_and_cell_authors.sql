-- Editable notebook sharing + per-cell authorship (added 2026-06-09).
--
-- Part A of the editable-sharing MVP:
--   1. notebook_shares.permission may now be 'view' OR 'edit'
--      ('edit' = shared editor, can add/run new cells in the owner's notebook).
--   2. cells.created_by_user_id records who created each cell.
--   3. Existing cells are backfilled to the owning notebook's user.
--
-- Idempotent: re-running drops/recreates the permission CHECK by whatever name
-- Postgres assigned it, and uses IF NOT EXISTS / NULL-guarded backfill.

-- 1. Extend the permission CHECK constraint to allow 'view' and 'edit'.
--    The live constraint name is inspected (not assumed) so this survives a
--    differently-named constraint from an earlier environment.
DO $$
DECLARE
  c text;
BEGIN
  SELECT conname INTO c
  FROM pg_constraint
  WHERE conrelid = 'notebook_shares'::regclass
    AND contype = 'c'
    AND pg_get_constraintdef(oid) ILIKE '%permission%';
  IF c IS NOT NULL THEN
    EXECUTE format('ALTER TABLE notebook_shares DROP CONSTRAINT %I', c);
  END IF;
END $$;

ALTER TABLE notebook_shares
  ADD CONSTRAINT notebook_shares_permission_check
  CHECK (permission IN ('view', 'edit'));

-- 2. Record the creating user on each cell.
ALTER TABLE cells
  ADD COLUMN IF NOT EXISTS created_by_user_id BIGINT REFERENCES users(id);

-- 3. Backfill existing cells to the notebook owner (only where unset).
UPDATE cells c
SET created_by_user_id = n.user_id
FROM notebooks n
WHERE c.notebook_id = n.id
  AND c.created_by_user_id IS NULL;
