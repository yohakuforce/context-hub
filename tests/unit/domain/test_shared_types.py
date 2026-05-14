"""Unit tests for shared value objects."""

import pytest
from datetime import datetime

from src.shared.types import (
    EmbeddingVector,
    RawContent,
    StructuredContent,
    ExtractedEntity,
    EntityType,
)


class TestRawContent:
    def test_valid_raw_content(self):
        rc = RawContent(
            text="Hello",
            source_url="https://example.com",
            author_id="U123",
            created_at=datetime.utcnow(),
        )
        assert rc.text == "Hello"

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            RawContent(
                text="",
                source_url=None,
                author_id=None,
                created_at=datetime.utcnow(),
            )

    def test_raw_content_is_immutable(self):
        rc = RawContent(
            text="X",
            source_url=None,
            author_id=None,
            created_at=datetime.utcnow(),
        )
        with pytest.raises(Exception):
            rc.text = "Y"  # type: ignore[misc]


class TestEmbeddingVector:
    def test_valid_vector(self):
        values = tuple([0.1] * 1536)
        v = EmbeddingVector(values=values, model_name="ada-002", dimensions=1536)
        assert v.dimensions == 1536

    def test_mismatched_dimensions_raises(self):
        with pytest.raises(ValueError, match="dimensions mismatch"):
            EmbeddingVector(
                values=(0.1, 0.2),
                model_name="ada-002",
                dimensions=1536,
            )

    def test_embedding_vector_is_immutable(self):
        v = EmbeddingVector(values=(1.0,), model_name="m", dimensions=1)
        with pytest.raises(Exception):
            v.dimensions = 2  # type: ignore[misc]
