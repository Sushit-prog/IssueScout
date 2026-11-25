"""Tests for benchmark filter functions."""

from datetime import UTC, datetime

from issuescout.bench.filters import (
    DropReason,
    _compute_changed_files_with_locatable,
    _compute_gold_files_all,
    _compute_gold_files_source,
    _is_doc_file,
    _is_generated,
    _is_lockfile,
    _is_test_file,
    apply_all_filters,
    filter_changed_file_count,
    filter_exactly_one_closing_issue,
    filter_issue_before_pr,
    filter_non_empty_issue_body,
    filter_not_docs_only,
    filter_not_generated_only,
    filter_not_lockfile_only,
)
from issuescout.github.models import ChangedFileData, FileStatus, IssueData, PRDetails


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


class TestPathHeuristics:
    """Tests for path classification helpers."""

    def test_is_test_file(self):
        assert _is_test_file("tests/test_auth.py")
        assert _is_test_file("testing/utils.py")
        assert _is_test_file("test_module.py")
        assert _is_test_file("module_test.py")
        assert _is_test_file("conftest.py")
        assert not _is_test_file("src/auth.py")
        assert not _is_test_file("src/test_utils.py")  # not test_ prefix

    def test_is_doc_file(self):
        assert _is_doc_file("docs/index.md")
        assert _is_doc_file("doc/guide.rst")
        assert _is_doc_file("README.md")
        assert _is_doc_file("CHANGES")
        assert _is_doc_file("HISTORY.rst")
        assert _is_doc_file("NEWS.txt")
        assert _is_doc_file("RELEASES.md")
        assert _is_doc_file("changelog/2024.md")
        assert not _is_doc_file("src/readme.py")

    def test_is_lockfile(self):
        assert _is_lockfile("requirements.txt")
        assert _is_lockfile("requirements-dev.txt")
        assert _is_lockfile("pyproject.toml")
        assert _is_lockfile("poetry.lock")
        assert _is_lockfile("Pipfile.lock")
        assert _is_lockfile("uv.lock")
        assert _is_lockfile("setup.cfg")
        assert _is_lockfile("setup.py")
        assert not _is_lockfile("src/config.py")

    def test_is_generated(self):
        assert _is_generated("proto/user_pb2.py")
        assert _is_generated("proto/user_pb2.pyi")
        assert _is_generated("generated/user.pb.go")
        assert _is_generated("dist/package.whl")
        assert _is_generated("build/lib/module.py")
        assert _is_generated("module.generated.py")
        assert _is_generated("proto/")
        assert not _is_generated("src/module.py")


class TestFilterFunctions:
    """Tests for individual filter functions."""

    def test_filter_exactly_one_closing_issue_keeps(self):
        pr = _make_pr(closing_issues=[42])
        assert filter_exactly_one_closing_issue(pr) is None

    def test_filter_exactly_one_closing_issue_drops_zero(self):
        pr = _make_pr(closing_issues=[])
        assert filter_exactly_one_closing_issue(pr) == DropReason.NOT_EXACTLY_ONE_CLOSING_ISSUE

    def test_filter_exactly_one_closing_issue_drops_multiple(self):
        pr = _make_pr(closing_issues=[42, 43])
        assert filter_exactly_one_closing_issue(pr) == DropReason.NOT_EXACTLY_ONE_CLOSING_ISSUE

    def test_filter_issue_before_pr_keeps(self):
        issue = _make_issue(
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            updated_at=datetime(2024, 1, 2, tzinfo=UTC),
        )
        pr = _make_pr(
            created_at=datetime(2024, 1, 5, tzinfo=UTC),
            merged_at=datetime(2024, 1, 10, tzinfo=UTC),
            closing_issues=[42],
        )
        assert filter_issue_before_pr(issue, pr) is None

    def test_filter_issue_before_pr_drops(self):
        issue = _make_issue(
            created_at=datetime(2024, 1, 10, tzinfo=UTC),
            updated_at=datetime(2024, 1, 11, tzinfo=UTC),
        )
        pr = _make_pr(
            created_at=datetime(2024, 1, 5, tzinfo=UTC),
            merged_at=datetime(2024, 1, 15, tzinfo=UTC),
            closing_issues=[42],
        )
        assert filter_issue_before_pr(issue, pr) == DropReason.ISSUE_AFTER_PR_OPENED

    def test_filter_changed_file_count_keeps(self):
        files = [
            ChangedFileData(filename="a.py", status=FileStatus.MODIFIED, additions=1, deletions=1),
            ChangedFileData(filename="b.py", status=FileStatus.MODIFIED, additions=1, deletions=1),
        ]
        assert filter_changed_file_count(files) is None

    def test_filter_changed_file_count_drops_zero(self):
        assert filter_changed_file_count([]) == DropReason.CHANGED_FILES_OUT_OF_RANGE

    def test_filter_changed_file_count_drops_too_many(self):
        files = [
            ChangedFileData(
                filename=f"f{i}.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            )
            for i in range(11)
        ]
        assert filter_changed_file_count(files) == DropReason.CHANGED_FILES_OUT_OF_RANGE

    def test_filter_non_empty_issue_body_keeps(self):
        issue = _make_issue(body="  has content  ")
        assert filter_non_empty_issue_body(issue) is None

    def test_filter_non_empty_issue_body_drops_empty(self):
        issue = _make_issue(body="")
        assert filter_non_empty_issue_body(issue) == DropReason.EMPTY_ISSUE_BODY

    def test_filter_non_empty_issue_body_drops_whitespace(self):
        issue = _make_issue(body="   \n\t  ")
        assert filter_non_empty_issue_body(issue) == DropReason.EMPTY_ISSUE_BODY

    def test_filter_not_docs_only_keeps_source(self):
        files = [
            ChangedFileData(
                filename="src/main.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        assert filter_not_docs_only(files) is None

    def test_filter_not_docs_only_drops_docs(self):
        files = [
            ChangedFileData(
                filename="docs/guide.md", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
            ChangedFileData(
                filename="README.md", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        assert filter_not_docs_only(files) == DropReason.DOCS_ONLY

    def test_filter_not_docs_only_ignores_added(self):
        # Added docs are not at base commit, so they don't count
        files = [
            ChangedFileData(
                filename="docs/new.md", status=FileStatus.ADDED, additions=10, deletions=0
            ),
        ]
        assert filter_not_docs_only(files) == DropReason.DOCS_ONLY

    def test_filter_not_lockfile_only_keeps_source(self):
        files = [
            ChangedFileData(
                filename="src/main.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        assert filter_not_lockfile_only(files) is None

    def test_filter_not_lockfile_only_drops_lockfile(self):
        files = [
            ChangedFileData(
                filename="requirements.txt", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
            ChangedFileData(
                filename="pyproject.toml", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        assert filter_not_lockfile_only(files) == DropReason.LOCKFILE_ONLY

    def test_filter_not_generated_only_keeps_source(self):
        files = [
            ChangedFileData(
                filename="src/main.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        assert filter_not_generated_only(files) is None

    def test_filter_not_generated_only_drops_generated(self):
        files = [
            ChangedFileData(
                filename="proto/user_pb2.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
            ChangedFileData(
                filename="generated/file.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        assert filter_not_generated_only(files) == DropReason.GENERATED_ONLY


class TestGoldComputation:
    """Tests for gold file computation."""

    def test_compute_gold_files_all_modified(self):
        files = [
            ChangedFileData(
                filename="src/a.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
            ChangedFileData(
                filename="src/b.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        gold = _compute_gold_files_all(files)
        assert gold == ["src/a.py", "src/b.py"]

    def test_compute_gold_files_all_renamed(self):
        files = [
            ChangedFileData(
                filename="src/new.py",
                status=FileStatus.RENAMED,
                previous_filename="src/old.py",
                additions=1,
                deletions=1,
            ),
        ]
        gold = _compute_gold_files_all(files)
        assert gold == ["src/old.py"]

    def test_compute_gold_files_all_removed(self):
        files = [
            ChangedFileData(
                filename="src/deleted.py", status=FileStatus.REMOVED, additions=0, deletions=10
            ),
        ]
        gold = _compute_gold_files_all(files)
        assert gold == ["src/deleted.py"]

    def test_compute_gold_files_all_added_excluded(self):
        files = [
            ChangedFileData(
                filename="src/new.py", status=FileStatus.ADDED, additions=10, deletions=0
            ),
        ]
        gold = _compute_gold_files_all(files)
        assert gold == []

    def test_compute_gold_files_source_excludes_tests_and_docs(self):
        files = [
            ChangedFileData(
                filename="src/main.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
            ChangedFileData(
                filename="tests/test_main.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
            ChangedFileData(
                filename="docs/guide.md", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        gold_source = _compute_gold_files_source(files)
        assert gold_source == ["src/main.py"]

    def test_compute_changed_files_with_locatable(self):
        files = [
            ChangedFileData(
                filename="src/a.py", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
            ChangedFileData(
                filename="src/new.py",
                status=FileStatus.RENAMED,
                previous_filename="src/old.py",
                additions=1,
                deletions=1,
            ),
            ChangedFileData(
                filename="src/deleted.py", status=FileStatus.REMOVED, additions=0, deletions=10
            ),
            ChangedFileData(
                filename="src/added.py", status=FileStatus.ADDED, additions=10, deletions=0
            ),
        ]
        result = _compute_changed_files_with_locatable(files)
        # Renamed files produce TWO entries: old_path (True) and new_path (False)
        assert result == [
            ("src/a.py", True),
            ("src/old.py", True),
            ("src/new.py", False),
            ("src/deleted.py", True),
            ("src/added.py", False),
        ]


class TestApplyAllFilters:
    """Tests for the combined filter pipeline."""

    def test_apply_all_filters_keeps_valid(self):
        issue = _make_issue(
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            updated_at=datetime(2024, 1, 2, tzinfo=UTC),
        )
        pr = _make_pr(
            created_at=datetime(2024, 1, 5, tzinfo=UTC),
            merged_at=datetime(2024, 1, 10, tzinfo=UTC),
            closing_issues=[42],
        )
        files = [
            ChangedFileData(
                filename="src/main.py", status=FileStatus.MODIFIED, additions=10, deletions=5
            ),
        ]
        reasons = apply_all_filters(issue, pr, files, "owner", "repo")
        assert reasons == []

    def test_apply_all_filters_drops_multiple_reasons(self):
        issue = _make_issue(
            body="",
            created_at=datetime(2024, 1, 10, tzinfo=UTC),
            updated_at=datetime(2024, 1, 11, tzinfo=UTC),
        )
        pr = _make_pr(
            created_at=datetime(2024, 1, 5, tzinfo=UTC),
            merged_at=datetime(2024, 1, 15, tzinfo=UTC),
            closing_issues=[42, 43],
        )
        files = [
            ChangedFileData(
                filename="docs/guide.md", status=FileStatus.MODIFIED, additions=1, deletions=1
            ),
        ]
        reasons = apply_all_filters(issue, pr, files, "owner", "repo")
        assert DropReason.NOT_EXACTLY_ONE_CLOSING_ISSUE in reasons
        assert DropReason.ISSUE_AFTER_PR_OPENED in reasons
        assert DropReason.EMPTY_ISSUE_BODY in reasons
        assert DropReason.DOCS_ONLY in reasons
        assert DropReason.GOLD_FILES_SOURCE_EMPTY in reasons
        assert DropReason.NO_LOCATABLE_SOURCE_FILE in reasons
