-- Migration 001: add slug, description, specs, retailer columns to products
-- and add indexes on products(category), products(slug).
-- Paired rollback: rollback_001_products_columns.sql
-- Note: price_history(product_id, scraped_at) already has a unique constraint index -- no duplicate index added.

BEGIN;

ALTER TABLE products
    -- slug is intentionally nullable here; NOT NULL + backfill happens in T5.
    -- UNIQUE on a nullable column is safe: PostgreSQL treats each NULL as distinct.
    ADD COLUMN IF NOT EXISTS slug        TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS specs       JSONB,
    ADD COLUMN IF NOT EXISTS retailer    TEXT;

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);
CREATE INDEX IF NOT EXISTS idx_products_slug     ON products (slug);

COMMIT;
