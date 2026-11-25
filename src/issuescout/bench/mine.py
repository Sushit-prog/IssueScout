"""Benchmark mining orchestration."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from issuescout.bench.config import BenchConfig, RepoConfig
from issuescout.bench.filters import (
    _compute_changed_files_with_locatable,
    _compute_gold_files_all,
    _compute_gold_files_source,
    apply_all_filters,
)
from issuescout.github.cache import ResponseCache
from issuescout.github.client import GitHubClient
from issuescout.github.models import ChangedFileData, FileStatus, IssueData, PRDetails
from issuescout.models import BenchmarkExample, ChangedFile, IssueRef, SplitTag

logger = logging.getLogger(__name__)


def monthly_windows(since: datetime, until: datetime) -> list[tuple[datetime, datetime]]:
    """Generate monthly windows from since to until (inclusive)."""
    windows = []
    current = since.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)

    while current <= until:
        # Calculate end of month
        if current.month == 12:
            next_month = current.replace(year=current.year + 1, month=1)
        else:
            next_month = current.replace(month=current.month + 1)

        window_end = min(next_month - timedelta(seconds=1), until)
        windows.append((current, window_end))
        current = next_month

    return windows


def build_search_query(owner: str, repo: str, window_start: datetime, window_end: datetime) -> str:
    """Build GraphQL search query for merged PRs in a time window."""
    start_str = window_start.strftime("%Y-%m-%d")
    end_str = window_end.strftime("%Y-%m-%d")
    return f"repo:{owner}/{repo} type:pr is:merged merged:{start_str}..{end_str}"


def pr_to_benchmark_example(
    issue: IssueData,
    pr: PRDetails,
    files: list[ChangedFileData],
    owner: str,
    repo: str,
    leakage_cutoff: datetime,
    base_commit_sha: str,
) -> BenchmarkExample:
    """Convert PR data to BenchmarkExample."""
    # Compute gold files
    gold_files_all = _compute_gold_files_all(files)
    gold_files_source = _compute_gold_files_source(files)
    changed_files_with_locatable = _compute_changed_files_with_locatable(files)

    # Build ChangedFile models
    changed_files = [
        ChangedFile(
            path=path,
            status=next(f.status.value for f in files if _file_matches(f, path)),
            additions=next(f.additions for f in files if _file_matches(f, path)),
            deletions=next(f.deletions for f in files if _file_matches(f, path)),
            locatable_at_base=locatable,
        )
        for path, locatable in changed_files_with_locatable
    ]

    # Determine split tag
    split_tag = SplitTag.POST_CUTOFF if issue.created_at >= leakage_cutoff else SplitTag.PRE_CUTOFF

    # merged_at should not be None for merged PRs, but handle just in case
    merged_at = pr.merged_at if pr.merged_at is not None else datetime.now(UTC)

    return BenchmarkExample(
        issue=IssueRef(owner=owner, repo=repo, number=issue.number),
        base_commit_sha=base_commit_sha,
        issue_title=issue.title,
        issue_body=issue.body or "",
        gold_files_all=gold_files_all,
        gold_files_source=gold_files_source,
        pr_number=pr.number,
        merged_at=merged_at,
        issue_created_at=issue.created_at,
        pr_opened_at=pr.created_at,
        changed_files=changed_files,
        split_tag=split_tag,
    )


def _file_matches(file_data: ChangedFileData, target_path: str) -> bool:
    """Check if a file data matches the target path (handles renames)."""
    if file_data.status == FileStatus.RENAMED:
        return file_data.previous_filename == target_path or file_data.filename == target_path
    return file_data.filename == target_path


def process_pr(
    client: GitHubClient,
    owner: str,
    repo: str,
    pr: PRDetails,
    leakage_cutoff: datetime,
) -> BenchmarkExample | None:
    """Process a single PR and return BenchmarkExample if it passes all filters."""
    # Fetch issue
    if not pr.closing_issues:
        return None

    issue_number = pr.closing_issues[0]
    try:
        issue = client.fetch_issue(owner, repo, issue_number)
    except Exception as e:
        logger.warning(f"Failed to fetch issue #{issue_number}: {e}")
        return None

    # Apply filters that need issue
    drop_reasons = apply_all_filters(issue, pr, [], owner, repo)
    if drop_reasons:
        logger.debug(f"PR #{pr.number} dropped: {drop_reasons}")
        return None

    # Fetch PR files
    try:
        files = client.fetch_pr_files(owner, repo, pr.number)
    except Exception as e:
        logger.warning(f"Failed to fetch files for PR #{pr.number}: {e}")
        return None

    # Apply file-based filters
    drop_reasons = apply_all_filters(issue, pr, files, owner, repo)
    if drop_reasons:
        logger.debug(f"PR #{pr.number} dropped after files: {drop_reasons}")
        return None

    # Fetch PR details to get base_commit_sha
    try:
        pr_details = client.fetch_pr_details(owner, repo, pr.number)
        base_commit_sha = pr_details.base_sha
    except Exception as e:
        logger.warning(f"Failed to fetch PR details for PR #{pr.number}: {e}")
        return None

    return pr_to_benchmark_example(
        issue=issue,
        pr=pr,
        files=files,
        owner=owner,
        repo=repo,
        leakage_cutoff=leakage_cutoff,
        base_commit_sha=base_commit_sha,
    )


def mine_repo(
    client: GitHubClient,
    repo_config: RepoConfig,
    bench_config: BenchConfig,
    out_path: Path,
) -> dict[str, int]:
    """Mine a single repository and append results to JSONL."""
    stats = {"processed": 0, "kept": 0, "dropped": 0, "errors": 0}

    # Load already processed PR numbers for resumability
    processed_prs = set()
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        processed_prs.add(record["pr_number"])
                    except json.JSONDecodeError:
                        pass

    owner = repo_config.owner
    repo = repo_config.name

    # Generate monthly windows
    since = repo_config.since or bench_config.leakage_cutoff
    until = repo_config.until or datetime.now(UTC)

    windows = monthly_windows(since, until)
    logger.info(f"Mining {owner}/{repo} across {len(windows)} monthly windows")

    for window_start, window_end in windows:
        if stats["kept"] >= repo_config.max_prs:
            break

        query = build_search_query(owner, repo, window_start, window_end)
        logger.info(f"Searching: {query}")

        cursor = None
        while stats["kept"] < repo_config.max_prs:
            try:
                page = client.fetch_merged_prs_page(
                    owner,
                    repo,
                    cursor=cursor,
                    per_page=100,
                    since=window_start.strftime("%Y-%m-%d"),
                    until=window_end.strftime("%Y-%m-%d"),
                )
            except Exception as e:
                logger.error(f"Search failed: {e}")
                stats["errors"] += 1
                break

            if not page.nodes:
                break

            for pr in page.nodes:
                if stats["kept"] >= repo_config.max_prs:
                    break

                if pr.number in processed_prs:
                    logger.debug(f"Skipping already processed PR #{pr.number}")
                    continue

                stats["processed"] += 1

                example = process_pr(client, owner, repo, pr, bench_config.leakage_cutoff)
                if example:
                    # Append to JSONL
                    with open(out_path, "a", encoding="utf-8") as f:
                        f.write(example.model_dump_json() + "\n")
                    stats["kept"] += 1
                    processed_prs.add(pr.number)
                    logger.info(f"Kept PR #{pr.number} (total: {stats['kept']})")
                else:
                    stats["dropped"] += 1

            if not page.page_info.has_next_page:
                break
            cursor = page.page_info.end_cursor

    return stats


def run_mining(config: BenchConfig) -> dict[str, dict[str, int]]:
    """Run benchmark mining for all configured repositories."""
    import os

    token = os.environ.get("GITHUB_TOKEN", "")
    client = GitHubClient(token=token, cache=ResponseCache(config.cache_dir_abs))
    all_stats = {}

    for repo_config in config.repos:
        logger.info(f"Starting mining for {repo_config.owner}/{repo_config.name}")
        stats = mine_repo(client, repo_config, config, config.out_path)
        all_stats[f"{repo_config.owner}/{repo_config.name}"] = stats
        logger.info(f"Completed {repo_config.owner}/{repo_config.name}: {stats}")

    return all_stats
