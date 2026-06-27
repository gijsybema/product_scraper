ALTER TABLE products
  ADD COLUMN IF NOT EXISTS ai_description TEXT,
  ADD COLUMN IF NOT EXISTS ai_deal_description TEXT,
  ADD COLUMN IF NOT EXISTS ai_deal_description_updated_at TIMESTAMPTZ;
