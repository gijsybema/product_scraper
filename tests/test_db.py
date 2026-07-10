from pathlib import Path
import sys
import inspect
from datetime import date
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import upsert_product, upsert_price_history, handle_product_404, reset_404_count, CONSECUTIVE_404_THRESHOLD, deactivate_if_long_term_oos, OOS_DEACTIVATION_THRESHOLD, get_price_context, update_ai_description, update_ai_deal_description, get_products_to_scrape


# --- idempotency ---

def test_upsert_product_is_idempotent():
    # No live DB needed: verify the SQL uses ON CONFLICT DO UPDATE so re-running
    # with the same (retailer_id, sku) overwrites with identical data, not duplicates.
    source = inspect.getsource(upsert_product)
    assert "ON CONFLICT (retailer_id, sku)" in source
    assert "DO UPDATE" in source

def test_upsert_product_returns_id_and_ai_description():
    # Caller needs (product_id, ai_description) to decide whether to generate one.
    source = inspect.getsource(upsert_product)
    assert "RETURNING id, ai_description" in source

def test_upsert_price_history_is_idempotent():
    # ON CONFLICT (product_id, scraped_at) ensures one record per product per day.
    source = inspect.getsource(upsert_price_history)
    assert "ON CONFLICT (product_id, scraped_at)" in source
    assert "DO UPDATE" in source

def test_upsert_price_history_returns_previous_price():
    # Caller needs the pre-upsert price to detect a change without a separate query.
    source = inspect.getsource(upsert_price_history)
    assert "RETURNING (SELECT price FROM prev)" in source

    ctx, cur = _make_cursor((205.0,))
    conn = MagicMock()
    conn.cursor.return_value = ctx
    result = upsert_price_history(
        conn, product_id=1, scraped_at=date(2026, 6, 26),
        price=194.0, availability=True, rating=4.5, review_count=100,
    )
    assert result == 205.0

def test_upsert_price_history_returns_none_for_first_row():
    # No prior price row (new product) — RETURNING yields NULL.
    ctx, cur = _make_cursor((None,))
    conn = MagicMock()
    conn.cursor.return_value = ctx
    result = upsert_price_history(
        conn, product_id=1, scraped_at=date(2026, 6, 26),
        price=194.0, availability=True, rating=4.5, review_count=100,
    )
    assert result is None


# --- get_products_to_scrape ---

def test_get_products_to_scrape_selects_name_brand_category():
    # generate_ai_deal_description needs name/brand/category on the product dict.
    source = inspect.getsource(get_products_to_scrape)
    assert "p.id, p.product_url, p.name, p.brand, p.category" in source
    assert "id, product_url, name, brand, category" in source


# --- handle_product_404 ---

def _make_cursor(fetchone_return):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_return
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur

def test_handle_product_404_single_update_statement():
    # Increment and conditional deactivation must be in one UPDATE — no TOCTOU gap.
    source = inspect.getsource(handle_product_404)
    assert source.count("UPDATE products") == 1
    assert "consecutive_404s + 1" in source
    assert "active" in source

def test_handle_product_404_passes_threshold_as_parameter():
    # Threshold must come from CONSECUTIVE_404_THRESHOLD, not be hardcoded in the SQL call.
    source = inspect.getsource(handle_product_404)
    assert "CONSECUTIVE_404_THRESHOLD" in source

def test_handle_product_404_returns_true_when_deactivated():
    # Row indicates threshold reached and product is now inactive.
    ctx, _ = _make_cursor((CONSECUTIVE_404_THRESHOLD, False))
    conn = MagicMock()
    conn.cursor.return_value = ctx
    assert handle_product_404(conn, product_id=1) is True

def test_handle_product_404_returns_false_below_threshold():
    # Row indicates counter incremented but product still active.
    ctx, _ = _make_cursor((CONSECUTIVE_404_THRESHOLD - 1, True))
    conn = MagicMock()
    conn.cursor.return_value = ctx
    assert handle_product_404(conn, product_id=1) is False

def test_handle_product_404_returns_false_when_product_not_found():
    # Product ID doesn't exist — fetchone returns None, should not crash.
    ctx, _ = _make_cursor(None)
    conn = MagicMock()
    conn.cursor.return_value = ctx
    assert handle_product_404(conn, product_id=999) is False


# --- reset_404_count ---

def test_reset_404_count_only_updates_nonzero():
    # Guard clause prevents unnecessary writes when counter is already 0.
    source = inspect.getsource(reset_404_count)
    assert "consecutive_404s > 0" in source


# --- deactivate_if_long_term_oos ---

def test_deactivate_if_long_term_oos_sql_structure():
    # Must count OOS days since last in-stock date and update products on threshold.
    source = inspect.getsource(deactivate_if_long_term_oos)
    assert "price_history" in source
    assert "OOS_DEACTIVATION_THRESHOLD" in source  # default arg — not hardcoded inline
    assert "availability = true" in source   # last-in-stock subquery
    assert "availability = false" in source  # OOS streak count
    assert "UPDATE products" in source
    assert "active = false" in source
    assert "RETURNING id" in source

def test_deactivate_if_long_term_oos_returns_true_when_deactivated():
    # Streak of 30 OOS days — product should be deactivated.
    ctx_select, _ = _make_cursor((OOS_DEACTIVATION_THRESHOLD,))
    ctx_update, _ = _make_cursor((1,))  # RETURNING id returns a row
    conn = MagicMock()
    conn.cursor.side_effect = [ctx_select, ctx_update]
    assert deactivate_if_long_term_oos(conn, product_id=1) is True

def test_deactivate_if_long_term_oos_returns_false_insufficient_streak():
    # Only 15 consecutive OOS days — below threshold, no deactivation.
    ctx_select, _ = _make_cursor((15,))
    conn = MagicMock()
    conn.cursor.return_value = ctx_select
    assert deactivate_if_long_term_oos(conn, product_id=1) is False

def test_deactivate_if_long_term_oos_returns_false_when_streak_reset_by_in_stock():
    # Recent in-stock day reset the streak to 29 — just below threshold.
    ctx_select, _ = _make_cursor((OOS_DEACTIVATION_THRESHOLD - 1,))
    conn = MagicMock()
    conn.cursor.return_value = ctx_select
    assert deactivate_if_long_term_oos(conn, product_id=1) is False

def test_deactivate_if_long_term_oos_returns_false_when_already_inactive():
    # Streak reached threshold, but product already inactive — UPDATE returns no row.
    ctx_select, _ = _make_cursor((OOS_DEACTIVATION_THRESHOLD,))
    ctx_update, _ = _make_cursor(None)  # RETURNING id returns nothing — already inactive
    conn = MagicMock()
    conn.cursor.side_effect = [ctx_select, ctx_update]
    assert deactivate_if_long_term_oos(conn, product_id=1) is False


# --- get_price_context ---

def test_get_price_context_returns_none_when_no_row():
    # Product has no price_history rows at all.
    ctx, _ = _make_cursor(None)
    conn = MagicMock()
    conn.cursor.return_value = ctx
    assert get_price_context(conn, product_id=1) is None

def test_get_price_context_returns_none_when_no_distinct_previous_price():
    # Price has never changed (or only one row exists) — previous_price is NULL.
    row = (194.0, date(2026, 6, 1), None, 194.0, date(2026, 6, 1),
           194.0, date(2026, 6, 1), 194.0, date(2026, 6, 1))
    ctx, _ = _make_cursor(row)
    conn = MagicMock()
    conn.cursor.return_value = ctx
    assert get_price_context(conn, product_id=1) is None

def test_get_price_context_drop_pct_positive_on_price_drop():
    # current=194.0, previous=205.0 -> price dropped, drop_pct must be positive.
    row = (194.0, date(2026, 6, 26), 205.0, 194.0, date(2026, 6, 1),
           194.0, date(2026, 6, 1), 205.0, date(2026, 6, 8))
    ctx, _ = _make_cursor(row)
    conn = MagicMock()
    conn.cursor.return_value = ctx
    result = get_price_context(conn, product_id=1)
    assert result["price_diff"] == 11.0          # positive = price dropped
    assert result["drop_pct"] == 5.37            # positive = price dropped, round((205-194)/205*100, 2)

def test_get_price_context_drop_pct_negative_on_price_rise():
    # current=85.0, previous=64.0 -> price rose, drop_pct must be negative.
    row = (85.0, date(2026, 6, 26), 64.0, 64.0, date(2026, 6, 23),
           64.0, date(2026, 6, 23), 85.0, date(2026, 5, 27))
    ctx, _ = _make_cursor(row)
    conn = MagicMock()
    conn.cursor.return_value = ctx
    result = get_price_context(conn, product_id=1)
    assert result["price_diff"] == -21.0          # negative = price rose, not dropped
    assert result["drop_pct"] == -32.81           # negative = not a drop, round((64-85)/64*100, 2)


# --- update_ai_description / update_ai_deal_description ---

def test_update_ai_description_sql():
    source = inspect.getsource(update_ai_description)
    assert "UPDATE products" in source
    assert "ai_description = %s" in source
    assert "WHERE id = %s" in source

def test_update_ai_description_executes_with_correct_params():
    ctx, cur = _make_cursor(None)
    conn = MagicMock()
    conn.cursor.return_value = ctx
    update_ai_description(conn, product_id=1, text="een tekst")
    args, _ = cur.execute.call_args
    assert args[1] == ("een tekst", 1)

def test_update_ai_deal_description_sql():
    source = inspect.getsource(update_ai_deal_description)
    assert "UPDATE products" in source
    assert "ai_deal_description = %s" in source
    assert "ai_deal_description_updated_at = NOW()" in source
    assert "WHERE id = %s" in source

def test_update_ai_deal_description_executes_with_correct_params():
    ctx, cur = _make_cursor(None)
    conn = MagicMock()
    conn.cursor.return_value = ctx
    update_ai_deal_description(conn, product_id=1, text="prijs daalde")
    args, _ = cur.execute.call_args
    assert args[1] == ("prijs daalde", 1)
