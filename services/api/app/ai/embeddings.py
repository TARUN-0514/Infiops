"""Embeddings for memory search. When no embedding model is configured, search uses
full-text ranking only."""

import hashlib
import math
from typing import Protocol

import httpx

from app.core.config import get_settings
from app.core.logging import log
from app.models.memory import EMBEDDING_DIM


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]] | None: ...


class NoEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        return None


class OllamaEmbedder:
    def __init__(self, url: str, model: str) -> None:
        self._url, self._model = url.rstrip("/"), model

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{self._url}/api/embed", json={"model": self._model, "input": texts}
                )
                r.raise_for_status()
                vectors: list[list[float]] = r.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("embedding_failed", error=type(exc).__name__)
            return None
        if any(len(v) != EMBEDDING_DIM for v in vectors):
            log.warning("embedding_dimension_mismatch", model=self._model)
            return None
        return vectors


class HashEmbedder:
    """Deterministic bag-of-words vectors so tests can exercise vector search."""

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        out = []
        for text in texts:
            vec = [0.0] * EMBEDDING_DIM
            for word in text.lower().split():
                w = word.strip(".,!?;:'\"")
                if len(w) < 3:
                    continue
                h = int(hashlib.sha256(w.encode()).hexdigest(), 16)
                vec[h % EMBEDDING_DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_provider == "ollama":
        return OllamaEmbedder(s.ollama_url, s.embedding_model)
    if s.embedding_provider == "hash":
        return HashEmbedder()
    return NoEmbedder()
