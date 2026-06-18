-- Add model routing metadata to cells (added 2026-05-29).
-- model_profile: the profile requested for this cell (or default).
-- actual_model_profile: the profile that produced the final answer (may differ if escalated).
-- routing_enabled: whether ROUTING_ENABLED was true when the cell ran.
-- escalated: whether the cell was routed to an escalation model.
-- escalation_reason: why escalation was triggered (if any).

ALTER TABLE cells ADD COLUMN IF NOT EXISTS model_profile TEXT;
ALTER TABLE cells ADD COLUMN IF NOT EXISTS actual_model_profile TEXT;
ALTER TABLE cells ADD COLUMN IF NOT EXISTS routing_enabled BOOLEAN;
ALTER TABLE cells ADD COLUMN IF NOT EXISTS escalated BOOLEAN DEFAULT FALSE;
ALTER TABLE cells ADD COLUMN IF NOT EXISTS escalation_reason TEXT;
