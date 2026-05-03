-- Migration 002: add consecutive_404s counter to products
-- Apply locally in pgAdmin first, then on Railway, before pushing dependent code.

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS consecutive_404s INT NOT NULL DEFAULT 0;
