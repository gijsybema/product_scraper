-- ==========================================
-- PRICE TRACKER: HEALTH CHECKS (RED FLAGS)
-- Purpose: fast checks to validate today's pipeline + data integrity.
-- Expectation: most "should return 0 rows" queries return nothing.
-- ==========================================

-- ------------------------------------------
-- PRODUCTS (health)
-- ------------------------------------------

-- Total active products (sanity)
SELECT COUNT(*) AS total_active_products
FROM products
WHERE active = TRUE;

-- ------------------------------------------
-- PRICE_HISTORY (health)
-- ------------------------------------------

-- Rows in price_history today (should be close to total_active_products)
SELECT COUNT(*) AS price_history_today
FROM price_history
WHERE scraped_at = CURRENT_DATE;

-- Active products missing a price_history row today (scrape failures)
-- Should be small; ideally 0.
SELECT p.id, p.name, p.product_url
FROM products p
LEFT JOIN price_history ph
  ON ph.product_id = p.id
 AND ph.scraped_at = CURRENT_DATE
WHERE p.active = TRUE
  AND ph.product_id IS NULL;

-- Duplicate check: price_history (should return 0 rows)
SELECT product_id, scraped_at, COUNT(*) AS cnt
FROM price_history
GROUP BY product_id, scraped_at
HAVING COUNT(*) > 1;

-- Price_history rows per day (volume trend)
SELECT
  scraped_at,
  COUNT(*) AS rows_count
FROM price_history
GROUP BY scraped_at
ORDER BY scraped_at DESC
LIMIT 60;

-- Coverage rate today (how much of active catalog got scraped today)
-- coverage_pct ~ 100% is ideal.
WITH active_products AS (
  SELECT COUNT(*) AS n
  FROM products
  WHERE active = TRUE
),
scraped_today AS (
  SELECT COUNT(DISTINCT product_id) AS n
  FROM price_history
  WHERE scraped_at = CURRENT_DATE
)
SELECT
  a.n AS active_products,
  s.n AS scraped_products_today,
  ROUND((s.n::numeric / NULLIF(a.n, 0)) * 100, 2) AS coverage_pct
FROM active_products a
CROSS JOIN scraped_today s;

-- ------------------------------------------
-- PRICE_DROPS (health)
-- ------------------------------------------

-- 5) Duplicate check: price_drops (should return 0 rows)
SELECT product_id, new_scraped_at, rule, COUNT(*) AS cnt
FROM price_drops
GROUP BY product_id, new_scraped_at, rule
HAVING COUNT(*) > 1;

-- 6) Check for negative or invalid values (should return 0 rows)
SELECT *
FROM price_drops
WHERE price_diff < 0
   OR drop_percentage < 0
   OR new_price <= 0
   OR old_price <= 0;

-- 7) Ensure only true drops are stored (should return 0 rows)
SELECT *
FROM price_drops
WHERE new_price >= old_price;

-- 8) Verify drop math consistency for today (should return 0 rows if consistent)
--    If you want rows only when mismatched, keep this WHERE clause.
SELECT
  product_id,
  old_price,
  new_price,
  price_diff,
  drop_percentage,
  (old_price - new_price) AS calc_diff,
  ROUND(((old_price - new_price) / NULLIF(old_price, 0)) * 100, 2) AS calc_pct
FROM price_drops
WHERE new_scraped_at = CURRENT_DATE
  AND (
    price_diff <> (old_price - new_price)
    OR drop_percentage <> ROUND(((old_price - new_price) / NULLIF(old_price, 0)) * 100, 2)
  );

-- Check was was marked sent
SELECT
  id,
  product_id,
  drop_percentage,
  sent_at
FROM price_drops
WHERE new_scraped_at = CURRENT_DATE
ORDER BY drop_percentage DESC;

-- ------------------------------------------
-- SCRAPE_RUNS (health)
-- ------------------------------------------

-- Latest scrape run (quick status check)
SELECT
  id,
  job_name,
  started_at,
  finished_at,
  status,
  retry_attempt,
  total_products,
  success_count,
  failed_count,
  next_retry_at,
  last_error
FROM scrape_runs
WHERE job_name = 'price_history_daily'
ORDER BY started_at DESC
LIMIT 1;

-- Runs stuck in 'running' (should be 0 rows)
SELECT
  id,
  job_name,
  started_at,
  status,
  retry_attempt,
  NOW() - started_at AS running_for
FROM scrape_runs
WHERE status = 'running'
ORDER BY started_at DESC;

-- Runs per day per retry_attempt (how often retries happen)
SELECT
  DATE(started_at AT TIME ZONE 'Europe/Amsterdam') AS day_amsterdam,
  retry_attempt,
  COUNT(*) AS runs
FROM scrape_runs
WHERE job_name = 'price_history_daily'
GROUP BY 1, 2
ORDER BY day_amsterdam DESC, retry_attempt;

-- Retry due now (what your retry runner would pick up)
SELECT
  id,
  job_name,
  started_at,
  status,
  retry_attempt,
  next_retry_at,
  NOW() AS now_ts
FROM scrape_runs
WHERE job_name = 'price_history_daily'
  AND next_retry_at IS NOT NULL
  AND next_retry_at <= NOW()
  AND status IN ('failed', 'blocked', 'partial')
  AND DATE(started_at AT TIME ZONE 'Europe/Amsterdam')
      = DATE(NOW() AT TIME ZONE 'Europe/Amsterdam')
ORDER BY next_retry_at ASC
LIMIT 5;

-- Count integrity check: flag runs where total_products != success + failed + deactivated + ip_blocked (should return 0 rows)
SELECT
  id,
  started_at,
  total_products,
  success_count,
  failed_count,
  deactivated_count,
  ip_blocked_count,
  (success_count + failed_count + deactivated_count + ip_blocked_count) AS counted,
  (total_products - (success_count + failed_count + deactivated_count + ip_blocked_count)) AS diff
FROM scrape_runs
WHERE total_products <> (success_count + failed_count + deactivated_count + ip_blocked_count)
ORDER BY started_at DESC;

-- Sanity check counts: total_products vs (success_count + failed_count + deactivated_count + ip_blocked_count)
-- Diff should be 0 in normal cases.
SELECT
  id,
  started_at,
  total_products,
  success_count,
  failed_count,
  deactivated_count,
  ip_blocked_count,
  (success_count + failed_count + deactivated_count + ip_blocked_count) AS counted,
  (total_products - (success_count + failed_count + deactivated_count + ip_blocked_count)) AS diff
FROM scrape_runs
WHERE job_name = 'price_history_daily'
ORDER BY started_at DESC
LIMIT 20;

-- Scheduled retries (future) + time until due
SELECT
  id,
  started_at,
  status,
  retry_attempt,
  next_retry_at,
  (next_retry_at - NOW()) AS due_in
FROM scrape_runs
WHERE job_name = 'price_history_daily'
  AND next_retry_at IS NOT NULL
ORDER BY next_retry_at ASC;

-- Failure reasons (last_error) frequency (top 20)
-- Note: will be more useful once you store last_error in finish_scrape_run for failures.
SELECT
  COALESCE(last_error, 'NULL') AS last_error,
  COUNT(*) AS occurrences
FROM scrape_runs
WHERE job_name = 'price_history_daily'
GROUP BY COALESCE(last_error, 'NULL')
ORDER BY occurrences DESC
LIMIT 20;

-- Last 20 runs with fail percentage (Amsterdam day boundary)
SELECT
  id,
  job_name,
  started_at,
  finished_at,
  status,
  retry_attempt,
  total_products,
  success_count,
  failed_count,
  ROUND((failed_count::numeric / NULLIF(total_products, 0)) * 100, 2) AS fail_pct,
  next_retry_at
FROM scrape_runs
WHERE job_name = 'price_history_daily'
ORDER BY started_at DESC
LIMIT 20;