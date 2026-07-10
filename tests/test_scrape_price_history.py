from pathlib import Path
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.scrape_price_history import process_single_product

_PRODUCT = {"name": "Test Product", "brand": "TestBrand", "category": "headphones"}


def _make_http_error(status_code: int) -> requests.exceptions.HTTPError:
    response = MagicMock()
    response.status_code = status_code
    err = requests.exceptions.HTTPError(response=response)
    return err


def _make_conn():
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


# --- 404 handling ---

def test_404_returns_is_404_true():
    """A 404 HTTPError signals deactivation and is not retried."""
    conn = _make_conn()
    with patch("scripts.scrape_price_history.scrape_product_facts",
               side_effect=_make_http_error(404)):
        success, is_404, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    assert success is False
    assert is_404 is True
    assert isinstance(err, requests.exceptions.HTTPError)


def test_404_does_not_retry():
    """A 404 must return immediately — scrape_product_facts called exactly once."""
    conn = _make_conn()
    mock_scrape = MagicMock(side_effect=_make_http_error(404))
    with patch("scripts.scrape_price_history.scrape_product_facts", mock_scrape):
        process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    assert mock_scrape.call_count == 1


# --- non-404 HTTP error ---

def test_non_404_http_error_is_not_deactivation():
    """A 503 HTTPError is a transient failure, not a deactivation signal."""
    conn = _make_conn()
    with patch("scripts.scrape_price_history.scrape_product_facts",
               side_effect=_make_http_error(503)):
        success, is_404, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    assert success is False
    assert is_404 is False


# --- success path ---

def test_success_returns_true():
    """A clean scrape returns (True, False, None)."""
    conn = _make_conn()
    facts = {"price": 199.99, "in_stock": True, "rating": 4.5, "review_count": 100}
    with patch("scripts.scrape_price_history.scrape_product_facts", return_value=facts), \
         patch("scripts.scrape_price_history.validate_price_facts", return_value=(True, [])), \
         patch("scripts.scrape_price_history.upsert_price_history"):
        success, is_404, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    assert success is True
    assert is_404 is False
    assert err is None


# --- ai_deal_description trigger ---

def _patch_scrape(price=199.99, previous_price=None):
    facts = {"price": price, "in_stock": True, "rating": 4.5, "review_count": 100}
    return patch.multiple(
        "scripts.scrape_price_history",
        scrape_product_facts=MagicMock(return_value=facts),
        validate_price_facts=MagicMock(return_value=(True, [])),
        upsert_price_history=MagicMock(return_value=previous_price),
    )


def test_price_unchanged_skips_deal_description():
    """previous_price == today's price — no context lookup, no generation."""
    conn = _make_conn()
    with _patch_scrape(price=199.99, previous_price=199.99), \
         patch("scripts.scrape_price_history.get_price_context") as mock_ctx, \
         patch("scripts.scrape_price_history.generate_ai_deal_description") as mock_gen:
        process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    mock_ctx.assert_not_called()
    mock_gen.assert_not_called()


def test_first_ever_price_skips_deal_description():
    """previous_price is None (new product) — no context lookup, no generation."""
    conn = _make_conn()
    with _patch_scrape(price=199.99, previous_price=None), \
         patch("scripts.scrape_price_history.get_price_context") as mock_ctx, \
         patch("scripts.scrape_price_history.generate_ai_deal_description") as mock_gen:
        process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    mock_ctx.assert_not_called()
    mock_gen.assert_not_called()


def test_price_change_generates_and_writes_deal_description():
    """previous_price differs from today's price — generates and writes deal description."""
    conn = _make_conn()
    ctx = {"current_price": 199.99}
    with _patch_scrape(price=199.99, previous_price=249.99), \
         patch("scripts.scrape_price_history.get_price_context", return_value=ctx), \
         patch("scripts.scrape_price_history.generate_ai_deal_description", return_value="Prijs daalde.") as mock_gen, \
         patch("scripts.scrape_price_history.update_ai_deal_description") as mock_update:
        process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    mock_gen.assert_called_once_with(_PRODUCT, ctx)
    mock_update.assert_called_once_with(conn, 1, "Prijs daalde.")


def test_price_change_generation_failure_leaves_stale_value():
    """generate_ai_deal_description returns None — no write, no crash."""
    conn = _make_conn()
    ctx = {"current_price": 199.99}
    with _patch_scrape(price=199.99, previous_price=249.99), \
         patch("scripts.scrape_price_history.get_price_context", return_value=ctx), \
         patch("scripts.scrape_price_history.generate_ai_deal_description", return_value=None), \
         patch("scripts.scrape_price_history.update_ai_deal_description") as mock_update:
        success, is_404, in_stock, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    mock_update.assert_not_called()
    assert success is True  # generation failure must not fail the price-history write


def test_deal_description_write_failure_does_not_fail_product():
    """update_ai_deal_description raising must not affect the overall success result."""
    conn = _make_conn()
    ctx = {"current_price": 199.99}
    with _patch_scrape(price=199.99, previous_price=249.99), \
         patch("scripts.scrape_price_history.get_price_context", return_value=ctx), \
         patch("scripts.scrape_price_history.generate_ai_deal_description", return_value="Prijs daalde."), \
         patch("scripts.scrape_price_history.update_ai_deal_description", side_effect=Exception("db error")):
        success, is_404, in_stock, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today(), product=_PRODUCT)

    assert success is True
    assert err is None
