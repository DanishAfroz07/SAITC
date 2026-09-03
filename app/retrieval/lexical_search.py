"""A small pure-Python BM25 index - the lexical half of hybrid search. No new
dependency: the corpus is small enough (~100 chunks) that a plain Python
implementation is fast and avoids pulling in a search library for one score.
"""
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    def __init__(self, chunk_ids: list[str], texts: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self._chunk_ids = chunk_ids
        self._k1 = k1
        self._b = b

        term_freqs = [Counter(tokenize(text)) for text in texts]
        self._term_freqs = term_freqs
        self._doc_lengths = [sum(tf.values()) for tf in term_freqs]
        self._avg_doc_length = (sum(self._doc_lengths) / len(self._doc_lengths)) if term_freqs else 0.0

        self._doc_freq: Counter = Counter()
        for tf in term_freqs:
            self._doc_freq.update(tf.keys())
        self._n_docs = len(texts)

    def _idf(self, term: str) -> float:
        df = self._doc_freq.get(term, 0)
        return math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1)

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """Returns (chunk_id, bm25_score) pairs, highest score first."""
        if self._n_docs == 0:
            return []

        query_terms = tokenize(query)
        scores: list[tuple[str, float]] = []
        for i, tf in enumerate(self._term_freqs):
            score = 0.0
            doc_len = self._doc_lengths[i]
            for term in query_terms:
                freq = tf.get(term)
                if not freq:
                    continue
                idf = self._idf(term)
                denom = freq + self._k1 * (1 - self._b + self._b * doc_len / self._avg_doc_length)
                score += idf * (freq * (self._k1 + 1)) / denom
            if score > 0:
                scores.append((self._chunk_ids[i], score))

        scores.sort(key=lambda pair: pair[1], reverse=True)
        return scores[:top_k]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Combines several ranked id lists into one, by rank position rather than
    raw score - avoids needing to normalise BM25 scores against cosine
    similarity, which live on different, incomparable scales."""
    fused_scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(fused_scores, key=lambda chunk_id: fused_scores[chunk_id], reverse=True)
