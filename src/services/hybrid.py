"""Reciprocal Rank Fusion (RRF) — pure, backend-agnostic ranking function.

RRF merges multiple ranked lists into a single combined ranking without
requiring score normalisation across heterogeneous backends.

Formula (per document, per ranked list):
    rrf_score += 1 / (k + rank)          (rank is 1-based)

Where k = 60 (de-facto standard, reduces sensitivity to top-rank outliers).

Tie-breaking rule: when two documents share the same RRF score, the document
with the lexicographically smaller doc_id is ranked higher.  This guarantees
deterministic output regardless of insertion order.

References:
    Cormack, Clarke, Buettcher (2009). "Reciprocal Rank Fusion outperforms
    Condorcet and individual Rank Learning Methods."
"""

from __future__ import annotations

from src.core.vectorstore import ScoredId

# RRF smoothing constant — 60 is the de-facto standard
_RRF_K: int = 60


def reciprocal_rank_fusion(
    *ranked_lists: list[ScoredId],
    k: int = _RRF_K,
    top_n: int | None = None,
) -> list[ScoredId]:
    """Merge ranked lists via Reciprocal Rank Fusion.

    Args:
        *ranked_lists: One or more lists of ScoredId, each sorted by
                       descending relevance (best result at index 0).
                       The .score field of input items is ignored;
                       only their rank positions matter.
        k:             RRF smoothing constant (default 60).
        top_n:         If given, return only the top-n results.
                       None means return all documents.

    Returns:
        Combined list of ScoredId sorted by:
          1. Descending RRF score.
          2. Ascending doc_id (lexicographic) as tie-breaker.

    Raises:
        ValueError: If k < 1.
    """
    if k < 1:
        raise ValueError(f"RRF k must be >= 1, got {k}")

    # Accumulate RRF scores: doc_id -> float
    scores: dict[str, float] = {}

    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            contribution = 1.0 / (k + rank)
            scores[item.doc_id] = scores.get(item.doc_id, 0.0) + contribution

    # Sort: descending score, then ascending doc_id for deterministic tie-break
    sorted_items = sorted(
        scores.items(),
        key=lambda pair: (-pair[1], pair[0]),
    )

    if top_n is not None:
        sorted_items = sorted_items[:top_n]

    return [ScoredId(doc_id=doc_id, score=score) for doc_id, score in sorted_items]
