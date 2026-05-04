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


# ---------------------------------------------------------------------------
# extract_product_specs — earbuds
# ---------------------------------------------------------------------------

def test_extract_specs_earbuds_shared_keys():
    html = _specs_html([
        ("Type oorkussen", "Earbud", False),
        ("Bluetooth-versie", "5.3", False),
        ("Gemiddelde accuduur", "7 uur", False),
        ("Kleur", "Zwart", False),
    ])
    result = extract_product_specs(html, "earbuds")
    assert result["ear_cup_type"] == "Earbud"
    assert result["bluetooth_version"] == "5.3"
    assert result["battery_life"] == "7 uur"
    assert result["color"] == "Zwart"


def test_extract_specs_earbuds_specific_keys():
    html = _specs_html([
        ("Volledig draadloze oordopjes", "Ja", True),
        ("Oplaadcase", "Ja", True),
        ("Accuduur case", "30 uur", False),
        ("Draadloos opladen", "Ja", True),
        ("IP-certificering", "IPX4", False),
        ("Multipoint pairing", "Ja", True),
    ])
    result = extract_product_specs(html, "earbuds")
    assert result["fully_wireless"] == "Ja"
    assert result["charging_case"] == "Ja"
    assert result["battery_life_case"] == "30 uur"
    assert result["wireless_charging"] == "Ja"
    assert result["ip_rating"] == "IPX4"
    assert result["multipoint_pairing"] == "Ja"


def test_extract_specs_earbuds_all_19_keys():
    rows = [
        ("Type oorkussen", "Earbud", False),
        ("Bluetooth", "Ja", True),
        ("Bluetooth-versie", "5.3", False),
        ("Noise cancelling", "Nee", True),
        ("Kwaliteit noise cancelling", "Gemiddeld", False),
        ("Ingebouwde microfoon", "Ja", True),
        ("Gemiddelde accuduur", "7 uur", False),
        ("Geluidsweergave", "Stereo", False),
        ("Gewicht in gram", "46 g", False),
        ("Waterbestendig", "Ja", True),
        ("Kleur", "Zwart", False),
        ("Materiaal", "Kunststof", False),
        ("Type stroomvoorziening", "Accu / batterij", False),
        ("Volledig draadloze oordopjes", "Ja", True),
        ("Oplaadcase", "Ja", True),
        ("Accuduur case", "30 uur", False),
        ("Draadloos opladen", "Ja", True),
        ("IP-certificering", "IPX4", False),
        ("Multipoint pairing", "Ja", True),
    ]
    result = extract_product_specs(html=_specs_html(rows), category="earbuds")
    assert len(result) == 19
    assert result["fully_wireless"] == "Ja"
    assert result["ip_rating"] == "IPX4"
    assert result["battery_life_case"] == "30 uur"


def test_extract_specs_earbuds_no_noise_cancelling_quality_when_absent():
    # Products without ANC won't have a quality row — key must be absent, not None
    html = _specs_html([
        ("Noise cancelling", "Nee", True),
        ("Volledig draadloze oordopjes", "Ja", True),
    ])
    result = extract_product_specs(html, "earbuds")
    assert result["noise_cancelling"] == "Nee"
    assert "noise_cancelling_quality" not in result


def test_extract_specs_earbuds_headphone_only_key_absent():
    # detachable_cable is headphones-only — must not appear in earbuds result
    html = _specs_html([
        ("Kabel los te koppelen", "Ja", True),
        ("Volledig draadloze oordopjes", "Ja", True),
    ])
    result = extract_product_specs(html, "earbuds")
    assert "detachable_cable" not in result
    assert result == {"fully_wireless": "Ja"}


# ---------------------------------------------------------------------------
# extract_product_specs — speakers
# ---------------------------------------------------------------------------

def test_extract_specs_speakers_shared_keys():
    html = _specs_html([
        ("Kleur", "Zwart", False),
        ("Bluetooth", "Ja", True),
        ("Geluidsweergave", "Stereo", False),
        ("Gemiddelde accuduur", "24 uur", False),
    ])
    result = extract_product_specs(html, "speakers")
    assert result["color"] == "Zwart"
    assert result["bluetooth"] == "Ja"
    assert result["audio_rendering"] == "Stereo"
    assert result["battery_life"] == "24 uur"


def test_extract_specs_speakers_specific_keys():
    html = _specs_html([
        ("Type speaker", "Bluetooth speaker", False),
        ("Formaat draadloze speaker", "Compact (10-20 cm)", False),
        ("Gewicht", "1,31 kg", False),
        ("Maximale accu/batterijduur", "24 uur", False),
        ("IP-certificering", "IP67", False),
        ("Wifi ingebouwd", "Ja", True),
        ("Multiroom audio", "Ja", True),
        ("Bediening via app", "Ja", True),
        ("Waterdichtheid", "Waterdicht", False),
        ("NFC", "Nee", True),
        ("Radio", "Ja", True),
        ("Afstandsbediening", "Nee", True),
        ("Bediening via knoppen op apparaat", "Ja", True),
    ])
    result = extract_product_specs(html, "speakers")
    assert result["speaker_type"] == "Bluetooth speaker"
    assert result["speaker_size"] == "Compact (10-20 cm)"
    assert result["weight"] == "1,31 kg"
    assert result["battery_life_max"] == "24 uur"
    assert result["ip_rating"] == "IP67"
    assert result["wifi"] == "Ja"
    assert result["multiroom"] == "Ja"
    assert result["app_control"] == "Ja"
    assert result["water_resistance"] == "Waterdicht"
    assert result["nfc"] == "Nee"
    assert result["radio"] == "Ja"
    assert result["remote_control"] == "Nee"
    assert result["physical_controls"] == "Ja"


def test_extract_specs_speakers_all_18_keys():
    rows = [
        ("Type speaker", "Bluetooth speaker", False),
        ("Formaat draadloze speaker", "Compact (10-20 cm)", False),
        ("Gewicht", "1,31 kg", False),
        ("Kleur", "Zwart", False),
        ("Ingebouwde microfoon", "Ja", True),
        ("Gemiddelde accuduur", "24 uur", False),
        ("Maximale accu/batterijduur", "24 uur", False),
        ("IP-certificering", "IP67", False),
        ("Bluetooth", "Ja", True),
        ("Wifi ingebouwd", "Ja", True),
        ("Multiroom audio", "Ja", True),
        ("Geluidsweergave", "Stereo", False),
        ("Bediening via app", "Ja", True),
        ("Waterdichtheid", "Waterdicht", False),
        ("NFC", "Nee", True),
        ("Radio", "Ja", True),
        ("Afstandsbediening", "Nee", True),
        ("Bediening via knoppen op apparaat", "Ja", True),
    ]
    result = extract_product_specs(html=_specs_html(rows), category="speakers")
    assert len(result) == 18
    assert result["speaker_type"] == "Bluetooth speaker"
    assert result["battery_life_max"] == "24 uur"
    assert result["physical_controls"] == "Ja"


def test_extract_specs_speakers_weight_key_distinct_from_headphones():
    # speakers use "Gewicht" -> "weight"; headphones use "Gewicht in gram" -> "weight_grams"
    html = _specs_html([("Gewicht", "1,31 kg", False)])
    result = extract_product_specs(html, "speakers")
    assert result["weight"] == "1,31 kg"
    assert "weight_grams" not in result


def test_extract_specs_speakers_earbuds_only_key_absent():
    # fully_wireless is earbuds-only — must not appear in speakers result
    html = _specs_html([
        ("Volledig draadloze oordopjes", "Ja", True),
        ("Type speaker", "Bluetooth speaker", False),
    ])
    result = extract_product_specs(html, "speakers")
    assert "fully_wireless" not in result
    assert result == {"speaker_type": "Bluetooth speaker"}
