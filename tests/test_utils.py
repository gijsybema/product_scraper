from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import normalize_category, generate_slug


# --- normalize_category ---

def test_normalize_category_exact_keys():
    assert normalize_category("hoofdtelefoon") == "headphones"
    assert normalize_category("koptelefoon") == "headphones"
    assert normalize_category("in-ear hoofdtelefoon") == "earbuds"
    assert normalize_category("oortelefoon") == "earbuds"
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


