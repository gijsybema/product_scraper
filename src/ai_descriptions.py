"""
AI-generated Dutch product copy using Claude Haiku.

All Claude API interaction lives here — no Claude calls in other modules.
"""

import logging
import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_TEMPERATURE = 0.3
_COST_INPUT_PER_M = 0.80   # USD per million input tokens
_COST_OUTPUT_PER_M = 4.00  # USD per million output tokens


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


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
    """Generate a 2–3 sentence Dutch product description. Returns None on failure."""
    try:
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=200,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": _build_product_description_prompt(product)}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning("generate_product_description failed: %s", e)
        return None


def _build_deal_description_prompt(product: dict, price_context: dict) -> str:
    ctx = price_context
    return (
        "Je bent een neutrale prijsanalist voor een Nederlandse prijsvergelijkingssite.\n\n"
        "Schrijf 1-2 zinnen die de huidige prijssituatie van dit product samenvatten.\n"
        "Noem alleen de meest opvallende feiten. Schrijf feitelijk, geen marketingtaal.\n"
        "Gebruik alleen de tijdsperiodes en cijfers die hieronder gegeven zijn — verzin geen "
        "andere tijdsperiodes, vergelijkingen of prijssegmenten.\n"
        "Gebruik nooit de woorden 'minimum', 'maximum' of 'segment'. Beschrijf prijzen altijd "
        "expliciet als 'laagste prijs' of 'hoogste prijs', eventueel met de tijdsperiode erbij "
        "(bijv. 'de laagste prijs in 30 dagen').\n"
        "Geef uitsluitend de 1-2 zinnen terug, zonder titel, kop of opsommingstekens.\n\n"
        f"Product: {product.get('name', '')} ({product.get('brand', '')})\n"
        f"Huidige prijs: €{ctx['current_price']} (sinds {ctx['current_price_since']})\n"
        f"Vorige prijs: €{ctx['previous_price']} ({ctx['price_diff']:+.2f}, {ctx['drop_pct']:+.1f}%)\n"
        f"Laagste prijs ooit: €{ctx['lowest_ever_price']} (op {ctx['lowest_ever_date']})\n"
        f"30-daags laagste prijs: €{ctx['low_30d']} (op {ctx['low_30d_date']})\n"
        f"30-daags hoogste prijs: €{ctx['high_30d']} (op {ctx['high_30d_date']})\n\n"
        "Prijsanalyse:"
    )


def generate_ai_deal_description(product: dict, price_context: dict) -> str | None:
    """Generate 1–2 Dutch sentences summarising the current price situation. Returns None on failure."""
    try:
        prompt = _build_deal_description_prompt(product, price_context)
        response = _client().messages.create(
            model=_MODEL,
            max_tokens=120,
            temperature=_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
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

    # candidate product ids covering the 4 deal-description scenarios,
    # picked manually from a live-DB diagnostic query during T29 planning
    DEAL_SCENARIOS = {
        "drop to all-time low": 2181,
        "drop, not lowest": 119,
        "price increase": 2180,
        "small fluctuation": 2076,
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
                    max_tokens=120,
                    temperature=_TEMPERATURE,
                    messages=[{"role": "user", "content": prompt}],
                )
                _print_result(response.content[0].text.strip(), response.usage)
            except Exception as e:
                print(f"[FAILED -- {e}]")
    finally:
        conn.close()
