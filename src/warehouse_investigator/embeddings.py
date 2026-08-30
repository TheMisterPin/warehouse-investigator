from __future__ import annotations

import math
import os
import re
import zlib
from typing import Protocol

from .ollama import OllamaClient

DEFAULT_EMBED_MODEL = "nomic-embed-text"


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic offline embedder for tests. Similar tokens land in similar vectors."""

    model = "hash-stub"
    dimension = 64

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in re.findall(r"[a-z0-9_-]+", text.lower()):
                vector[zlib.adler32(token.encode("utf-8")) % self.dimension] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class OllamaEmbedder:
    def __init__(self, client: OllamaClient | None = None, model: str | None = None) -> None:
        self.client = client or OllamaClient()
        self.model = model or os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.client.embed(texts, model=self.model)
