from pathlib import Path
import sys
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.scrape_price_history import process_single_product


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
        success, is_404, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today())

    assert success is False
    assert is_404 is True
    assert isinstance(err, requests.exceptions.HTTPError)


def test_404_does_not_retry():
    """A 404 must return immediately — scrape_product_facts called exactly once."""
    conn = _make_conn()
    mock_scrape = MagicMock(side_effect=_make_http_error(404))
    with patch("scripts.scrape_price_history.scrape_product_facts", mock_scrape):
        process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today())

    assert mock_scrape.call_count == 1


# --- non-404 HTTP error ---

def test_non_404_http_error_is_not_deactivation():
    """A 503 HTTPError is a transient failure, not a deactivation signal."""
    conn = _make_conn()
    with patch("scripts.scrape_price_history.scrape_product_facts",
               side_effect=_make_http_error(503)):
        success, is_404, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today())

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
        success, is_404, err = process_single_product(conn, product_id=1, product_url="http://x", scraped_at=date.today())

    assert success is True
    assert is_404 is False
    assert err is None
