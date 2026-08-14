"""
AI-generated Dutch product copy using Claude Haiku.

All Claude API interaction lives here — no Claude calls in other modules.
"""

import logging
import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_TEMPERATURE = 0.3
_COST_INPUT_PER_M = 1.00   # USD per million input tokens
_COST_OUTPUT_PER_M = 5.00  # USD per million output tokens


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


_total_cost = 0.0


def get_total_cost() -> float:
    """Running total (USD) of all generation calls made in this process."""
    return _total_cost


def _log_usage(kind: str, name: str, usage) -> None:
    global _total_cost
    cost = (usage.input_tokens / 1_000_000 * _COST_INPUT_PER_M
            + usage.output_tokens / 1_000_000 * _COST_OUTPUT_PER_M)
    _total_cost += cost
    print(f"[AI COST] {kind} name=\"{name}\" tokens_in={usage.input_tokens} tokens_out={usage.output_tokens} cost=${cost:.5f}")


def _build_product_description_prompt(product: dict) -> str:
    specs = product.get("specs") or {}
    specs_lines = "\n".join(f"{k}: {v}" for k, v in specs.items()) or "niet beschikbaar"
    return (
        "Je bent een neutrale productredacteur voor een Nederlandse prijsvergelijkingssite.\n\n"
        "Schrijf één alinea van 2-3 zinnen die het volgende product beschrijft op basis van de onderstaande gegevens.\n"
        "Schrijf feitelijk en bondig. Geen marketingtaal. Geen prijsinformatie.\n\n"
        f"Product: {product.get('name', '')}\n"
        f"Merk: {product.get('brand', '')}\n"
        f"Categorie: {product.get('category', '')}\n"
        f"Omschrijving: {product.get('description') or 'niet beschikbaar'}\n"
        f"Specificaties:\n{specs_lines}\n\n"
        "Beschrijving:"
    )


def generate_product_description(product: dict) -> str | None:
    """Generate a 2–3 sentence Dutch product description. Returns None on failure.

    Skips generation (no API call) when specs is missing/empty — without
    structured specs there's nothing to ground the description in, risking
    hallucinated details.
    """
    try:
        if not product.get("specs"):
            return None
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=200,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": _build_product_description_prompt(product)}],
        )
        _log_usage("product_description", product.get("name", ""), response.usage)
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("generate_product_description failed: %s", e)
        return None


def _fmt_price(value: float) -> str:
    """Dutch-style price formatting: whole numbers have no decimals, others use a comma."""
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".replace(".", ",")


def _fmt_price_diff(value: float) -> str:
    """Signed Dutch-style price formatting, e.g. '+50' or '-21,50'."""
    sign = "+" if value >= 0 else "-"
    return f"{sign}{_fmt_price(abs(value))}"


def _classify_price_situation(ctx: dict) -> str:
    """Deterministically pick which single extra fact matters, instead of asking
    the model to judge what's 'salient' (subjective, inconsistent between calls).

    low_90d (not "lowest ever") is used deliberately — it's the longest window
    a visitor can actually verify on the site's own price-history graph, which
    only shows 90 days.
    """
    current = ctx["current_price"]
    if current <= ctx["low_90d"]:
        return "low_90d"
    if current <= ctx["low_30d"]:
        return "low_30d"
    if current >= ctx["high_30d"]:
        return "high_30d"
    return "none"


_SITUATION_INSTRUCTION = {
    "low_90d": "Vermeld expliciet dat dit de laagste prijs in de afgelopen 90 dagen is.",
    "low_30d": "Vermeld expliciet dat dit de laagste prijs in de afgelopen 30 dagen is.",
    "high_30d": "Vermeld expliciet dat dit de hoogste prijs in de afgelopen 30 dagen is.",
    "none": "Vermeld hoe de huidige prijs zich verhoudt tot de laagste prijs in de afgelopen 90 dagen.",
}


def _build_deal_description_prompt(product: dict, price_context: dict) -> str:
    ctx = price_context
    situation_instruction = _SITUATION_INSTRUCTION[_classify_price_situation(ctx)]
    return (
        "Je bent een neutrale prijsanalist voor een Nederlandse prijsvergelijkingssite.\n\n"
        "Schrijf een korte prijsanalyse van twee korte zinnen:\n"
        "Zin 1: benoem de huidige prijs en het verschil met de vorige prijs.\n"
        f"Zin 2: {situation_instruction}\n"
        "Houd beide zinnen kort en bondig. Schrijf feitelijk, geen marketingtaal.\n"
        "Gebruik alleen de tijdsperiodes en cijfers die hieronder gegeven zijn — verzin geen "
        "andere tijdsperiodes, vergelijkingen of prijssegmenten. Noem nooit een tijdsaanduiding "
        "(zoals 'vorige week', 'gisteren' of 'eerder') bij de vorige prijs — die is hieronder niet gegeven.\n"
        "Gebruik nooit de woorden 'minimum', 'maximum' of 'segment'. Beschrijf prijzen altijd "
        "expliciet als 'laagste prijs' of 'hoogste prijs', eventueel met de tijdsperiode erbij "
        "(bijv. 'de laagste prijs in 30 dagen').\n"
        "Gebruik exact dezelfde prijsnotatie als hieronder gegeven (bijv. €340 of €339,99) — "
        "voeg geen decimalen toe aan hele bedragen.\n"
        "Geef uitsluitend de zin(nen) terug, zonder titel, kop of opsommingstekens.\n\n"
        f"Product: {product.get('name', '')} ({product.get('brand', '')})\n"
        f"Huidige prijs: €{_fmt_price(ctx['current_price'])} (sinds {ctx['current_price_since']})\n"
        f"Vorige prijs: €{_fmt_price(ctx['previous_price'])} ({_fmt_price_diff(ctx['price_diff'])}, {ctx['drop_pct']:+.1f}%)\n"
        f"90-daags laagste prijs: €{_fmt_price(ctx['low_90d'])} (op {ctx['low_90d_date']})\n"
        f"30-daags laagste prijs: €{_fmt_price(ctx['low_30d'])} (op {ctx['low_30d_date']})\n"
        f"30-daags hoogste prijs: €{_fmt_price(ctx['high_30d'])} (op {ctx['high_30d_date']})\n\n"
        "Prijsanalyse:"
    )


def generate_ai_deal_description(product: dict, price_context: dict) -> str | None:
    """Generate 1–2 Dutch sentences summarising the current price situation. Returns None on failure."""
    try:
        prompt = _build_deal_description_prompt(product, price_context)
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=100,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        _log_usage("deal_description", product.get("name", ""), response.usage)
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("generate_ai_deal_description failed: %s", e)
        return None


if __name__ == "__main__":
    import sys
    import os
    import truststore
    truststore.inject_into_ssl()
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    from src.db import get_connection, get_price_context

    CATEGORIES = ["headphones", "earbuds", "speakers", "soundbars"]

    # candidate product ids covering the deal-description scenarios, picked manually from a
    # live-DB diagnostic query during T38 (2026-08-14) — prices drift over time, so these will
    # go stale again; re-run a similar diagnostic query against price_history if needed
    DEAL_SCENARIOS = {
        "low_90d (all-time low equivalent)": 2153,
        "drop, not lowest": 68,
        "price increase / high_30d": 2039,
        "small fluctuation": 2058,
        "low_30d, not low_90d": 9,
    }

    def _print_result(text, usage):
        cost = (usage.input_tokens / 1_000_000 * _COST_INPUT_PER_M
                + usage.output_tokens / 1_000_000 * _COST_OUTPUT_PER_M)
        print(text)
        print(f"\n[tokens: {usage.input_tokens} in / {usage.output_tokens} out | cost: ${cost:.5f}]")

    conn = get_connection()
    try:
        print(f"\n{'#'*60}")
        print("# PRODUCT DESCRIPTIONS")
        print(f"{'#'*60}")
        for cat in CATEGORIES:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name, brand, category, description, specs
                    FROM products
                    WHERE category = %s AND active = true AND specs IS NOT NULL
                    ORDER BY id LIMIT 1
                    """,
                    (cat,),
                )
                row = cur.fetchone()
            if not row:
                print(f"\n[WARN] no product found for category: {cat}")
                continue
            p = {"name": row[0], "brand": row[1], "category": row[2],
                 "description": row[3], "specs": row[4]}
            print(f"\n{'='*60}")
            print(f"Category : {p['category']}")
            print(f"Product  : {p['name']} ({p['brand']})")
            print(f"{'─'*60}")
            try:
                response = _client().messages.create(
                    model=_MODEL,
                    max_tokens=200,
                    temperature=_TEMPERATURE,
                    messages=[{"role": "user", "content": _build_product_description_prompt(p)}],
                )
                _print_result(response.content[0].text.strip(), response.usage)
            except Exception as e:
                print(f"[FAILED -- {e}]")

        print(f"\n{'#'*60}")
        print("# DEAL DESCRIPTIONS")
        print(f"{'#'*60}")
        for scenario, product_id in DEAL_SCENARIOS.items():
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, brand, category FROM products WHERE id = %s",
                    (product_id,),
                )
                row = cur.fetchone()
            if not row:
                print(f"\n[WARN] product id {product_id} not found (scenario: {scenario})")
                continue
            p = {"name": row[0], "brand": row[1], "category": row[2]}
            ctx = get_price_context(conn, product_id)
            print(f"\n{'='*60}")
            print(f"Scenario : {scenario}")
            if not ctx:
                print(f"Product  : {p['name']} ({p['brand']}) [id={product_id}]")
                print("[WARN] get_price_context returned None — no distinct previous price]")
                continue
            prompt = _build_deal_description_prompt(p, ctx)
            print(prompt)
            print(f"{'─'*60}")
            try:
                response = _client().messages.create(
                    model=_MODEL,
                    max_tokens=100,
                    temperature=_TEMPERATURE,
                    messages=[{"role": "user", "content": prompt}],
                )
                _print_result(response.content[0].text.strip(), response.usage)
            except Exception as e:
                print(f"[FAILED -- {e}]")
    finally:
        conn.close()
