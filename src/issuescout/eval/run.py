"""CLI for running evaluation of ranking methods."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from issuescout.baselines.bm25 import BM25Index
from issuescout.eval.metrics import RankingMetrics, compute_ranking_metrics
from issuescout.github.checkout import ensure_bare_repo, fetch_commit
from issuescout.tools.repo import list_files, read_files_batch

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="IssueScout evaluation runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Path to evaluation data JSONL file",
    )
    parser.add_argument(
        "--method",
        type=str,
        required=True,
        choices=["bm25"],
        help="Ranking method to evaluate",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=10,
        help="Number of top results to return per query",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for results JSON",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/repos"),
        help="Directory for bare repository cache",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=5000,
        help="Maximum files to index per repository",
    )
    parser.add_argument(
        "--origin-url",
        type=str,
        default=None,
        help=(
            "Custom origin URL for repository "
            "(e.g., file:///path/to/repo). Overrides default GitHub HTTPS URL."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def load_eval_data(data_path: Path) -> list[dict[str, Any]]:
    """Load evaluation data from JSONL file.

    Each line should be a JSON object with:
    - owner: repository owner
    - repo: repository name
    - base_commit: commit SHA to evaluate at
    - issue_text: issue title + body text
    - gold_files: list of gold file paths (repo-relative)
    """
    data = []
    with data_path.open() as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                data.append(obj)
            except json.JSONDecodeError as e:
                logger.error(f"Line {line_num}: Invalid JSON: {e}")
                raise
    return data


def get_bm25_results(
    bare_repo_path: Path,
    commit_sha: str,
    issue_text: str,
    k: int,
    max_files: int,
) -> list[tuple[str, float]]:
    """Run BM25 ranking on a repository at a specific commit.

    Args:
        bare_repo_path: Path to bare repository
        commit_sha: Commit SHA to evaluate at
        issue_text: Issue text to query with
        k: Number of top results
        max_files: Maximum files to index

    Returns:
        List of (file_path, score) tuples
    """
    # List source files at commit
    file_paths = list_files(
        bare_repo_path,
        commit_sha,
        max_files=max_files,
    )

    if not file_paths:
        logger.warning(f"No source files found at commit {commit_sha[:12]}")
        return []

    # Read file contents
    contents = read_files_batch(bare_repo_path, commit_sha, file_paths)

    # Build documents list
    documents = [(fp, contents[fp]) for fp in file_paths if fp in contents]

    if not documents:
        logger.warning(f"No readable files at commit {commit_sha[:12]}")
        return []

    # Build and query BM25 index
    index = BM25Index()
    index.build(documents)

    results = index.query(issue_text, k=k)
    return results


def evaluate_single(
    owner: str,
    repo: str,
    base_commit: str,
    issue_text: str,
    gold_files: list[str],
    cache_dir: Path,
    method: str,
    k: int,
    max_files: int,
    origin_url: str | None = None,
) -> tuple[RankingMetrics, list[str]]:
    """Evaluate a single issue-repo pair.

    Returns:
        Tuple of (RankingMetrics, predicted_file_list)
    """
    # Ensure bare repo exists and fetch commit
    bare_repo_path = ensure_bare_repo(cache_dir, owner, repo, origin_url=origin_url)
    fetch_commit(bare_repo_path, base_commit)

    # Run ranking method
    if method == "bm25":
        results = get_bm25_results(bare_repo_path, base_commit, issue_text, k, max_files)
    else:
        raise ValueError(f"Unknown method: {method}")

    predicted = [fp for fp, _ in results]

    # Compute metrics
    metrics = compute_ranking_metrics(set(gold_files), predicted)

    return metrics, predicted


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Load evaluation data
    logger.info(f"Loading evaluation data from {args.data}")
    eval_data = load_eval_data(args.data)
    logger.info(f"Loaded {len(eval_data)} evaluation instances")

    # Run evaluation
    all_metrics: list[RankingMetrics] = []
    all_predictions: list[dict[str, Any]] = []

    for i, item in enumerate(eval_data, 1):
        owner: str = item["owner"]
        repo: str = item["repo"]
        base_commit: str = item["base_commit"]
        issue_text: str = item["issue_text"]
        gold_files: list[str] = item["gold_files"]
        # Allow per-instance origin_url override from data file
        origin_url: str | None = item.get("origin_url", args.origin_url)

        logger.info(f"[{i}/{len(eval_data)}] Evaluating {owner}/{repo}@{base_commit[:12]}")

        try:
            metrics, predicted = evaluate_single(
                owner=owner,
                repo=repo,
                base_commit=base_commit,
                issue_text=issue_text,
                gold_files=gold_files,
                cache_dir=args.cache_dir,
                method=args.method,
                k=args.k,
                max_files=args.max_files,
                origin_url=origin_url,
            )
            all_metrics.append(metrics)
            all_predictions.append(
                {
                    "owner": owner,
                    "repo": repo,
                    "base_commit": base_commit,
                    "gold_files": gold_files,
                    "predicted_files": predicted,
                    "metrics": metrics.to_dict(),
                }
            )
            logger.info(
                f"  Recall@1: {metrics.recall_at_1:.3f}, "
                f"Recall@5: {metrics.recall_at_5:.3f}, "
                f"Recall@10: {metrics.recall_at_10:.3f}, "
                f"MRR: {metrics.mrr:.3f}"
            )
        except Exception as e:
            logger.error(f"  Failed: {e}")
            all_predictions.append(
                {
                    "owner": owner,
                    "repo": repo,
                    "base_commit": base_commit,
                    "gold_files": gold_files,
                    "predicted_files": [],
                    "metrics": None,
                    "error": str(e),
                }
            )

    # Aggregate metrics (excluding failed)
    successful = [m for m in all_metrics if m is not None]
    if successful:
        from issuescout.eval.metrics import aggregate_metrics

        agg = aggregate_metrics(successful)
        logger.info("=== AGGREGATE METRICS ===")
        logger.info(f"Recall@1:  {agg.recall_at_1:.3f}")
        logger.info(f"Recall@5:  {agg.recall_at_5:.3f}")
        logger.info(f"Recall@10: {agg.recall_at_10:.3f}")
        logger.info(f"Precision@1:  {agg.precision_at_1:.3f}")
        logger.info(f"Precision@5:  {agg.precision_at_5:.3f}")
        logger.info(f"Precision@10: {agg.precision_at_10:.3f}")
        logger.info(f"MRR:       {agg.mrr:.3f}")
        logger.info(f"MAP@10:    {agg.map_at_10:.3f}")

    # Write results
    output = {
        "method": args.method,
        "k": args.k,
        "total_instances": len(eval_data),
        "successful_instances": len(successful),
        "aggregate_metrics": agg.to_dict() if successful else None,
        "per_instance": all_predictions,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"Results written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
