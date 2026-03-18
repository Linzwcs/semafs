"""Retrieval scoring helpers for category metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\\-\\u4e00-\\u9fff]{2,}")


@dataclass(frozen=True)
class RetrievalWeights:
    """Weighted scoring config for keyword/summary hybrid retrieval."""

    keyword_weight: float = 0.65
    summary_weight: float = 0.35

    def normalized(self) -> "RetrievalWeights":
        total = self.keyword_weight + self.summary_weight
        if total <= 0:
            return RetrievalWeights(0.65, 0.35)
        return RetrievalWeights(
            keyword_weight=self.keyword_weight / total,
            summary_weight=self.summary_weight / total,
        )


def score_category_text(
    query: str,
    keywords: tuple[str, ...],
    summary: str,
    weights: RetrievalWeights | None = None,
) -> float:
    """Compute hybrid retrieval score using keywords + summary."""
    cfg = (weights or RetrievalWeights()).normalized()
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0

    keyword_score = _coverage_score(q_tokens, _tokenize(" ".join(keywords)))
    summary_score = _coverage_score(q_tokens, _tokenize(summary))
    return (
        cfg.keyword_weight * keyword_score
        + cfg.summary_weight * summary_score
    )


def _coverage_score(query_tokens: set[str], corpus_tokens: set[str]) -> float:
    if not query_tokens or not corpus_tokens:
        return 0.0
    hit = len(query_tokens.intersection(corpus_tokens))
    return hit / len(query_tokens)


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}
