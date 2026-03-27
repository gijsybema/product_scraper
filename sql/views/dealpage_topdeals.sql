CREATE OR REPLACE VIEW dealpage_topdeals AS
SELECT *
FROM deal_candidates
ORDER BY price_diff DESC, price_drop_pct DESC
LIMIT 20;