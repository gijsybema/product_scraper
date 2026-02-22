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
