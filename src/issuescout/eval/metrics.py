"""Evaluation metrics for ranking quality (zero LLM calls)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankingMetrics:
    """Container for all ranking metrics at various k values."""

    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    precision_at_1: float
    precision_at_5: float
    precision_at_10: float
    mrr: float
    map_at_10: float

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary for serialization."""
        return {
            "recall@1": self.recall_at_1,
            "recall@5": self.recall_at_5,
            "recall@10": self.recall_at_10,
            "precision@1": self.precision_at_1,
            "precision@5": self.precision_at_5,
            "precision@10": self.precision_at_10,
            "mrr": self.mrr,
            "map@10": self.map_at_10,
        }


def recall_at_k(relevant: list[str] | set[str], predicted: list[str], k: int) -> float:
    """Compute Recall@K.

    Args:
        relevant: List or set of relevant (gold) document IDs
        predicted: List of predicted document IDs (ranked)
        k: Cutoff rank

    Returns:
        Recall@K score (0.0 to 1.0)
    """
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant
    if not relevant_set:
        return 1.0  # No relevant docs, perfect recall by convention

    predicted_at_k = set(predicted[:k])
    return len(relevant_set & predicted_at_k) / len(relevant_set)


def precision_at_k(relevant: list[str] | set[str], predicted: list[str], k: int) -> float:
    """Compute Precision@K.

    Args:
        relevant: List or set of relevant (gold) document IDs
        predicted: List of predicted document IDs (ranked)
        k: Cutoff rank

    Returns:
        Precision@K score (0.0 to 1.0)
    """
    if k == 0:
        return 0.0

    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant
    # Standard definition: relevant items in top-k divided by k
    predicted_at_k = predicted[:k]
    if not predicted_at_k:
        return 0.0

    hits = sum(1 for doc_id in predicted_at_k if doc_id in relevant_set)
    return hits / k


def average_precision_at_k(relevant: set[str], predicted: list[str], k: int) -> float:
    """Compute Average Precision@K (AP@K).

    Args:
        relevant: Set of relevant (gold) document IDs
        predicted: List of predicted document IDs (ranked)
        k: Cutoff rank

    Returns:
        AP@K score (0.0 to 1.0)
    """
    if not relevant:
        return 1.0

    score = 0.0
    hits = 0
    for i, doc_id in enumerate(predicted[:k], 1):
        if doc_id in relevant:
            hits += 1
            score += hits / i

    return score / min(len(relevant), k)


def mean_reciprocal_rank(relevant: set[str], predicted: list[str]) -> float:
    """Compute Mean Reciprocal Rank (MRR).

    Args:
        relevant: Set of relevant (gold) document IDs
        predicted: List of predicted document IDs (ranked)

    Returns:
        MRR score (0.0 to 1.0)
    """
    for i, doc_id in enumerate(predicted, 1):
        if doc_id in relevant:
            return 1.0 / i
    return 0.0


def compute_ranking_metrics(
    relevant: set[str] | list[str],
    predicted: list[str],
    k_values: tuple[int, ...] = (1, 5, 10),
) -> RankingMetrics:
    """Compute all ranking metrics for a single query.

    Args:
        relevant: Set or list of relevant (gold) document IDs
        predicted: List of predicted document IDs (ranked by relevance)
        k_values: Tuple of k values to compute metrics for (default: 1, 5, 10)

    Returns:
        RankingMetrics with all computed metrics
    """
    relevant_set = set(relevant) if not isinstance(relevant, set) else relevant

    # Recall@K
    recall_at_1 = recall_at_k(relevant_set, predicted, 1)
    recall_at_5 = recall_at_k(relevant_set, predicted, 5)
    recall_at_10 = recall_at_k(relevant_set, predicted, 10)

    # Precision@K
    precision_at_1 = precision_at_k(relevant_set, predicted, 1)
    precision_at_5 = precision_at_k(relevant_set, predicted, 5)
    precision_at_10 = precision_at_k(relevant_set, predicted, 10)

    # MRR
    mrr = mean_reciprocal_rank(relevant_set, predicted)

    # MAP@10
    map_at_10 = average_precision_at_k(relevant_set, predicted, 10)

    return RankingMetrics(
        recall_at_1=recall_at_1,
        recall_at_5=recall_at_5,
        recall_at_10=recall_at_10,
        precision_at_1=precision_at_1,
        precision_at_5=precision_at_5,
        precision_at_10=precision_at_10,
        mrr=mrr,
        map_at_10=map_at_10,
    )


def aggregate_metrics(metrics_list: list[RankingMetrics]) -> RankingMetrics:
    """Aggregate metrics across multiple queries by averaging.

    Args:
        metrics_list: List of RankingMetrics from individual queries

    Returns:
        Averaged RankingMetrics
    """
    if not metrics_list:
        return RankingMetrics(
            recall_at_1=0.0,
            recall_at_5=0.0,
            recall_at_10=0.0,
            precision_at_1=0.0,
            precision_at_5=0.0,
            precision_at_10=0.0,
            mrr=0.0,
            map_at_10=0.0,
        )

    n = len(metrics_list)
    return RankingMetrics(
        recall_at_1=sum(m.recall_at_1 for m in metrics_list) / n,
        recall_at_5=sum(m.recall_at_5 for m in metrics_list) / n,
        recall_at_10=sum(m.recall_at_10 for m in metrics_list) / n,
        precision_at_1=sum(m.precision_at_1 for m in metrics_list) / n,
        precision_at_5=sum(m.precision_at_5 for m in metrics_list) / n,
        precision_at_10=sum(m.precision_at_10 for m in metrics_list) / n,
        mrr=sum(m.mrr for m in metrics_list) / n,
        map_at_10=sum(m.map_at_10 for m in metrics_list) / n,
    )
