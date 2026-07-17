from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import openai

import src.embeddings as embeddings_module
from src.embeddings import (
    build_embedding_text,
    generate_embedding,
    get_total_cost,
)

_PRODUCT = {
    "name": "WH-1000XM5",
    "brand": "Sony",
    "category": "headphones",
    "ai_description": "Noise cancelling over-ear headphones.",
    "specs": {"Kleur": "Zwart", "Gewicht": "250 g", "Leeg": None, "Ook leeg": "", "Null string": "null"},
}


def _mock_client(embedding=None, total_tokens=10):
    client = MagicMock()
    response = MagicMock()
    response.data = [MagicMock(embedding=embedding or [0.1, 0.2, 0.3])]
    response.usage.total_tokens = total_tokens
    client.embeddings.create.return_value = response
    return client


# --- build_embedding_text ---

def test_build_embedding_text_fully_populated():
    text = build_embedding_text(_PRODUCT)
    assert "WH-1000XM5" in text
    assert "Merk: Sony" in text
    assert "Categorie: headphones" in text
    assert "Noise cancelling over-ear headphones." in text
    assert "Kleur: Zwart" in text
    assert "Gewicht: 250 g" in text

def test_build_embedding_text_all_optional_fields_null():
    product = {"name": "X"}
    text = build_embedding_text(product)
    assert text == "X"

def test_build_embedding_text_skips_null_and_empty_specs():
    text = build_embedding_text(_PRODUCT)
    assert "Leeg" not in text
    assert "Ook leeg" not in text
    assert "Null string" not in text

def test_build_embedding_text_excludes_price():
    product = {**_PRODUCT, "current_price": 149.99}
    text = build_embedding_text(product)
    assert "149.99" not in text
    assert "149,99" not in text


# --- generate_embedding ---

def test_generate_embedding_returns_vector():
    with patch("src.embeddings._client", return_value=_mock_client([0.1, 0.2, 0.3])):
        result = generate_embedding("some text")
    assert result == [0.1, 0.2, 0.3]

def test_generate_embedding_returns_none_on_openai_error():
    client = MagicMock()
    client.embeddings.create.side_effect = openai.APIConnectionError(request=MagicMock())
    with patch("src.embeddings._client", return_value=client):
        result = generate_embedding("some text")
    assert result is None

def test_generate_embedding_accumulates_cost():
    embeddings_module._total_cost = 0.0
    with patch("src.embeddings._client", return_value=_mock_client(total_tokens=1_000_000)):
        generate_embedding("some text")
    assert get_total_cost() == 0.02
