-- Reddit permission rights (one row per collected post).
--
-- Also widens sources.kind: reddit rows cannot be seeded while the 001
-- CHECK only names rss/edgar/nse/calendar/internal.
ALTER TABLE sources DROP CONSTRAINT IF EXISTS sources_kind_check;
ALTER TABLE sources ADD CONSTRAINT sources_kind_check
    CHECK (kind IN ('rss','edgar','nse','calendar','internal','reddit'));

CREATE TABLE IF NOT EXISTS reddit_rights (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id     text NOT NULL,
    author      text NOT NULL DEFAULT '',
    subreddit   text NOT NULL DEFAULT '',
    post_url    text NOT NULL UNIQUE,
    state       text NOT NULL DEFAULT 'candidate'
                CHECK (state IN ('candidate','pm_approved','sent','granted','denied','expired','review')),
    pm_text     text NOT NULL DEFAULT '',
    send_count  integer NOT NULL DEFAULT 0,
    sent_at     timestamptz,
    decided_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rights_state ON reddit_rights (state);
CREATE INDEX IF NOT EXISTS idx_rights_author ON reddit_rights (author);
