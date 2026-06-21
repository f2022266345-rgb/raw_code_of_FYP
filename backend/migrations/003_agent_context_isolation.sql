-- Migration 003: Agent context isolation
-- Adds agent_type to episodic_memory so each agent's conversations
-- are stored separately in the vector DB while cross-agent context
-- can still be retrieved when needed.

ALTER TABLE episodic_memory
  ADD COLUMN IF NOT EXISTS agent_type VARCHAR(20) DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_episodic_user_agent
  ON episodic_memory(user_id, agent_type);

-- Backfill existing rows with NULL (they will be retrieved cross-agent)
-- No action needed — NULL agent_type rows remain globally retrievable.
