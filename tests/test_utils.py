from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import normalize_category, generate_slug, validate_product_details


# --- normalize_category ---

def test_normalize_category_exact_keys():
    assert normalize_category("hoofdtelefoon") == "headphones"
    assert normalize_category("koptelefoon") == "headphones"
    assert normalize_category("in-ear hoofdtelefoon") == "earbuds"
    assert normalize_category("oortelefoon") == "earbuds"
    assert normalize_category("oordopjes") == "earbuds"
    assert normalize_category("earbud") == "earbuds"
    assert normalize_category("speaker") == "speakers"
    assert normalize_category("soundbar") == "soundbars"

def test_normalize_category_case_insensitive():
    assert normalize_category("Koptelefoon") == "headphones"
    assert normalize_category("SOUNDBAR") == "soundbars"
    assert normalize_category("In-Ear Hoofdtelefoon") == "earbuds"

def test_normalize_category_substring_match():
    # longest key wins: "in-ear hoofdtelefoon" (earbuds) beats "hoofdtelefoon" (headphones)
    assert normalize_category("draadloze in-ear hoofdtelefoon") == "earbuds"
    assert normalize_category("draadloze hoofdtelefoon") == "headphones"
    assert normalize_category("bluetooth speaker set") == "speakers"

def test_normalize_category_url_segments():
    # URL path segments used by discover_products.py as fallback_category
    assert normalize_category("hoofdtelefoons") == "headphones"   # /hoofdtelefoons/filter
    assert normalize_category("oordopjes") == "earbuds"           # /oordopjes/filter
    assert normalize_category("draadloze-speakers") == "speakers"  # /draadloze-speakers/filter
    assert normalize_category("soundbars") == "soundbars"          # /soundbars/filter

def test_normalize_category_unknown_returns_none():
    assert normalize_category("televisie") is None
    assert normalize_category("laptop") is None

def test_normalize_category_empty_returns_none():
    assert normalize_category("") is None
    assert normalize_category("   ") is None
    assert normalize_category(None) is None

def test_normalize_category_whitespace_padded_valid():
    assert normalize_category("  soundbar  ") == "soundbars"
    assert normalize_category("  hoofdtelefoon  ") == "headphones"


# --- generate_slug ---

def test_generate_slug_basic():
    assert generate_slug("Sony WH-1000XM5", set()) == "sony-wh-1000xm5"

def test_generate_slug_lowercase_and_hyphenation():
    assert generate_slug("Bose QuietComfort 45", set()) == "bose-quietcomfort-45"

def test_generate_slug_accents_stripped():
    assert generate_slug("Sennheisér HD 450BT", set()) == "sennheiser-hd-450bt"

def test_generate_slug_no_collision():
    existing = {"sony-wh-1000xm5"}
    assert generate_slug("Bose QuietComfort 45", existing) == "bose-quietcomfort-45"

def test_generate_slug_collision_appends_2():
    existing = {"sony-wh-1000xm5"}
    assert generate_slug("Sony WH-1000XM5", existing) == "sony-wh-1000xm5-2"

def test_generate_slug_collision_appends_3():
    existing = {"sony-wh-1000xm5", "sony-wh-1000xm5-2"}
    assert generate_slug("Sony WH-1000XM5", existing) == "sony-wh-1000xm5-3"

def test_generate_slug_empty_name_raises():
    with pytest.raises(ValueError):
        generate_slug("", set())

def test_generate_slug_whitespace_only_raises():
    with pytest.raises(ValueError):
        generate_slug("   ", set())

def test_generate_slug_all_symbols_raises():
    with pytest.raises(ValueError):
        generate_slug("!!! ???", set())


# --- validate_product_details ---

_VALID_DETAILS = {
    "name": "Sony WH-1000XM5",
    "product_url": "https://www.coolblue.nl/product/123/sony.html",
    "image_url": "https://images.coolblue.nl/img.jpg",
    "category": "headphones",
}

def test_validate_product_details_valid():
    ok, errors = validate_product_details(_VALID_DETAILS)
    assert ok
    assert errors == []

def test_validate_product_details_category_none_is_invalid():
    d = {**_VALID_DETAILS, "category": None}
    ok, errors = validate_product_details(d)
    assert not ok
    assert any("category" in e for e in errors)

def test_validate_product_details_category_missing_is_invalid():
    d = {k: v for k, v in _VALID_DETAILS.items() if k != "category"}
    ok, errors = validate_product_details(d)
    assert not ok
    assert any("category" in e for e in errors)

def test_validate_product_details_category_invalid_value():
    d = {**_VALID_DETAILS, "category": "televisie"}
    ok, errors = validate_product_details(d)
    assert not ok
    assert any("category" in e for e in errors)

def test_validate_product_details_category_valid_values():
    for cat in ("headphones", "earbuds", "speakers", "soundbars"):
        d = {**_VALID_DETAILS, "category": cat}
        ok, _ = validate_product_details(d)
        assert ok, f"Expected valid for category={cat!r}"

def test_validate_product_details_missing_name():
    d = {**_VALID_DETAILS, "name": ""}
    ok, errors = validate_product_details(d)
    assert not ok
    assert any("name" in e for e in errors)

def test_validate_product_details_invalid_product_url():
    d = {**_VALID_DETAILS, "product_url": "not-a-url"}
    ok, errors = validate_product_details(d)
    assert not ok
    assert any("product_url" in e for e in errors)


