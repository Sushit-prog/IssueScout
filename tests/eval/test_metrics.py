"""Tests for evaluation metrics."""

from issuescout.eval.metrics import (
    RankingMetrics,
    aggregate_metrics,
    average_precision_at_k,
    compute_ranking_metrics,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)


class TestRecallAtK:
    """Tests for recall_at_k function."""

    def test_perfect_recall(self):
        """Test recall when all relevant docs are in top-k."""
        relevant = {"a", "b", "c"}
        predicted = ["a", "b", "c", "d", "e"]
        assert recall_at_k(relevant, predicted, 3) == 1.0
        assert recall_at_k(relevant, predicted, 5) == 1.0

    def test_partial_recall(self):
        """Test recall when some relevant docs are in top-k."""
        relevant = {"a", "b", "c"}
        predicted = ["a", "d", "e"]
        assert recall_at_k(relevant, predicted, 3) == 1 / 3

    def test_zero_recall(self):
        """Test recall when no relevant docs in top-k."""
        relevant = {"a", "b", "c"}
        predicted = ["d", "e", "f"]
        assert recall_at_k(relevant, predicted, 3) == 0.0

    def test_empty_relevant(self):
        """Test recall with empty relevant set (convention: 1.0)."""
        relevant = set()
        predicted = ["a", "b", "c"]
        assert recall_at_k(relevant, predicted, 3) == 1.0

    def test_k_larger_than_predicted(self):
        """Test recall when k > len(predicted)."""
        relevant = {"a", "b"}
        predicted = ["a"]
        assert recall_at_k(relevant, predicted, 5) == 0.5

    def test_relevant_as_list(self):
        """Test recall works with list input."""
        relevant = ["a", "b", "c"]
        predicted = ["a", "b", "d"]
        assert recall_at_k(relevant, predicted, 3) == 2 / 3


class TestPrecisionAtK:
    """Tests for precision_at_k function."""

    def test_perfect_precision(self):
        """Test precision when all top-k are relevant."""
        relevant = {"a", "b", "c"}
        predicted = ["a", "b", "c", "d", "e"]
        assert precision_at_k(relevant, predicted, 3) == 1.0

    def test_partial_precision(self):
        """Test precision when some top-k are relevant."""
        relevant = {"a", "b", "c"}
        predicted = ["a", "d", "e"]
        assert precision_at_k(relevant, predicted, 3) == 1 / 3

    def test_zero_precision(self):
        """Test precision when no top-k are relevant."""
        relevant = {"a", "b", "c"}
        predicted = ["d", "e", "f"]
        assert precision_at_k(relevant, predicted, 3) == 0.0

    def test_k_zero(self):
        """Test precision with k=0."""
        relevant = {"a", "b"}
        predicted = ["a", "b"]
        assert precision_at_k(relevant, predicted, 0) == 0.0

    def test_k_larger_than_predicted(self):
        """Test precision when k > len(predicted).

        Standard precision@k = hits / k. With 1 hit and k=5, precision = 1/5 = 0.2.
        """
        relevant = {"a", "b"}
        predicted = ["a"]
        assert precision_at_k(relevant, predicted, 5) == 0.2


class TestAveragePrecisionAtK:
    """Tests for average_precision_at_k function."""

    def test_perfect_ap(self):
        """Test AP when all relevant at top."""
        relevant = {"a", "b", "c"}
        predicted = ["a", "b", "c", "d", "e"]
        assert average_precision_at_k(relevant, predicted, 10) == 1.0

    def test_partial_ap(self):
        """Test AP with partial ranking."""
        relevant = {"a", "b", "c"}
        # a at rank 1, b at rank 3, c not in top-5
        predicted = ["a", "d", "b", "e", "f"]
        # AP = (1/1 + 2/3) / min(3, 5) = (1 + 0.666...) / 3 = 1.666.../3 = 0.555...
        ap = average_precision_at_k(relevant, predicted, 5)
        assert abs(ap - (1 + 2 / 3) / 3) < 0.001

    def test_empty_relevant(self):
        """Test AP with empty relevant (convention: 1.0)."""
        relevant = set()
        predicted = ["a", "b", "c"]
        assert average_precision_at_k(relevant, predicted, 5) == 1.0

    def test_no_relevant_in_predicted(self):
        """Test AP when no relevant docs in predicted."""
        relevant = {"a", "b"}
        predicted = ["c", "d", "e"]
        assert average_precision_at_k(relevant, predicted, 5) == 0.0


class TestMeanReciprocalRank:
    """Tests for mean_reciprocal_rank function."""

    def test_first_result_relevant(self):
        """Test MRR when first result is relevant."""
        relevant = {"a", "b"}
        predicted = ["a", "c", "d"]
        assert mean_reciprocal_rank(relevant, predicted) == 1.0

    def test_second_result_relevant(self):
        """Test MRR when second result is relevant."""
        relevant = {"b"}
        predicted = ["a", "b", "c"]
        assert mean_reciprocal_rank(relevant, predicted) == 0.5

    def test_third_result_relevant(self):
        """Test MRR when third result is relevant."""
        relevant = {"c"}
        predicted = ["a", "b", "c"]
        assert mean_reciprocal_rank(relevant, predicted) == 1 / 3

    def test_no_relevant(self):
        """Test MRR when no relevant in predicted."""
        relevant = {"x", "y"}
        predicted = ["a", "b", "c"]
        assert mean_reciprocal_rank(relevant, predicted) == 0.0

    def test_empty_relevant(self):
        """Test MRR with empty relevant."""
        relevant = set()
        predicted = ["a", "b"]
        assert mean_reciprocal_rank(relevant, predicted) == 0.0


class TestComputeRankingMetrics:
    """Tests for compute_ranking_metrics function."""

    def test_basic_metrics(self):
        """Test computing all metrics at once."""
        relevant = {"a", "b", "c"}
        predicted = ["a", "d", "b", "e", "c", "f"]

        metrics = compute_ranking_metrics(relevant, predicted)

        # Recall: 1/3 at k=1 (a), 2/3 at k=3 (a,b), 3/3 at k=5 (a,b,c)
        assert metrics.recall_at_1 == 1 / 3
        assert metrics.recall_at_5 == 1.0
        assert metrics.recall_at_10 == 1.0

        # Precision: 1/1 at k=1, 3/5 at k=5, 3/10 at k=10
        assert metrics.precision_at_1 == 1.0
        assert abs(metrics.precision_at_5 - 3 / 5) < 0.001
        assert abs(metrics.precision_at_10 - 3 / 10) < 0.001

        # MRR: first relevant at position 1
        assert metrics.mrr == 1.0

    def test_to_dict(self):
        """Test to_dict serialization."""
        relevant = {"a", "b"}
        predicted = ["a", "b"]
        metrics = compute_ranking_metrics(relevant, predicted)
        d = metrics.to_dict()
        assert "recall@1" in d
        assert "recall@5" in d
        assert "recall@10" in d
        assert "precision@1" in d
        assert "precision@5" in d
        assert "precision@10" in d
        assert "mrr" in d
        assert "map@10" in d


class TestAggregateMetrics:
    """Tests for aggregate_metrics function."""

    def test_average_two_queries(self):
        """Test averaging metrics across queries."""
        m1 = RankingMetrics(
            recall_at_1=1.0,
            recall_at_5=1.0,
            recall_at_10=1.0,
            precision_at_1=1.0,
            precision_at_5=1.0,
            precision_at_10=1.0,
            mrr=1.0,
            map_at_10=1.0,
        )
        m2 = RankingMetrics(
            recall_at_1=0.0,
            recall_at_5=0.0,
            recall_at_10=0.0,
            precision_at_1=0.0,
            precision_at_5=0.0,
            precision_at_10=0.0,
            mrr=0.0,
            map_at_10=0.0,
        )
        avg = aggregate_metrics([m1, m2])
        assert avg.recall_at_1 == 0.5
        assert avg.mrr == 0.5

    def test_empty_list(self):
        """Test aggregating empty list returns zeros."""
        avg = aggregate_metrics([])
        assert avg.recall_at_1 == 0.0
        assert avg.mrr == 0.0
