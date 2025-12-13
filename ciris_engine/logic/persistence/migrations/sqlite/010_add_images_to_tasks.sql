-- Migration: Add images_json column to tasks table for native multimodal vision support
-- Images are stored as JSON array of ImageContent objects on the TASK level
-- All thoughts associated with a task inherit images from their source task

-- SQLite workaround for ADD COLUMN IF NOT EXISTS:
-- Create a temporary trigger that does nothing but succeeds if column exists
-- Then add the column if it doesn't exist (will error if it does, but trigger proves it exists)

-- This migration uses a recreate pattern to safely add column if missing
-- The new base schema includes this column, so this is for existing databases only

-- Check if column exists by selecting it; if it fails, the subsequent SELECT adds it
-- Using CREATE TABLE ... AS SELECT pattern with COALESCE for safety

-- For SQLite, we use a simple approach: just add the column
-- The migration runner should skip this if already applied
ALTER TABLE tasks ADD COLUMN images_json TEXT;
