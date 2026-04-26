-- retailers
CREATE TABLE IF NOT EXISTS retailers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  base_url TEXT
);

-- products
CREATE TABLE IF NOT EXISTS products (
  id SERIAL PRIMARY KEY,
  retailer_id INTEGER REFERENCES retailers(id),
  sku TEXT NOT NULL,
  name TEXT NOT NULL,
  brand TEXT NOT NULL,
  category TEXT,
  slug TEXT UNIQUE,
  description TEXT,
  specs JSONB,
  retailer TEXT,
  product_url TEXT NOT NULL UNIQUE,
  image_url TEXT,
  all_image_urls JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (retailer_id, sku)
);

-- price_history
CREATE TABLE IF NOT EXISTS price_history (
  id SERIAL PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  scraped_at DATE NOT NULL,
  price NUMERIC(10,2),
  availability BOOLEAN,
  rating DOUBLE PRECISION,
  review_count INTEGER,
  UNIQUE (product_id, scraped_at)
);

-- price_drops
CREATE TABLE IF NOT EXISTS price_drops (
  id SERIAL PRIMARY KEY,

  product_id INTEGER NOT NULL REFERENCES products(id),

  -- welke metingen vergeleken zijn
  new_scraped_at DATE NOT NULL,
  old_scraped_at DATE,

  -- waarden
  old_price NUMERIC(10,2) NOT NULL,
  new_price NUMERIC(10,2) NOT NULL,
  price_diff NUMERIC(10,2) NOT NULL,         -- old_price - new_price (positief bij drop)
  drop_percentage NUMERIC(6,2) NOT NULL,     -- positief bij drop

  -- type event (handig als je later meerdere drop-types toevoegt)
  rule TEXT NOT NULL DEFAULT 'daily_drop',

  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  sent_at TIMESTAMP,

  -- sanity checks (optioneel maar nuttig)
  CONSTRAINT chk_price_drops_prices_positive CHECK (old_price > 0 AND new_price > 0),
  CONSTRAINT chk_price_drops_drop_positive CHECK (price_diff >= 0 AND drop_percentage >= 0),

  -- voorkom dubbele rows als je detect script nog een keer draait
  CONSTRAINT uniq_price_drops_day UNIQUE (product_id, new_scraped_at, rule)
);

--scrape runs
CREATE TABLE IF NOT EXISTS scrape_runs (
  id BIGSERIAL PRIMARY KEY,
  job_name TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'running', -- running|success|failed|blocked|partial
  total_products INT,
  success_count INT DEFAULT 0,
  failed_count INT DEFAULT 0,
  blocked_count INT DEFAULT 0,
  next_retry_at TIMESTAMPTZ,
  retry_attempt INT NOT NULL DEFAULT 0,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_job_started
  ON scrape_runs(job_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_next_retry
  ON scrape_runs(job_name, next_retry_at)
  WHERE next_retry_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);
CREATE INDEX IF NOT EXISTS idx_products_slug     ON products (slug);

