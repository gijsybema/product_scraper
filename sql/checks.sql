-- ==========================================
-- PRICE TRACKER DATA HEALTH CHECKS
-- ==========================================

-- 1. Total active products
SELECT COUNT(*) AS total_active_products
FROM products
WHERE active = TRUE;

-- 2. Rows in price_history today
SELECT COUNT(*) AS price_history_today
FROM price_history
WHERE scraped_at = CURRENT_DATE;

-- 3. Products missing a price_history row today (scrape failures)
SELECT p.id, p.name, p.product_url
FROM products p
LEFT JOIN price_history ph
  ON ph.product_id = p.id
 AND ph.scraped_at = CURRENT_DATE
WHERE p.active = TRUE
  AND ph.product_id IS NULL;

-- 4. Duplicate check: price_history (should return 0 rows)
SELECT product_id, scraped_at, COUNT(*) AS cnt
FROM price_history
GROUP BY product_id, scraped_at
HAVING COUNT(*) > 1;

-- 5. Duplicate check: price_drops (should return 0 rows)
SELECT product_id, new_scraped_at, rule, COUNT(*) AS cnt
FROM price_drops
GROUP BY product_id, new_scraped_at, rule
HAVING COUNT(*) > 1;

-- 6. Inspect today’s drops
SELECT *
FROM price_drops
WHERE new_scraped_at = CURRENT_DATE
ORDER BY drop_percentage DESC;

-- 7. Verify drop math consistency
SELECT
  product_id,
  old_price,
  new_price,
  price_diff,
  drop_percentage,
  (old_price - new_price) AS calc_diff,
  ROUND(((old_price - new_price) / old_price) * 100, 2) AS calc_pct
FROM price_drops
WHERE new_scraped_at = CURRENT_DATE;

-- 8. Check for negative or invalid values (should return 0 rows)
SELECT *
FROM price_drops
WHERE price_diff < 0
   OR drop_percentage < 0
   OR new_price <= 0
   OR old_price <= 0;

-- 9. Ensure only true drops are stored (should return 0 rows)
SELECT *
FROM price_drops
WHERE new_price >= old_price;

-- 10. Preview eligible alerts (10% drop, >= €300, in stock)
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
  AND pd.new_price >= 300
  AND ph.availability = TRUE
ORDER BY pd.drop_percentage DESC;

-- 11. Drops per day (historical volume)
SELECT new_scraped_at, COUNT(*) AS drops_count
FROM price_drops
GROUP BY new_scraped_at
ORDER BY new_scraped_at DESC;

-- 12. How many products have ever dropped
SELECT COUNT(DISTINCT product_id) AS products_with_drops
FROM price_drops;