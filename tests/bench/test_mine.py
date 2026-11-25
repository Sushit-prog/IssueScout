"""Tests for benchmark mining orchestration."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from issuescout.bench.config import BenchConfig, RepoConfig
from issuescout.bench.mine import (
    build_search_query,
    mine_repo,
    monthly_windows,
    pr_to_benchmark_example,
    process_pr,
    run_mining,
)
from issuescout.github.models import (
    ChangedFileData,
    FileStatus,
    IssueData,
    PageInfo,
    PRDetails,
    PRPage,
)
from issuescout.models import BenchmarkExample, IssueRef, SplitTag


def _make_pr(**kwargs) -> PRDetails:
    """Create a minimal valid PRDetails for testing."""
    now = datetime.now(UTC)
    defaults = {
        "number": 1,
        "title": "Test PR",
        "body": "Body",
        "state": "closed",
        "merged": True,
        "mergeable": True,
        "created_at": now,
        "updated_at": now,
        "closed_at": now,
        "merged_at": now,
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "base_ref": "main",
        "head_ref": "feature",
        "html_url": "https://github.com/o/r/pull/1",
        "closing_issues": [],
    }
    defaults.update(kwargs)
    return PRDetails(**defaults)


def _make_issue(**kwargs) -> IssueData:
    """Create a minimal valid IssueData for testing."""
    now = datetime.now(UTC)
    defaults = {
        "number": 42,
        "title": "Test Issue",
        "body": "Body",
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "state": "closed",
        "html_url": "https://github.com/o/r/issues/42",
    }
    defaults.update(kwargs)
    return IssueData(**defaults)


class TestMonthlyWindows:
    """Tests for monthly window generation."""

    def test_single_month(self):
        since = datetime(2025, 6, 1, tzinfo=UTC)
        until = datetime(2025, 6, 30, 23, 59, 59, tzinfo=UTC)
        windows = monthly_windows(since, until)
        assert len(windows) == 1
        assert windows[0][0] == datetime(2025, 6, 1, tzinfo=UTC)
        assert windows[0][1] == until

    def test_multiple_months(self):
        since = datetime(2025, 6, 1, tzinfo=UTC)
        until = datetime(2025, 8, 15, tzinfo=UTC)
        windows = monthly_windows(since, until)
        assert len(windows) == 3
        assert windows[0] == (
            datetime(2025, 6, 1, tzinfo=UTC),
            datetime(2025, 6, 30, 23, 59, 59, tzinfo=UTC),
        )
        assert windows[1] == (
            datetime(2025, 7, 1, tzinfo=UTC),
            datetime(2025, 7, 31, 23, 59, 59, tzinfo=UTC),
        )
        assert windows[2][0] == datetime(2025, 8, 1, tzinfo=UTC)
        assert windows[2][1] == until


class TestBuildSearchQuery:
    """Tests for GraphQL search query building."""

    def test_build_search_query(self):
        query = build_search_query(
            "pallets",
            "flask",
            datetime(2025, 6, 1, tzinfo=UTC),
            datetime(2025, 6, 30, 23, 59, 59, tzinfo=UTC),
        )
        assert query == "repo:pallets/flask type:pr is:merged merged:2025-06-01..2025-06-30"


class TestPrToBenchmarkExample:
    """Tests for PR to BenchmarkExample conversion."""

    def test_pr_to_benchmark_example(self):
        issue = _make_issue(
            number=42,
            title="Fix bug",
            body="Bug description",
            created_at=datetime(2025, 7, 10, tzinfo=UTC),
            updated_at=datetime(2025, 7, 11, tzinfo=UTC),
        )
        pr = _make_pr(
            number=100,
            title="Fix",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[42],
            base_sha="abc123def4567890abc123def4567890abc123de",
        )
        files = [
            ChangedFileData(
                filename="src/auth.py", status=FileStatus.MODIFIED, additions=10, deletions=5
            ),
            ChangedFileData(
                filename="tests/test_auth.py", status=FileStatus.ADDED, additions=20, deletions=0
            ),
            ChangedFileData(
                filename="src/new.py",
                status=FileStatus.RENAMED,
                previous_filename="src/old.py",
                additions=5,
                deletions=5,
            ),
            ChangedFileData(
                filename="src/deleted.py", status=FileStatus.REMOVED, additions=0, deletions=10
            ),
        ]
        leakage_cutoff = datetime(2025, 6, 1, tzinfo=UTC)

        example = pr_to_benchmark_example(
            issue=issue,
            pr=pr,
            files=files,
            owner="pallets",
            repo="flask",
            leakage_cutoff=leakage_cutoff,
            base_commit_sha="abc123def4567890abc123def4567890abc123de",
        )

        assert isinstance(example, BenchmarkExample)
        assert example.issue == IssueRef(owner="pallets", repo="flask", number=42)
        assert example.base_commit_sha == "abc123def4567890abc123def4567890abc123de"
        assert example.issue_title == "Fix bug"
        assert example.issue_body == "Bug description"
        assert example.gold_files_all == ["src/auth.py", "src/old.py", "src/deleted.py"]
        assert example.gold_files_source == ["src/auth.py", "src/old.py", "src/deleted.py"]
        assert example.pr_number == 100
        assert example.merged_at == datetime(2025, 7, 15, tzinfo=UTC)
        assert example.issue_created_at == datetime(2025, 7, 10, tzinfo=UTC)
        assert example.pr_opened_at == datetime(2025, 7, 12, tzinfo=UTC)
        assert example.split_tag == SplitTag.POST_CUTOFF

        # Check changed_files (renamed files produce two entries: old_path and new_path)
        # Also includes added files (tests/test_auth.py) with locatable_at_base=False
        assert len(example.changed_files) == 5
        paths = {cf.path for cf in example.changed_files}
        assert paths == {
            "src/auth.py",
            "src/old.py",
            "src/new.py",
            "src/deleted.py",
            "tests/test_auth.py",
        }

        # Check locatable_at_base
        locatable = {cf.path: cf.locatable_at_base for cf in example.changed_files}
        assert locatable["src/auth.py"] is True
        assert locatable["src/old.py"] is True
        assert locatable["src/deleted.py"] is True
        assert locatable["src/new.py"] is False  # new path from rename not at base
        assert locatable["tests/test_auth.py"] is False  # added file


class TestProcessPr:
    """Tests for process_pr function."""

    def test_process_pr_success(self):
        client = MagicMock()
        issue = _make_issue(
            number=42,
            title="Fix bug",
            body="Bug description",
            created_at=datetime(2025, 7, 10, tzinfo=UTC),
            updated_at=datetime(2025, 7, 11, tzinfo=UTC),
        )
        pr = _make_pr(
            number=100,
            title="Fix",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[42],
            base_sha="abc123def4567890abc123def4567890abc123de",
        )
        files = [
            ChangedFileData(
                filename="src/auth.py", status=FileStatus.MODIFIED, additions=10, deletions=5
            ),
        ]

        client.fetch_issue.return_value = issue
        client.fetch_pr_files.return_value = files
        client.fetch_pr_details.return_value = _make_pr(
            number=100,
            title="Fix",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[42],
            base_sha="abc123def4567890abc123def4567890abc123de",
        )

        leakage_cutoff = datetime(2025, 6, 1, tzinfo=UTC)

        example = process_pr(client, "pallets", "flask", pr, leakage_cutoff)

        assert example is not None
        assert example.pr_number == 100
        client.fetch_issue.assert_called_once_with("pallets", "flask", 42)
        client.fetch_pr_files.assert_called_once_with("pallets", "flask", 100)
        client.fetch_pr_details.assert_called_once_with("pallets", "flask", 100)

    def test_process_pr_no_closing_issues(self):
        client = MagicMock()
        pr = _make_pr(
            number=100,
            title="Fix",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[],
            base_sha="sha",
        )
        leakage_cutoff = datetime(2025, 6, 1, tzinfo=UTC)

        example = process_pr(client, "pallets", "flask", pr, leakage_cutoff)

        assert example is None
        client.fetch_issue.assert_not_called()

    def test_process_pr_fetch_issue_fails(self):
        client = MagicMock()
        pr = _make_pr(
            number=100,
            title="Fix",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[42],
            base_sha="sha",
        )
        client.fetch_issue.side_effect = Exception("API error")
        leakage_cutoff = datetime(2025, 6, 1, tzinfo=UTC)

        example = process_pr(client, "pallets", "flask", pr, leakage_cutoff)

        assert example is None

    def test_process_pr_filtered_out(self):
        client = MagicMock()
        issue = _make_issue(
            number=42,
            title="Fix bug",
            body="",  # Empty body - will be filtered
            created_at=datetime(2025, 7, 10, tzinfo=UTC),
            updated_at=datetime(2025, 7, 11, tzinfo=UTC),
        )
        pr = _make_pr(
            number=100,
            title="Fix",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[42],
            base_sha="sha",
        )
        client.fetch_issue.return_value = issue
        leakage_cutoff = datetime(2025, 6, 1, tzinfo=UTC)

        example = process_pr(client, "pallets", "flask", pr, leakage_cutoff)

        assert example is None


class TestMineRepo:
    """Tests for mine_repo function."""

    def test_mine_repo_skips_processed(self, tmp_path):
        client = MagicMock()
        out_path = tmp_path / "bench.jsonl"

        # Pre-populate with one record
        existing = {
            "issue": {"owner": "pallets", "repo": "flask", "number": 42},
            "base_commit_sha": "sha",
            "issue_title": "t",
            "issue_body": "b",
            "gold_files_all": ["a.py"],
            "gold_files_source": ["a.py"],
            "pr_number": 100,
            "merged_at": "2025-07-15T10:30:00+00:00",
            "issue_created_at": "2025-07-10T10:30:00+00:00",
            "pr_opened_at": "2025-07-12T10:30:00+00:00",
            "changed_files": [],
            "split_tag": "post_cutoff",
        }
        out_path.write_text(json.dumps(existing) + "\n")

        repo_config = RepoConfig(owner="pallets", name="flask", max_prs=500)
        bench_config = BenchConfig(
            repos=[repo_config],
            leakage_cutoff=datetime(2025, 6, 1, tzinfo=UTC),
            out_path=out_path,
            cache_dir=Path(".cache"),
        )

        # Mock search to return PR #100 (already processed) and #101 (new)
        pr100 = _make_pr(
            number=100,
            title="Fix",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[42],
            base_sha="sha",
        )
        pr101 = _make_pr(
            number=101,
            title="Fix2",
            created_at=datetime(2025, 7, 12, tzinfo=UTC),
            merged_at=datetime(2025, 7, 15, tzinfo=UTC),
            closing_issues=[43],
            base_sha="sha",
        )
        page = PRPage(
            nodes=[pr100, pr101],
            page_info=PageInfo(has_next_page=False, end_cursor=None),
            total_count=2,
        )
        client.fetch_merged_prs_page.return_value = page

        # Mock process_pr to return a valid example for #101
        def mock_process(client, owner, repo, pr, cutoff):
            if pr.number == 101:
                return BenchmarkExample(
                    issue=IssueRef(owner="pallets", repo="flask", number=43),
                    base_commit_sha="abcdef1234567890abcdef1234567890abcdef12",
                    issue_title="t",
                    issue_body="b",
                    gold_files_all=["b.py"],
                    gold_files_source=["b.py"],
                    pr_number=101,
                    merged_at=datetime(2025, 7, 15, tzinfo=UTC),
                    issue_created_at=datetime(2025, 7, 10, tzinfo=UTC),
                    pr_opened_at=datetime(2025, 7, 12, tzinfo=UTC),
                    changed_files=[],
                    split_tag=SplitTag.POST_CUTOFF,
                )
            return None

        with patch("issuescout.bench.mine.process_pr", side_effect=mock_process):
            stats = mine_repo(client, repo_config, bench_config, out_path)

        assert stats["processed"] == 1  # PR #100 skipped as already processed
        assert stats["kept"] == 1  # only #101 kept
        assert stats["dropped"] == 0


class TestRunMining:
    """Tests for run_mining function."""

    def test_run_mining_calls_mine_repo(self):
        config = BenchConfig(
            repos=[
                RepoConfig(owner="pallets", name="flask"),
                RepoConfig(owner="psf", name="requests"),
            ],
            leakage_cutoff=datetime(2025, 6, 1, tzinfo=UTC),
            out_path=Path("data/bench.jsonl"),
            cache_dir=Path(".cache"),
        )

        with patch("issuescout.bench.mine.GitHubClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            with patch("issuescout.bench.mine.mine_repo") as mock_mine_repo:
                mock_mine_repo.return_value = {
                    "processed": 10,
                    "kept": 5,
                    "dropped": 5,
                    "errors": 0,
                }

                stats = run_mining(config)

                assert "pallets/flask" in stats
                assert "psf/requests" in stats
                assert mock_mine_repo.call_count == 2
