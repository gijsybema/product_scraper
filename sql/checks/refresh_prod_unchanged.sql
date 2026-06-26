-- refresh_prod_unchanged.sql
-- Run on PROD DB (Railway) before and after refresh_local_db.sh to confirm
-- nothing was written to prod. Row counts and latest timestamps should be identical.
-- Connect pgAdmin to the Railway server, open Query Tool there, then run this.

-- Row counts
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

-- Most recent writes — these timestamps must not change after the refresh
SELECT MAX(created_at)  AS newest_product     FROM products;
SELECT MAX(scraped_at)  AS newest_price_entry FROM price_history;
SELECT MAX(created_at)  AS newest_price_drop  FROM price_drops;
SELECT MAX(started_at)  AS newest_scrape_run  FROM scrape_runs;
