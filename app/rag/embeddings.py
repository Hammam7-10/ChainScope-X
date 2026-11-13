"""CPU-friendly multilingual local embedding adapter (FastEmbed/ONNX)."""
from __future__ import annotations

import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSION = 384


class EmbeddingModelError(RuntimeError):
    pass


class FastEmbedEncoder:
    """Generate actual vectors locally; no network embedding endpoint is used."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        try:
            from fastembed import TextEmbedding
            cache_dir = Path(os.getenv("FASTEMBED_CACHE_PATH", str(Path.home() / ".cache" / "fastembed")))
            cache_dir.expanduser().mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir.expanduser()))
        except Exception as exc:
            raise EmbeddingModelError("Local FastEmbed model could not be loaded") from exc
        self.model_name = model_name

    def encode(self, texts: Iterable[str]) -> list[list[float]]:
        values = list(texts)
        if any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError("Embedding inputs must be non-empty strings")
        if not values:
            return []
        try:
            vectors = [vector.tolist() if hasattr(vector, "tolist") else list(vector)
                       for vector in self._model.embed(values)]
        except Exception as exc:
            raise EmbeddingModelError("Local embedding generation failed") from exc
        if len(vectors) != len(values):
            raise EmbeddingModelError("Embedding model returned an unexpected vector count")
        normalized: list[list[float]] = []
        for vector in vectors:
            if len(vector) != EMBEDDING_DIMENSION:
                raise EmbeddingModelError("Embedding model returned an unexpected vector dimension")
            row = [float(number) for number in vector]
            if not all(math.isfinite(number) for number in row):
                raise EmbeddingModelError("Embedding model returned a non-finite vector")
            normalized.append(row)
        return normalized


@lru_cache(maxsize=1)
def default_encoder() -> FastEmbedEncoder:
    return FastEmbedEncoder()
