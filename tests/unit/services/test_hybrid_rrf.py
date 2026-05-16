"""Tests for services.hybrid — reciprocal_rank_fusion pure function.

These tests verify:
- Basic single-list passthrough
- Multi-list score accumulation
- Tie-breaking by doc_id (ascending lexicographic)
- top_n filtering
- Invalid k raises ValueError
- Empty lists are handled gracefully
- Documents appearing in only one list still receive a score
"""

from __future__ import annotations

import pytest

from src.core.vectorstore import ScoredId
from src.services.hybrid import reciprocal_rank_fusion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ids(results: list[ScoredId]) -> list[str]:
    return [r.doc_id for r in results]


def _make(doc_id: str, score: float = 0.0) -> ScoredId:
    return ScoredId(doc_id=doc_id, score=score)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRRF:
    def test_single_list_preserves_order(self):
        ranked = [_make("a"), _make("b"), _make("c")]
        result = reciprocal_rank_fusion(ranked)
        assert _ids(result) == ["a", "b", "c"]

    def test_single_list_scores_decrease_monotonically(self):
        ranked = [_make("a"), _make("b"), _make("c")]
        result = reciprocal_rank_fusion(ranked)
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_document_in_both_lists_scores_higher(self):
        # "shared" appears rank-1 in both lists
        list1 = [_make("shared"), _make("only_1")]
        list2 = [_make("shared"), _make("only_2")]
        result = reciprocal_rank_fusion(list1, list2)
        ids = _ids(result)
        assert ids[0] == "shared"

    def test_all_documents_returned(self):
        list1 = [_make("a"), _make("b")]
        list2 = [_make("c"), _make("d")]
        result = reciprocal_rank_fusion(list1, list2)
        assert set(_ids(result)) == {"a", "b", "c", "d"}

    def test_tie_broken_by_doc_id_ascending(self):
        # Two documents each appear once at rank 1 in separate single-doc lists.
        # Their RRF scores are identical, so the lesser doc_id wins.
        list1 = [_make("zzz")]
        list2 = [_make("aaa")]
        result = reciprocal_rank_fusion(list1, list2)
        assert _ids(result) == ["aaa", "zzz"]

    def test_top_n_truncates_result(self):
        ranked = [_make("a"), _make("b"), _make("c"), _make("d")]
        result = reciprocal_rank_fusion(ranked, top_n=2)
        assert len(result) == 2

    def test_top_n_none_returns_all(self):
        ranked = [_make(str(i)) for i in range(10)]
        result = reciprocal_rank_fusion(ranked, top_n=None)
        assert len(result) == 10

    def test_empty_input_returns_empty(self):
        result = reciprocal_rank_fusion([])
        assert result == []

    def test_no_lists_returns_empty(self):
        result = reciprocal_rank_fusion()
        assert result == []

    def test_invalid_k_raises(self):
        with pytest.raises(ValueError, match="k must be >= 1"):
            reciprocal_rank_fusion([_make("a")], k=0)

    def test_negative_k_raises(self):
        with pytest.raises(ValueError, match="k must be >= 1"):
            reciprocal_rank_fusion([_make("a")], k=-5)

    def test_custom_k_affects_scores(self):
        ranked = [_make("a")]
        result_k1 = reciprocal_rank_fusion(ranked, k=1)
        result_k60 = reciprocal_rank_fusion(ranked, k=60)
        # With k=1, score = 1/(1+1) = 0.5
        # With k=60, score = 1/(60+1) ≈ 0.0164
        assert result_k1[0].score > result_k60[0].score

    def test_scores_are_positive(self):
        ranked = [_make("a"), _make("b")]
        result = reciprocal_rank_fusion(ranked)
        assert all(r.score > 0 for r in result)

    def test_result_items_are_scored_id_instances(self):
        ranked = [_make("x")]
        result = reciprocal_rank_fusion(ranked)
        assert all(isinstance(r, ScoredId) for r in result)

    def test_three_lists_cumulative_score(self):
        # "a" appears at rank 1 in all three lists
        list1 = [_make("a"), _make("b")]
        list2 = [_make("a"), _make("c")]
        list3 = [_make("a"), _make("d")]
        result = reciprocal_rank_fusion(list1, list2, list3)
        assert result[0].doc_id == "a"
        # Score for "a" must be > score for any single-list document
        single_max = max(r.score for r in result if r.doc_id != "a")
        assert result[0].score > single_max

    def test_input_scores_are_ignored(self):
        """The .score field of input ScoredId is irrelevant; only rank matters."""
        high_score_last = _make("b", score=999.0)
        low_score_first = _make("a", score=0.001)
        result = reciprocal_rank_fusion([low_score_first, high_score_last])
        # "a" is rank 1, so its RRF score is higher regardless of input score
        assert result[0].doc_id == "a"
