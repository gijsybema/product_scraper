-- ==========================================
-- PRICE TRACKER: ANALYTICAL CHECKS (DESCRIPTIVES)
-- Purpose: volumes, trends, and useful summaries.
-- ==========================================

-- ------------------------------------------
-- PRODUCTS (analytics)
-- ------------------------------------------

-- Active vs inactive products
SELECT
  active,
  COUNT(*) AS product_count
FROM products
GROUP BY active
ORDER BY active DESC;


-- ------------------------------------------
-- PRICE_HISTORY (analytics)
-- ------------------------------------------



-- ------------------------------------------
-- PRICE_DROPS (analytics)
-- ------------------------------------------

-- Inspect today’s drops (largest first)
SELECT *
FROM price_drops
WHERE new_scraped_at = CURRENT_DATE
ORDER BY drop_percentage DESC;

-- Drops per day (historical volume)
SELECT
  new_scraped_at,
  COUNT(*) AS drops_count
FROM price_drops
GROUP BY new_scraped_at
ORDER BY new_scraped_at DESC
LIMIT 60;

-- How many products have ever dropped
SELECT COUNT(DISTINCT product_id) AS products_with_drops
FROM price_drops;

-- Biggest drops all-time (top 25)
SELECT
  pd.product_id,
  p.name,
  pd.old_price,
  pd.new_price,
  pd.drop_percentage,
  pd.new_scraped_at
FROM price_drops pd
JOIN products p ON p.id = pd.product_id
ORDER BY pd.drop_percentage DESC
LIMIT 25;

-- Preview eligible alerts today (10% drop, >= €150, in stock, not sent)
SELECT
  pd.product_id,
  p.name,
  pd.old_price,
  pd.new_price,
  pd.drop_percentage
FROM price_drops pd
JOIN products p ON p.id = pd.product_id
JOIN price_history ph
  ON ph.product_id = pd.product_id
 AND ph.scraped_at = CURRENT_DATE
WHERE pd.new_scraped_at = CURRENT_DATE
  AND pd.sent_at IS NULL
  AND pd.drop_percentage >= 10
  AND pd.new_price >= 150
  AND ph.availability = TRUE
ORDER BY pd.drop_percentage DESC;

-- ------------------------------------------
-- SCRAPE_RUNS (analytics)
-- ------------------------------------------


