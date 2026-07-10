from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai_descriptions import _fmt_price, _fmt_price_diff


# --- _fmt_price ---

def test_fmt_price_whole_number_has_no_decimals():
    assert _fmt_price(340.0) == "340"

def test_fmt_price_decimal_uses_dutch_comma():
    assert _fmt_price(339.99) == "339,99"

def test_fmt_price_single_decimal_pads_to_two():
    assert _fmt_price(339.9) == "339,90"


# --- _fmt_price_diff ---

def test_fmt_price_diff_positive_whole_number():
    assert _fmt_price_diff(50.0) == "+50"

def test_fmt_price_diff_negative_whole_number():
    assert _fmt_price_diff(-21.0) == "-21"

def test_fmt_price_diff_negative_decimal():
    assert _fmt_price_diff(-21.5) == "-21,50"

def test_fmt_price_diff_zero_is_positive_sign():
    assert _fmt_price_diff(0.0) == "+0"
