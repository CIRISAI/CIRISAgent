-- Migration 006: Add unique index on (agent_occurrence_id, correlation_id)
--
-- Purpose: Prevent duplicate task creation for the same Reddit comment/post
--
-- Problem: Multiple observer polls can race and create duplicate tasks for the same
--          correlation_id (Reddit post/comment ID), causing duplicate replies.
--
-- Solution: Create a unique index on (agent_occurrence_id, correlation_id) extracted
--           from context_json to enforce uniqueness at the database level.
--
-- Note: SQLite supports JSON extraction in indexes since version 3.9.0 (2015)
--       Uses json_extract() function to pull correlation_id from context_json

CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_occurrence_correlation
ON tasks(agent_occurrence_id, json_extract(context_json, '$.correlation_id'))
WHERE json_extract(context_json, '$.correlation_id') IS NOT NULL;
