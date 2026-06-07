CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_fts
  ON products
  USING GIN (to_tsvector('simple', coalesce(name, '') || ' ' || coalesce(brand, '')));