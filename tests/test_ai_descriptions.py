from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import src.ai_descriptions as ai_descriptions
from src.ai_descriptions import (
    _fmt_price,
    _fmt_price_diff,
    _classify_price_situation,
    _build_product_description_prompt,
    _build_deal_description_prompt,
    generate_product_description,
    generate_ai_deal_description,
)

_PRODUCT = {
    "name": "WH-1000XM5",
    "brand": "Sony",
    "category": "headphones",
    "description": "Noise cancelling over-ear headphones",
    "specs": {"Kleur": "Zwart", "Gewicht": "250 g"},
}

_PRICE_CONTEXT = {
    "current_price": 340.0,
    "current_price_since": "2026-07-01",
    "previous_price": 390.0,
    "price_diff": -50.0,
    "drop_pct": -12.8,
    "low_90d": 320.0,
    "low_90d_date": "2026-03-03",
    "low_30d": 330.0,
    "low_30d_date": "2026-06-15",
    "high_30d": 400.0,
    "high_30d_date": "2026-06-01",
}


def _mock_client(text="Gegenereerde tekst."):
    client = MagicMock()
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    response.usage.input_tokens = 400
    response.usage.output_tokens = 100
    client.messages.create.return_value = response
    return client


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


# --- _classify_price_situation ---

def test_classify_price_situation_low_90d_takes_priority():
    # current == low_90d and == low_30d: 90d framing should win (it's the strongest claim).
    ctx = {"current_price": 300.0, "low_90d": 300.0, "low_30d": 300.0, "high_30d": 350.0}
    assert _classify_price_situation(ctx) == "low_90d"

def test_classify_price_situation_low_30d_when_not_low_90d():
    # current matches the 30-day low, but an even lower price exists earlier in the 90-day window.
    ctx = {"current_price": 340.0, "low_90d": 320.0, "low_30d": 340.0, "high_30d": 340.0}
    assert _classify_price_situation(ctx) == "low_30d"

def test_classify_price_situation_high_30d():
    ctx = {"current_price": 400.0, "low_90d": 320.0, "low_30d": 330.0, "high_30d": 400.0}
    assert _classify_price_situation(ctx) == "high_30d"

def test_classify_price_situation_none_when_mid_range():
    ctx = {"current_price": 350.0, "low_90d": 320.0, "low_30d": 330.0, "high_30d": 400.0}
    assert _classify_price_situation(ctx) == "none"


# --- prompt construction ---

def test_product_description_prompt_includes_fields():
    prompt = _build_product_description_prompt(_PRODUCT)
    assert "WH-1000XM5" in prompt
    assert "Sony" in prompt
    assert "headphones" in prompt
    assert "Noise cancelling over-ear headphones" in prompt
    assert "Kleur: Zwart" in prompt

def test_product_description_prompt_missing_fields_fallback():
    product = {"name": "X", "brand": "Y", "category": "z"}
    prompt = _build_product_description_prompt(product)
    assert "niet beschikbaar" in prompt

def test_deal_description_prompt_includes_formatted_prices():
    prompt = _build_deal_description_prompt(_PRODUCT, _PRICE_CONTEXT)
    assert "€340" in prompt
    assert "€390" in prompt
    assert "-50" in prompt
    assert "€320" in prompt

def test_deal_description_prompt_bans_forbidden_words():
    prompt = _build_deal_description_prompt(_PRODUCT, _PRICE_CONTEXT)
    assert "nooit de woorden" in prompt

def test_deal_description_prompt_bans_invented_timeframe_for_previous_price():
    prompt = _build_deal_description_prompt(_PRODUCT, _PRICE_CONTEXT)
    assert "vorige week" in prompt  # cited as a forbidden example, not asserted as output
    assert "Noem nooit een tijdsaanduiding" in prompt

def test_deal_description_prompt_uses_classified_situation_instruction():
    # _PRICE_CONTEXT: current=340, low_90d=320 -> "none" situation (not at any low/high extreme).
    prompt = _build_deal_description_prompt(_PRODUCT, _PRICE_CONTEXT)
    assert ai_descriptions._SITUATION_INSTRUCTION["none"] in prompt


# --- success path ---

def test_generate_product_description_returns_stripped_text():
    with patch("src.ai_descriptions._client", return_value=_mock_client("  Beschrijving tekst.  ")):
        result = generate_product_description(_PRODUCT)
    assert result == "Beschrijving tekst."

def test_generate_ai_deal_description_returns_stripped_text():
    with patch("src.ai_descriptions._client", return_value=_mock_client("  Prijs daalde.  ")):
        result = generate_ai_deal_description(_PRODUCT, _PRICE_CONTEXT)
    assert result == "Prijs daalde."


# --- None on failure ---

def test_generate_product_description_returns_none_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    with patch("src.ai_descriptions._client", return_value=client):
        result = generate_product_description(_PRODUCT)
    assert result is None

def test_generate_ai_deal_description_returns_none_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    with patch("src.ai_descriptions._client", return_value=client):
        result = generate_ai_deal_description(_PRODUCT, _PRICE_CONTEXT)
    assert result is None


# --- no API call for invalid input ---

def test_generate_product_description_none_product_skips_api_call():
    client = MagicMock()
    with patch("src.ai_descriptions._client", return_value=client):
        result = generate_product_description(None)
    assert result is None
    client.messages.create.assert_not_called()

def test_generate_ai_deal_description_none_product_skips_api_call():
    client = MagicMock()
    with patch("src.ai_descriptions._client", return_value=client):
        result = generate_ai_deal_description(None, _PRICE_CONTEXT)
    assert result is None
    client.messages.create.assert_not_called()

def test_generate_ai_deal_description_missing_context_key_skips_api_call():
    incomplete_ctx = {"current_price": 340.0}  # missing required keys
    client = MagicMock()
    with patch("src.ai_descriptions._client", return_value=client):
        result = generate_ai_deal_description(_PRODUCT, incomplete_ctx)
    assert result is None
    client.messages.create.assert_not_called()

def test_generate_product_description_none_specs_skips_api_call():
    product = {**_PRODUCT, "specs": None}
    client = MagicMock()
    with patch("src.ai_descriptions._client", return_value=client):
        result = generate_product_description(product)
    assert result is None
    client.messages.create.assert_not_called()

def test_generate_product_description_empty_specs_skips_api_call():
    product = {**_PRODUCT, "specs": {}}
    client = MagicMock()
    with patch("src.ai_descriptions._client", return_value=client):
        result = generate_product_description(product)
    assert result is None
    client.messages.create.assert_not_called()


# --- cost tracking ---

def test_get_total_cost_accumulates_across_calls():
    ai_descriptions._total_cost = 0.0
    with patch("src.ai_descriptions._client", return_value=_mock_client()):
        generate_product_description(_PRODUCT)
        generate_product_description(_PRODUCT)
    per_call = (400 / 1_000_000) * ai_descriptions._COST_INPUT_PER_M + (100 / 1_000_000) * ai_descriptions._COST_OUTPUT_PER_M
    assert ai_descriptions.get_total_cost() == per_call * 2

def test_get_total_cost_unaffected_by_skipped_generation():
    ai_descriptions._total_cost = 0.0
    product = {**_PRODUCT, "specs": None}
    with patch("src.ai_descriptions._client", return_value=_mock_client()):
        generate_product_description(product)
    assert ai_descriptions.get_total_cost() == 0.0
