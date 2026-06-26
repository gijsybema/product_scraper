-- refresh_before_after.sql
-- Run on LOCAL DB before and after refresh_local_db.sh to compare state.
-- Usage in pgAdmin: run once before, note results; run again after, compare.

-- Row counts per table
SELECT 'retailers'    AS "table", COUNT(*) AS rows FROM retailers
UNION ALL
SELECT 'products',      COUNT(*) FROM products
UNION ALL
SELECT 'price_history', COUNT(*) FROM price_history
UNION ALL
SELECT 'price_drops',   COUNT(*) FROM price_drops
UNION ALL
SELECT 'scrape_runs',   COUNT(*) FROM scrape_runs
ORDER BY "table";

-- Date ranges of windowed tables
SELECT
  MIN(scraped_at)    AS price_history_oldest,
  MAX(scraped_at)    AS price_history_newest
FROM price_history;

SELECT
  MIN(new_scraped_at) AS price_drops_oldest,
  MAX(new_scraped_at) AS price_drops_newest
FROM price_drops;

SELECT
  MIN(started_at)    AS scrape_runs_oldest,
  MAX(started_at)    AS scrape_runs_newest
FROM scrape_runs;

-- Schema version: last applied migration (by filename convention)
-- Run manually in pgAdmin to confirm migrations landed:
--   \dt   (list tables)
--   \d products   (confirm columns like consecutive_404s, description, specs exist)
