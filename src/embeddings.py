"""
Product embedding generation using OpenAI text-embedding-3-small.

All OpenAI calls live here — no OpenAI calls in other modules.
"""

import logging
import openai

logger = logging.getLogger(__name__)

_MODEL = "text-embedding-3-small"


def _client() -> openai.OpenAI:
    return openai.OpenAI()


def build_embedding_text(product: dict) -> str:
    """Assemble the plain-text embedding input from a product dict. Never raises.

    Price is deliberately excluded — see docs/spec_embeddings.md §5
    "Why price is excluded".
    """
    lines = []

    name = product.get("name")
    if name:
        lines.append(name)

    brand = product.get("brand")
    if brand:
        lines.append(f"Merk: {brand}")

    category = product.get("category")
    if category:
        lines.append(f"Categorie: {category}")

    ai_description = product.get("ai_description")
    if ai_description:
        lines.append(ai_description)

    specs = product.get("specs") or {}
    spec_lines = [
        f"{key}: {value}"
        for key, value in specs.items()
        if value is not None and value != "" and value != "null"
    ]
    if spec_lines:
        lines.append("Specs:")
        lines.extend(spec_lines)

    return "\n".join(lines)


def generate_embedding(text: str) -> list[float] | None:
    """Call the OpenAI embeddings API. Returns None and logs WARNING on any failure."""
    try:
        response = _client().embeddings.create(model=_MODEL, input=text)
        return response.data[0].embedding
    except Exception as e:
        logger.warning("generate_embedding failed: %s", e)
        return None


def format_embedding_for_pg(embedding: list[float]) -> str:
    """Format an embedding as the `[n1,n2,...]` string literal pgvector expects."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def store_embedding(conn, product_id: int, embedding: list[float]) -> None:
    """Write an embedding to products.embedding and commit."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE products SET embedding = %s WHERE id = %s",
            (format_embedding_for_pg(embedding), product_id),
        )
    conn.commit()


if __name__ == "__main__":
    import sys
    import os
    import truststore
    truststore.inject_into_ssl()
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from dotenv import load_dotenv
    load_dotenv(".env.local")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    from src.db import get_connection

    CATEGORIES = ["headphones", "earbuds", "speakers", "soundbars"]

    conn = get_connection()
    try:
        for cat in CATEGORIES:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name, brand, category, specs, ai_description
                    FROM products
                    WHERE category = %s AND active = true
                    ORDER BY id LIMIT 1
                    """,
                    (cat,),
                )
                row = cur.fetchone()
            if not row:
                print(f"\n[WARN] no product found for category: {cat}")
                continue
            p = {"name": row[0], "brand": row[1], "category": row[2],
                 "specs": row[3], "ai_description": row[4]}
            text = build_embedding_text(p)
            print(f"\n{'='*60}")
            print(f"Category : {p['category']}")
            print(f"Product  : {p['name']} ({p['brand']})")
            print(f"{'-'*60}")
            print(text)
            embedding = generate_embedding(text)
            if embedding is None:
                print("[FAILED]")
            else:
                print(f"\n[embedding: {len(embedding)} dims, first 5 = {embedding[:5]}]")
    finally:
        conn.close()
