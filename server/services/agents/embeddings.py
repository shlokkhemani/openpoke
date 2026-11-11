"""Text embedders: a lazy FastEmbed wrapper and a deterministic hashing embedder for tests."""

from __future__ import annotations

import hashlib
import re
import threading
from typing import List, Protocol

import numpy as np


class Embedder(Protocol):
    def embed(self, texts: List[str]) -> np.ndarray:
        """Return an (n, D) float32 array with L2-normalised rows."""


def _normalise(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return np.divide(mat, norms, out=np.zeros_like(mat), where=norms > 0)


class FastEmbedder:
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        self._model_name = model
        self._model = None
        self._load_lock = threading.Lock()

    def embed(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(model_name=self._model_name)
        vecs = np.asarray(list(self._model.embed(list(texts))), dtype=np.float32)
        return _normalise(vecs.reshape(len(texts), -1))


class HashingEmbedder:
    """Bag of hashed words and character trigrams; stable across processes."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _features(self, text: str) -> List[str]:
        feats: List[str] = []
        for word in re.findall(r"\w+", text.casefold()):
            feats.append("w:" + word)
            padded = f" {word} "
            feats.extend("c:" + padded[i : i + 3] for i in range(len(padded) - 2))
        return feats

    def embed(self, texts: List[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feat in self._features(text):
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
                out[row, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        return _normalise(out)


__all__ = ["Embedder", "FastEmbedder", "HashingEmbedder"]
