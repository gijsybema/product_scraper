ALTER TABLE products
  DROP COLUMN IF EXISTS ai_description,
  DROP COLUMN IF EXISTS ai_deal_description,
  DROP COLUMN IF EXISTS ai_deal_description_updated_at;
