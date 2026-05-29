from pathlib import Path
import sys
import inspect
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import upsert_product, upsert_price_history, handle_product_404, reset_404_count, CONSECUTIVE_404_THRESHOLD, deactivate_if_long_term_oos, OOS_DEACTIVATION_THRESHOLD


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
