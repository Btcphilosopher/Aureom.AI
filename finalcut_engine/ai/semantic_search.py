"""Semantic-ish search over library assets: "find sunset footage", "find people talking".

The reference implementation is TF-IDF + cosine similarity over each asset's
keywords/transcript/metadata text — genuinely functional lexical search
without an embedding-model dependency. Swap ``embed_fn`` for a real text
embedding model to get true semantic (not just lexical) matching; the
ranking/query API does not change.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class SemanticSearchIndex:
    """Indexes arbitrary (id, text) documents; typically one per :class:`MediaAsset`."""

    embed_fn: Optional[Callable[[str], np.ndarray]] = None  # pluggable real embedding model
    _documents: Dict[str, str] = field(default_factory=dict)
    _doc_freq: Counter = field(default_factory=Counter)

    def add_document(self, doc_id: str, text: str) -> None:
        if doc_id in self._documents:
            self._remove_from_doc_freq(doc_id)
        self._documents[doc_id] = text
        for token in set(tokenize(text)):
            self._doc_freq[token] += 1

    def _remove_from_doc_freq(self, doc_id: str) -> None:
        for token in set(tokenize(self._documents[doc_id])):
            self._doc_freq[token] -= 1

    def _tfidf_vector(self, text: str) -> Dict[str, float]:
        tokens = tokenize(text)
        if not tokens:
            return {}
        counts = Counter(tokens)
        n_docs = max(1, len(self._documents))
        vector = {}
        for token, count in counts.items():
            tf = count / len(tokens)
            idf = math.log(1 + n_docs / (1 + self._doc_freq.get(token, 0)))
            vector[token] = tf * idf
        return vector

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        norm_a = math.sqrt(sum(v * v for v in a.values())) or 1.0
        norm_b = math.sqrt(sum(v * v for v in b.values())) or 1.0
        return dot / (norm_a * norm_b)

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        if self.embed_fn is not None:
            return self._search_embedding(query, top_k)
        query_vec = self._tfidf_vector(query)
        scored = [(doc_id, self._cosine(query_vec, self._tfidf_vector(text))) for doc_id, text in self._documents.items()]
        scored = [(doc_id, score) for doc_id, score in scored if score > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def _search_embedding(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        query_emb = self.embed_fn(query)
        scored = []
        for doc_id, text in self._documents.items():
            doc_emb = self.embed_fn(text)
            denom = (np.linalg.norm(query_emb) * np.linalg.norm(doc_emb)) or 1.0
            scored.append((doc_id, float(np.dot(query_emb, doc_emb) / denom)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
