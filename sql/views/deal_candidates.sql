CREATE OR REPLACE VIEW deal_candidates AS
WITH current_prices AS (
  SELECT
    ph.product_id,
    ph.price AS current_price,
    ph.scraped_at AS current_date,
    ph.availability
  FROM price_history ph
  WHERE ph.scraped_at = CURRENT_DATE
),
max_30d AS (
  SELECT
    ph.product_id,
    MAX(ph.price) AS max_price_30d
  FROM price_history ph
  WHERE ph.scraped_at >= CURRENT_DATE - INTERVAL '29 days'
  GROUP BY ph.product_id
),
price_changes AS (
  SELECT
    ph.product_id,
    ph.scraped_at,
    ph.price,
    LAG(ph.price) OVER (
      PARTITION BY ph.product_id
      ORDER BY ph.scraped_at DESC
    ) AS prev_price_desc
  FROM price_history ph
  WHERE ph.scraped_at <= CURRENT_DATE
),
price_streaks AS (
  SELECT
    pc.product_id,
    pc.scraped_at,
    pc.price,
    SUM(
      CASE
        WHEN pc.prev_price_desc IS DISTINCT FROM pc.price THEN 1
        ELSE 0
      END
    ) OVER (
      PARTITION BY pc.product_id
      ORDER BY pc.scraped_at DESC
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS streak_group
  FROM price_changes pc
),
current_price_since AS (
  SELECT
    ps.product_id,
    MIN(ps.scraped_at) AS price_level_since
  FROM price_streaks ps
  JOIN current_prices cp
    ON cp.product_id = ps.product_id
  WHERE ps.streak_group = 1
    AND ps.price = cp.current_price
  GROUP BY ps.product_id
)
SELECT
  p.id,
  p.name,
  cp.current_price,
  m.max_price_30d AS previous_price,
  (m.max_price_30d - cp.current_price) AS price_diff,
  ROUND(
    ((m.max_price_30d - cp.current_price) / m.max_price_30d) * 100,
    1
  ) AS price_drop_pct,
  p.product_url AS url,
  cps.price_level_since::text AS price_level_since
FROM products p
JOIN current_prices cp
  ON cp.product_id = p.id
JOIN max_30d m
  ON m.product_id = p.id
JOIN current_price_since cps
  ON cps.product_id = p.id
WHERE cp.availability = TRUE
  AND m.max_price_30d > cp.current_price
  AND cp.current_price >= 100
  ;
