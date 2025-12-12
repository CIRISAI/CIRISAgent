-- Migration: Add images_json column to tasks table for native multimodal vision support
-- Images are stored as JSON array of ImageContent objects on the TASK level
-- All thoughts associated with a task inherit images from their source task

ALTER TABLE tasks ADD COLUMN images_json TEXT;
