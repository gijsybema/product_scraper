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


-- Deactivation health check: active flag, OOS streak, and 404 counts per product
-- status column quick-read:
--   'active / in stock'       normal
--   'oos streak in progress'  building toward threshold, not yet deactivated
--   '⚠ should be deactivated' streak >= 30 but still active (not yet caught by scraper)
--   'deactivated: oos'        caught by OOS streak logic
--   'deactivated: 404s'       caught by repeated-404 logic
--   'deactivated: unknown'    inactive for another reason
-- first_scraped_date helps interpret NULL last_in_stock_date:
--   if first_scraped_date = last_scraped and last_in_stock_date IS NULL,
--   the product has been OOS since it was first discovered.
WITH last_in_stock AS (
    SELECT
        product_id,
        MAX(scraped_at) AS last_in_stock_date
    FROM price_history
    WHERE availability = true
    GROUP BY product_id
),
first_and_last_scraped AS (
    SELECT
        product_id,
        MIN(scraped_at) AS first_scraped_date,
        MAX(scraped_at) AS last_scraped_date
    FROM price_history
    GROUP BY product_id
),
oos_streak AS (
    SELECT
        ph.product_id,
        COUNT(DISTINCT ph.scraped_at) AS consecutive_oos_days
    FROM price_history ph
    LEFT JOIN last_in_stock lis ON lis.product_id = ph.product_id
    WHERE ph.availability = false
      AND (lis.last_in_stock_date IS NULL
           OR ph.scraped_at > lis.last_in_stock_date)
    GROUP BY ph.product_id
)
SELECT
    p.id,
    p.name,
    p.category,
    p.active,
    p.consecutive_404s,
    COALESCE(os.consecutive_oos_days, 0)  AS consecutive_oos_days,
    lis.last_in_stock_date,
    fs.first_scraped_date,
    fs.last_scraped_date,
    CASE
        WHEN p.active = false AND p.consecutive_404s >= 3                           THEN 'deactivated: 404s'
        WHEN p.active = false AND COALESCE(os.consecutive_oos_days, 0) >= 30        THEN 'deactivated: oos'
        WHEN p.active = false                                                       THEN 'deactivated: unknown'
        WHEN COALESCE(os.consecutive_oos_days, 0) >= 30                             THEN '⚠ should be deactivated'
        WHEN COALESCE(os.consecutive_oos_days, 0) > 0                               THEN 'oos streak in progress'
        ELSE 'active / in stock'
    END AS status
FROM products p
LEFT JOIN oos_streak os       ON os.product_id = p.id
LEFT JOIN last_in_stock lis   ON lis.product_id = p.id
LEFT JOIN first_and_last_scraped fs ON fs.product_id = p.id
ORDER BY
    CASE WHEN p.active = false THEN 1 ELSE 0 END,
    consecutive_oos_days DESC;


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


