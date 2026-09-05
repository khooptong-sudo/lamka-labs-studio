-- Topic feeds for the history + science channels (verified live 2026-09-05:
-- HTTP 200, valid RSS/Atom, dated English entries, topical fit).
-- Idempotent like 003: ON CONFLICT DO NOTHING so re-running is safe.
-- market is a US/IN geography CHECK from the finance lanes; all publishers
-- below are US/global, so 'US'. Freshness (48h) and scoring apply unchanged.

-- Science channel.
INSERT INTO sources (kind, url, name, market, active, poll_minutes) VALUES
    ('rss', 'https://www.nasa.gov/rss/dyn/breaking_news.rss', 'NASA Breaking News',   'US', true, 30),
    ('rss', 'https://www.quantamagazine.org/feed/',            'Quanta Magazine',       'US', true, 30),
    ('rss', 'https://www.sciencedaily.com/rss/top/science.xml', 'ScienceDaily Top',    'US', true, 30),
    ('rss', 'https://phys.org/rss-feed/',                      'Phys.org',              'US', true, 30),
    ('rss', 'https://arstechnica.com/science/feed/',           'Ars Technica Science',  'US', true, 30)
ON CONFLICT DO NOTHING;

-- History channel.
INSERT INTO sources (kind, url, name, market, active, poll_minutes) VALUES
    ('rss', 'https://www.historyextra.com/feed/', 'BBC History Magazine', 'US', true, 30),
    ('rss', 'https://daily.jstor.org/feed/',      'JSTOR Daily',          'US', true, 30),
    ('rss', 'https://www.history.com/news/feed',  'History.com News',     'US', true, 30)
ON CONFLICT DO NOTHING;
-- Rejected in verification: smithsonianmag /rss/latest (404), /rss (200 but
-- zero entries), history.com/rss and /feed (404). Do not re-add without re-verifying.
