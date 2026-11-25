"""Benchmark mining report generation."""

import json
from collections import Counter
from pathlib import Path
from typing import Any


def generate_report(jsonl_path: Path) -> dict[str, Any]:
    """Generate statistics report from benchmark JSONL file."""
    if not jsonl_path.exists():
        return {"error": f"File not found: {jsonl_path}"}

    records = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not records:
        return {"total": 0, "message": "No records found"}

    # Basic counts
    total = len(records)

    # Split distribution
    split_counts = Counter(r.get("split_tag", "unknown") for r in records)

    # Repository distribution
    repo_counts: Counter[str] = Counter()
    for r in records:
        issue = r.get("issue", {})
        repo_key = f"{issue.get('owner', 'unknown')}/{issue.get('repo', 'unknown')}"
        repo_counts[repo_key] += 1

    # Gold files statistics
    gold_all_counts = [len(r.get("gold_files_all", [])) for r in records]
    gold_source_counts = [len(r.get("gold_files_source", [])) for r in records]

    # Changed files statistics
    changed_counts = [len(r.get("changed_files", [])) for r in records]

    # Date ranges
    merged_dates = [r.get("merged_at") for r in records if r.get("merged_at")]
    issue_dates = [r.get("issue_created_at") for r in records if r.get("issue_created_at")]
    pr_dates = [r.get("pr_opened_at") for r in records if r.get("pr_opened_at")]

    def parse_date(d: str) -> str:
        try:
            from datetime import datetime

            return datetime.fromisoformat(d.replace("Z", "+00:00")).date().isoformat()
        except Exception:
            return d

    report = {
        "total_examples": total,
        "split_distribution": dict(split_counts),
        "repository_distribution": dict(repo_counts),
        "gold_files_all": {
            "mean": sum(gold_all_counts) / len(gold_all_counts) if gold_all_counts else 0,
            "min": min(gold_all_counts) if gold_all_counts else 0,
            "max": max(gold_all_counts) if gold_all_counts else 0,
            "distribution": dict(Counter(gold_all_counts)),
        },
        "gold_files_source": {
            "mean": sum(gold_source_counts) / len(gold_source_counts) if gold_source_counts else 0,
            "min": min(gold_source_counts) if gold_source_counts else 0,
            "max": max(gold_source_counts) if gold_source_counts else 0,
            "distribution": dict(Counter(gold_source_counts)),
        },
        "changed_files": {
            "mean": sum(changed_counts) / len(changed_counts) if changed_counts else 0,
            "min": min(changed_counts) if changed_counts else 0,
            "max": max(changed_counts) if changed_counts else 0,
            "distribution": dict(Counter(changed_counts)),
        },
        "date_ranges": {
            "merged_at": {
                "min": parse_date(min(merged_dates)) if merged_dates else None,
                "max": parse_date(max(merged_dates)) if merged_dates else None,
            },
            "issue_created_at": {
                "min": parse_date(min(issue_dates)) if issue_dates else None,
                "max": parse_date(max(issue_dates)) if issue_dates else None,
            },
            "pr_opened_at": {
                "min": parse_date(min(pr_dates)) if pr_dates else None,
                "max": parse_date(max(pr_dates)) if pr_dates else None,
            },
        },
    }

    return report


def print_report(jsonl_path: Path) -> None:
    """Print human-readable report."""
    report = generate_report(jsonl_path)

    if "error" in report:
        print(f"Error: {report['error']}")
        return

    if "message" in report:
        print(report["message"])
        return

    print("=== Benchmark Dataset Report ===")
    print(f"Total examples: {report['total_examples']}")
    print()

    print("--- Split Distribution ---")
    for split, count in report["split_distribution"].items():
        pct = (count / report["total_examples"]) * 100
        print(f"  {split}: {count} ({pct:.1f}%)")
    print()

    print("--- Repository Distribution ---")
    for repo, count in report["repository_distribution"].items():
        pct = (count / report["total_examples"]) * 100
        print(f"  {repo}: {count} ({pct:.1f}%)")
    print()

    print("--- Gold Files (All) ---")
    gf = report["gold_files_all"]
    print(f"  Mean: {gf['mean']:.2f}, Min: {gf['min']}, Max: {gf['max']}")
    print(f"  Distribution: {gf['distribution']}")
    print()

    print("--- Gold Files (Source Only) ---")
    gf = report["gold_files_source"]
    print(f"  Mean: {gf['mean']:.2f}, Min: {gf['min']}, Max: {gf['max']}")
    print(f"  Distribution: {gf['distribution']}")
    print()

    print("--- Changed Files ---")
    cf = report["changed_files"]
    print(f"  Mean: {cf['mean']:.2f}, Min: {cf['min']}, Max: {cf['max']}")
    print(f"  Distribution: {cf['distribution']}")
    print()

    print("--- Date Ranges ---")
    for key, ranges in report["date_ranges"].items():
        print(f"  {key}: {ranges['min']} to {ranges['max']}")
