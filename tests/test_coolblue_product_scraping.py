from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.coolblue_product_scraping import (
    extract_product_description,
    extract_product_specs,
    extract_product_category,
)


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


def test_extract_description_no_section_wrapper_react_id():
    # Some product pages omit section#product-information entirely and use a
    # React-generated id on the content div instead of 'collapse-content-*'.
    html = """
    <div>
      <h3>Omschrijving</h3>
      <div><div id="_R_ql6jal6lll5bsnpfiuifb_">Description from React page.</div></div>
    </div>
    """
    result = extract_product_description(html)
    assert result == "Description from React page."


def test_extract_description_nested_html_joined_with_spaces():
    # Collapse div contains block-level HTML — get_text(separator=" ") should
    # join each text node with a space and strip surrounding whitespace.
    html = """
    <section id="product-information">
      <div>
        <h3>Omschrijving</h3>
        <div>
          <div id="collapse-content-abc123">
            <p>First paragraph.</p><p>Second paragraph.</p>
          </div>
        </div>
      </div>
    </section>
    """
    result = extract_product_description(html)
    assert result == "First paragraph. Second paragraph."


def test_extract_description_omschrijving_not_first_h3():
    # A different section heading appears before Omschrijving — the parser
    # must iterate all h3 elements and find the correct one.
    html = """
    <section id="product-information">
      <div>
        <h3>Korte specificaties</h3>
        <div>Some specs here.</div>
      </div>
      <div>
        <h3>Omschrijving</h3>
        <div><div id="collapse-content-def456">Correct description.</div></div>
      </div>
    </section>
    """
    result = extract_product_description(html)
    assert result == "Correct description."


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


# ---------------------------------------------------------------------------
# extract_product_specs — soundbars
# ---------------------------------------------------------------------------

def test_extract_specs_soundbars_shared_keys():
    html = _specs_html([
        ("Kleur", "Zwart", False),
        ("Bluetooth", "Ja", True),
        ("Geluidsweergave", "Surround", False),
        ("Wifi ingebouwd", "Ja", True),
    ])
    result = extract_product_specs(html, "soundbars")
    assert result["color"] == "Zwart"
    assert result["bluetooth"] == "Ja"
    assert result["audio_rendering"] == "Surround"
    assert result["wifi"] == "Ja"


def test_extract_specs_soundbars_specific_keys():
    html = _specs_html([
        ("Losse subwoofer", "Nee", True),
        ("Aantal audio kanalen", "9", False),
        ("Aantal subwooferkanalen", "1", False),
        ("Surround sound", "Dolby Atmos", False),
        ("Hi-res audio", "Ja", True),
        ("HDMI-aansluiting", "Ja", True),
        ("HDMI ARC (Audio Return Channel)", "Ja", True),
        ("Speelt van netwerk", "Ja", True),
        ("Spotify Connect", "Ja", True),
        ("AirPlay", "Ja", True),
        ("Google Cast", "Nee", True),
        ("Compatibel met smartphone / apps", "Ja", True),
        ("Smart home platform", "Amazon Alexa, Apple HomeKit", False),
    ])
    result = extract_product_specs(html, "soundbars")
    assert result["separate_subwoofer"] == "Nee"
    assert result["audio_channels"] == "9"
    assert result["subwoofer_channels"] == "1"
    assert result["surround_sound"] == "Dolby Atmos"
    assert result["hi_res_audio"] == "Ja"
    assert result["hdmi"] == "Ja"
    assert result["hdmi_arc"] == "Ja"
    assert result["plays_from_network"] == "Ja"
    assert result["spotify_connect"] == "Ja"
    assert result["airplay"] == "Ja"
    assert result["google_cast"] == "Nee"
    assert result["smartphone_compatible"] == "Ja"
    assert result["smart_home_platform"] == "Amazon Alexa, Apple HomeKit"


def test_extract_specs_soundbars_all_22_keys():
    rows = [
        ("Gewicht", "5,76 kg", False),
        ("Kleur", "Zwart", False),
        ("Losse subwoofer", "Nee", True),
        ("Aantal audio kanalen", "9", False),
        ("Aantal subwooferkanalen", "1", False),
        ("Geluidsweergave", "Surround", False),
        ("Surround sound", "Dolby Atmos", False),
        ("Hi-res audio", "Ja", True),
        ("HDMI-aansluiting", "Ja", True),
        ("HDMI ARC (Audio Return Channel)", "Ja", True),
        ("Bluetooth", "Ja", True),
        ("Wifi ingebouwd", "Ja", True),
        ("Speelt van netwerk", "Ja", True),
        ("Multiroom audio", "Ja", True),
        ("NFC", "Ja", True),
        ("Radio", "Ja", True),
        ("Spotify Connect", "Ja", True),
        ("AirPlay", "Ja", True),
        ("Google Cast", "Nee", True),
        ("Compatibel met smartphone / apps", "Ja", True),
        ("Smart home platform", "Amazon Alexa, Apple HomeKit", False),
        ("Bediening via app", "Ja", True),
    ]
    result = extract_product_specs(html=_specs_html(rows), category="soundbars")
    assert len(result) == 22
    assert result["weight"] == "5,76 kg"
    assert result["surround_sound"] == "Dolby Atmos"
    assert result["smart_home_platform"] == "Amazon Alexa, Apple HomeKit"


def test_extract_specs_soundbars_speaker_only_key_absent():
    # speaker_type is speakers-only — must not appear in soundbars result
    html = _specs_html([
        ("Type speaker", "Bluetooth speaker", False),
        ("Geluidsweergave", "Surround", False),
    ])
    result = extract_product_specs(html, "soundbars")
    assert "speaker_type" not in result
    assert result == {"audio_rendering": "Surround"}


# ---------------------------------------------------------------------------
# extract_product_specs — structural edge cases
# ---------------------------------------------------------------------------

def test_extract_specs_row_with_one_td_is_skipped():
    # A <tr> with only one <td> (no separate icon + value columns) must be
    # skipped; the valid row alongside it must still be extracted.
    html = """
    <section id="product-specifications">
      <table>
        <tr>
          <th><p>Type oorkussen</p></th>
          <td>Over ear</td>
        </tr>
        <tr>
          <td width="32"></td>
          <th><p>Bluetooth-versie</p></th>
          <td>5.3</td>
        </tr>
      </table>
    </section>
    """
    result = extract_product_specs(html, "headphones")
    assert "ear_cup_type" not in result
    assert result == {"bluetooth_version": "5.3"}


def test_extract_specs_svg_without_aria_label_value_dropped():
    # SVG present but no aria-label → falls back to get_text() → empty string
    # → must be filtered out; the valid row alongside it must still be present.
    html = """
    <section id="product-specifications">
      <table>
        <tr>
          <td width="32"></td>
          <th><p>Noise cancelling</p></th>
          <td><svg></svg></td>
        </tr>
        <tr>
          <td width="32"></td>
          <th><p>Type oorkussen</p></th>
          <td>Over ear</td>
        </tr>
      </table>
    </section>
    """
    result = extract_product_specs(html, "headphones")
    assert "noise_cancelling" not in result
    assert result == {"ear_cup_type": "Over ear"}


def test_extract_specs_duplicate_label_last_value_wins():
    # If the same Dutch label appears twice in the table, the last row's value
    # should be stored (dict overwrite behaviour).
    html = _specs_html([
        ("Type oorkussen", "Over ear", False),
        ("Type oorkussen", "On ear", False),
    ])
    result = extract_product_specs(html, "headphones")
    assert result == {"ear_cup_type": "On ear"}


def test_extract_specs_whitespace_only_value_dropped():
    # A <td> whose text strips to "" must be excluded from the result.
    html = """
    <section id="product-specifications">
      <table>
        <tr>
          <td width="32"></td>
          <th><p>Type oorkussen</p></th>
          <td>   </td>
        </tr>
        <tr>
          <td width="32"></td>
          <th><p>Bluetooth-versie</p></th>
          <td>5.3</td>
        </tr>
      </table>
    </section>
    """
    result = extract_product_specs(html, "headphones")
    assert "ear_cup_type" not in result
    assert result == {"bluetooth_version": "5.3"}


# ---------------------------------------------------------------------------
# extract_product_category
# ---------------------------------------------------------------------------

def _breadcrumb_script(items: list[str]) -> str:
    """Build a JSON-LD BreadcrumbList script tag from a list of item names."""
    data = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"name": name, "position": i + 1}
            for i, name in enumerate(items)
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def test_extract_category_recognizable_term_returns_category():
    # Standard category page breadcrumb: Home > Hoofdtelefoons > product name
    html = _breadcrumb_script(["Home", "Hoofdtelefoons", "Sony WH-1000XM5"])
    assert extract_product_category(html) == "headphones"


def test_extract_category_all_four_categories():
    # Each category term must resolve to its controlled value.
    cases = [
        (["Home", "Hoofdtelefoons", "Product"], "headphones"),
        (["Home", "Oordopjes", "Product"], "earbuds"),
        (["Home", "Draadloze speakers", "Product"], "speakers"),
        (["Home", "Soundbars", "Product"], "soundbars"),
    ]
    for items, expected in cases:
        result = extract_product_category(_breadcrumb_script(items))
        assert result == expected, f"Expected {expected!r} for breadcrumb {items}"


def test_extract_category_brand_path_returns_none():
    # Sony brand-path pages have no recognisable category term —
    # Home > Alle merken > Sony > product name → None.
    html = _breadcrumb_script(["Home", "Alle merken", "Sony", "Sony WH-1000XM5"])
    assert extract_product_category(html) is None


def test_extract_category_no_breadcrumb_script_returns_none():
    # Only a Product JSON-LD block present — no BreadcrumbList → None.
    product = {"@type": "Product", "name": "Sony WH-1000XM5"}
    html = f'<script type="application/ld+json">{json.dumps(product)}</script>'
    assert extract_product_category(html) is None


def test_extract_category_multiple_scripts_finds_breadcrumb():
    # Page has both a Product block and a BreadcrumbList block —
    # parser must skip the Product block and process the BreadcrumbList.
    product = {"@type": "Product", "name": "Sony WF-1000XM5"}
    breadcrumb = _breadcrumb_script(["Home", "Oordopjes", "Sony WF-1000XM5"])
    html = (
        f'<script type="application/ld+json">{json.dumps(product)}</script>'
        + breadcrumb
    )
    assert extract_product_category(html) == "earbuds"
