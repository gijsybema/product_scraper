-- Rollback 002: remove consecutive_404s column
ALTER TABLE products
  DROP COLUMN IF EXISTS consecutive_404s;
