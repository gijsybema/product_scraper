-- Rollback for migrate_001_products_columns.sql
-- Drops only what the migration adds; leaves all other columns and tables untouched.
-- WARNING: any data stored in slug, description, specs, retailer will be permanently lost.

BEGIN;

-- Drop indexes explicitly before dropping columns.
-- PostgreSQL would auto-drop idx_products_slug when slug is dropped, but being
-- explicit here keeps the rollback symmetric with the migration and avoids surprises.
DROP INDEX IF EXISTS idx_products_category;
DROP INDEX IF EXISTS idx_products_slug;

-- Drop columns added by migration.
-- No CASCADE: if a view references these columns this will fail, which is the correct
-- behaviour (fail loudly rather than silently drop dependent objects).
ALTER TABLE products
    DROP COLUMN IF EXISTS slug,
    DROP COLUMN IF EXISTS description,
    DROP COLUMN IF EXISTS specs,
    DROP COLUMN IF EXISTS retailer;

COMMIT;
