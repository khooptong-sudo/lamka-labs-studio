-- Keep the human-review Inbox focused on new, source-dated material.
-- Existing historical items remain stored; the worker uses this value to hide
-- them from the fresh-news queue and reject future stale feed entries.

UPDATE config
   SET value = jsonb_set(value, '{fresh_news_hours}', '48'::jsonb, true)
 WHERE key = 'ingest';
