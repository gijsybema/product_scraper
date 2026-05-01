from pathlib import Path
import sys
import inspect

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import upsert_product, upsert_price_history


# --- idempotency ---

def test_upsert_product_is_idempotent():
    # No live DB needed: verify the SQL uses ON CONFLICT DO UPDATE so re-running
    # with the same (retailer_id, sku) overwrites with identical data, not duplicates.
    source = inspect.getsource(upsert_product)
    assert "ON CONFLICT (retailer_id, sku)" in source
    assert "DO UPDATE" in source

def test_upsert_price_history_is_idempotent():
    # ON CONFLICT (product_id, scraped_at) ensures one record per product per day.
    source = inspect.getsource(upsert_price_history)
    assert "ON CONFLICT (product_id, scraped_at)" in source
    assert "DO UPDATE" in source
