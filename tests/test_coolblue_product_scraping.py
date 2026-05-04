from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.coolblue_product_scraping import extract_product_description, extract_product_specs


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

def _description_html(text: str | None = "This is the product description.") -> str:
    inner = (
        f'<div id="collapse-content-abc123">{text}</div>'
        if text is not None
        else ""
    )
    return f"""
    <section id="product-information">
      <div>
        <h3>Omschrijving</h3>
        <div>{inner}</div>
      </div>
    </section>
    """


def _specs_html(rows: list[tuple[str, str, bool]]) -> str:
    """
    rows: [(label, value, is_bool), ...]
    is_bool=True renders value as <svg aria-label="value">
    """
    tr_rows = []
    for label, value, is_bool in rows:
        val_cell = (
            f'<svg aria-label="{value}"></svg>'
            if is_bool
            else value
        )
        tr_rows.append(
            f"<tr>"
            f'<td width="32"></td>'
            f"<th><p>{label}</p></th>"
            f"<td>{val_cell}</td>"
            f"</tr>"
        )
    return f"""
    <section id="product-specifications">
      <table>{"".join(tr_rows)}</table>
    </section>
    """


# ---------------------------------------------------------------------------
# extract_product_description
# ---------------------------------------------------------------------------

def test_extract_description_found():
    html = _description_html("Great noise-cancelling headphones.")
    result = extract_product_description(html)
    assert result == "Great noise-cancelling headphones."


def test_extract_description_strips_whitespace():
    html = _description_html("  Padded text.  ")
    result = extract_product_description(html)
    assert result == "Padded text."


def test_extract_description_no_product_information_section():
    html = "<html><body><p>Nothing here</p></body></html>"
    assert extract_product_description(html) is None


def test_extract_description_no_omschrijving_heading():
    html = """
    <section id="product-information">
      <div><h3>Korte specificaties</h3></div>
    </section>
    """
    assert extract_product_description(html) is None


def test_extract_description_no_collapse_content_div():
    html = """
    <section id="product-information">
      <div>
        <h3>Omschrijving</h3>
        <div>No collapse-content id here.</div>
      </div>
    </section>
    """
    assert extract_product_description(html) is None


def test_extract_description_empty_collapse_returns_none():
    html = """
    <section id="product-information">
      <div>
        <h3>Omschrijving</h3>
        <div><div id="collapse-content-xyz">   </div></div>
      </div>
    </section>
    """
    assert extract_product_description(html) is None


# ---------------------------------------------------------------------------
# extract_product_specs
# ---------------------------------------------------------------------------

def test_extract_specs_headphones_text_values():
    html = _specs_html([
        ("Type oorkussen", "Over ear", False),
        ("Bluetooth-versie", "5.3", False),
        ("Gemiddelde accuduur", "70 uur", False),
    ])
    result = extract_product_specs(html, "headphones")
    assert result["ear_cup_type"] == "Over ear"
    assert result["bluetooth_version"] == "5.3"
    assert result["battery_life"] == "70 uur"


def test_extract_specs_headphones_boolean_ja():
    html = _specs_html([("Noise cancelling", "Ja", True)])
    result = extract_product_specs(html, "headphones")
    assert result["noise_cancelling"] == "Ja"


def test_extract_specs_headphones_boolean_nee():
    html = _specs_html([("Waterbestendig", "Nee", True)])
    result = extract_product_specs(html, "headphones")
    assert result["water_resistant"] == "Nee"


def test_extract_specs_headphones_all_14_keys():
    rows = [
        ("Type oorkussen", "Over ear", False),
        ("Bluetooth", "Ja", True),
        ("Bluetooth-versie", "5.3", False),
        ("Noise cancelling", "Ja", True),
        ("Kwaliteit noise cancelling", "Topklasse", False),
        ("Ingebouwde microfoon", "Ja", True),
        ("Gemiddelde accuduur", "70 uur", False),
        ("Geluidsweergave", "Spatial audio", False),
        ("Gewicht in gram", "278 g", False),
        ("Waterbestendig", "Nee", True),
        ("Kleur", "Zwart", False),
        ("Materiaal", "Kunststof", False),
        ("Type stroomvoorziening", "Accu / batterij", False),
        ("Kabel los te koppelen", "Ja", True),
    ]
    result = extract_product_specs(html=_specs_html(rows), category="headphones")
    assert len(result) == 14
    assert result["color"] == "Zwart"
    assert result["material"] == "Kunststof"
    assert result["power_type"] == "Accu / batterij"
    assert result["detachable_cable"] == "Ja"


def test_extract_specs_partial_keys_only_present_returned():
    # Only some headphone keys in the table — rest must be absent, not None
    html = _specs_html([("Type oorkussen", "On ear", False)])
    result = extract_product_specs(html, "headphones")
    assert result == {"ear_cup_type": "On ear"}


def test_extract_specs_no_section_returns_none():
    html = "<html><body><p>Nothing here</p></body></html>"
    assert extract_product_specs(html, "headphones") is None


def test_extract_specs_unknown_category_returns_empty_dict():
    html = _specs_html([("Type oorkussen", "Over ear", False)])
    result = extract_product_specs(html, "televisions")
    assert result == {}


def test_extract_specs_irrelevant_rows_excluded():
    # Artikelnummer is in the Coolblue table but not in headphone key map
    html = _specs_html([
        ("Artikelnummer", "959897", False),
        ("Type oorkussen", "Over ear", False),
    ])
    result = extract_product_specs(html, "headphones")
    assert "Artikelnummer" not in result
    assert result == {"ear_cup_type": "Over ear"}
