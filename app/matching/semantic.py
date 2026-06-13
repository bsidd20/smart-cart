"""Embedding-based matching with an offline fallback.

If sentence-transformers is installed we use 'all-MiniLM-L6-v2' for real semantic
embeddings. Otherwise we fall back to a hashed character n-gram vector, which needs
no downloads and keeps the same interface, so switching is a one-line change. The
fallback only captures sub-word overlap, not meaning - see how matcher.py limits how
much it's trusted.
"""
from __future__ import annotations

import numpy as np

_EMBED_DIM = 512


class HashingNgramEmbedder:
    backend = "hashing-ngram"

    def __init__(self, dim: int = _EMBED_DIM, ngram_range=(2, 4)):
        self.dim = dim
        self.ngram_range = ngram_range

    def _vector(self, text: str) -> np.ndarray:
        text = f" {text.lower().strip()} "
        vec = np.zeros(self.dim, dtype=np.float32)
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                h = hash(gram)              # signed, to reduce bucket collisions
                vec[h % self.dim] += 1.0 if h >= 0 else -1.0
        norm = np.linalg.norm(vec)
        return vec if norm == 0 else vec / norm

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._vector(t) for t in texts]) if texts \
            else np.zeros((0, self.dim), dtype=np.float32)


class SentenceTransformerEmbedder:
    backend = "sentence-transformers"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # lazy import
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        return self._model.encode(texts, normalize_embeddings=True,
                                  convert_to_numpy=True).astype(np.float32)


def get_embedder():
    try:
        return SentenceTransformerEmbedder()
    except Exception:
        return HashingNgramEmbedder()


def cosine_similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)
    return matrix @ query_vec
