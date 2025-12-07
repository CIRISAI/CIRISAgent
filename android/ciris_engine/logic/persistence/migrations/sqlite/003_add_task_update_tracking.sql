-- Migration 003: Add task update tracking fields
-- Adds fields to support detecting when new observations arrive for an active task

-- Add updated_info_available flag
ALTER TABLE tasks ADD COLUMN updated_info_available INTEGER DEFAULT 0;

-- Add updated_info_content field
ALTER TABLE tasks ADD COLUMN updated_info_content TEXT DEFAULT NULL;
