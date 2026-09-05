-- Reddit allowlist seeds (verified live at spec time: public, active).
-- Re-verify a sub before re-adding: drop the row if it stops resolving.
INSERT INTO sources (kind, url, name, market, active, poll_minutes) VALUES
    ('reddit', 'https://www.reddit.com/r/UnresolvedMysteries/', 'r/UnresolvedMysteries', 'US', true, 60),
    ('reddit', 'https://www.reddit.com/r/TrueCrime/',           'r/TrueCrime',           'US', true, 60)
ON CONFLICT DO NOTHING;
