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
  product_url TEXT NOT NULL UNIQUE,
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

-- price_alerts
CREATE TABLE IF NOT EXISTS price_alerts (
  id SERIAL PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id),
  old_price NUMERIC(10,2) NOT NULL,
  new_price NUMERIC(10,2) NOT NULL,
  drop_percentage NUMERIC(6,2) NOT NULL,
  rule TEXT NOT NULL, -- e.g. '10_percent_drop'
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  sent_at TIMESTAMP
);
