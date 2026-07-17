DROP INDEX IF EXISTS idx_products_embedding;
ALTER TABLE products DROP COLUMN IF EXISTS embedding;
