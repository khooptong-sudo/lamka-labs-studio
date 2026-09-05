-- Overnight-autopilot queue flag. NULL = not queued. Status untouched.
ALTER TABLE stories ADD COLUMN IF NOT EXISTS autopilot_queued_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_stories_autopilot_queue ON stories (autopilot_queued_at)
    WHERE autopilot_queued_at IS NOT NULL;
