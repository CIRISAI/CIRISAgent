-- Migration: Add images_json column to tasks table
-- For native multimodal vision support
ALTER TABLE tasks ADD COLUMN images_json TEXT;
