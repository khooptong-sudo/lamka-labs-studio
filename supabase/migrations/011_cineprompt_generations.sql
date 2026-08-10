-- supabase/migrations/011_cineprompt_generations.sql
-- Studio Cinema page: one row per saved CinePrompt + fal.run generation.
-- video_url is the original fal.run source, kept only for provenance — it
-- may 404 later since fal.run retention isn't guaranteed. local_path is
-- authoritative for playback.

CREATE TABLE IF NOT EXISTS cineprompt_generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    mode TEXT NOT NULL,
    model TEXT NOT NULL,
    fields JSONB NOT NULL,
    prompt TEXT NOT NULL,
    video_url TEXT NOT NULL,
    local_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cineprompt_generations_created_at
    ON cineprompt_generations (created_at DESC);
