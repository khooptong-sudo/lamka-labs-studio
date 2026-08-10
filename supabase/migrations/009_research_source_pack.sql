-- Research-first finance video sources.
--
-- Additive and idempotent: this must be applied after 008 to existing live
-- databases. These are primary regulator / investor-education feeds, chosen
-- to ground time-sensitive market and personal-finance scripts in sources an
-- editor can verify directly. No source auto-publishes or auto-generates.

-- The old seed used a retired SEC RSS address. Preserve the existing row and
-- point it at the official current feed rather than creating a second poller.
UPDATE sources
   SET url = 'https://www.sec.gov/news/pressreleases.rss',
       poll_minutes = 60,
       active = true
 WHERE name = 'SEC Press Releases';

INSERT INTO sources (kind, url, name, market, active, poll_minutes)
SELECT 'rss', v.url, v.name, v.market, true, v.poll_minutes
  FROM (
    VALUES
      ('https://rbi.org.in/pressreleases_rss.xml', 'RBI Press Releases', 'IN', 60),
      ('https://rbi.org.in/notifications_rss.xml', 'RBI Notifications', 'IN', 60),
      ('https://www.sebi.gov.in/sebirss.xml', 'SEBI Releases, Circulars & Orders', 'IN', 60),
      ('https://www.sec.gov/rss/investor/alertsandbulletins.xml', 'SEC Investor Alerts & Bulletins', 'US', 360)
  ) AS v(url, name, market, poll_minutes)
 WHERE NOT EXISTS (SELECT 1 FROM sources s WHERE s.url = v.url);
