"""Pure filter functions for benchmark mining with typed drop reasons."""

import re
from enum import StrEnum

from issuescout.github.models import ChangedFileData, FileStatus, IssueData, PRDetails


class DropReason(StrEnum):
    """Reasons for dropping a PR/issue pair."""

    NOT_EXACTLY_ONE_CLOSING_ISSUE = "not_exactly_one_closing_issue"
    CLOSING_ISSUE_DIFFERENT_REPO = "closing_issue_different_repo"
    ISSUE_AFTER_PR_OPENED = "issue_after_pr_opened"
    CHANGED_FILES_OUT_OF_RANGE = "changed_files_out_of_range"
    DOCS_ONLY = "docs_only"
    LOCKFILE_ONLY = "lockfile_only"
    GENERATED_ONLY = "generated_only"
    EMPTY_ISSUE_BODY = "empty_issue_body"
    GOLD_FILES_SOURCE_EMPTY = "gold_files_source_empty"
    NO_LOCATABLE_SOURCE_FILE = "no_locatable_source_file"
    BASE_SHA_MISSING = "base_sha_missing"


def filter_exactly_one_closing_issue(pr: PRDetails) -> DropReason | None:
    """Keep only PRs that close exactly one issue."""
    if len(pr.closing_issues) != 1:
        return DropReason.NOT_EXACTLY_ONE_CLOSING_ISSUE
    return None


def filter_closing_issue_same_repo(pr: PRDetails, owner: str, repo: str) -> DropReason | None:
    """Keep only PRs where the closing issue is in the same repo (no cross-repo references)."""
    # PRDetails.closing_issues only contains issue numbers, not full refs.
    # Cross-repo references would be like "owner/repo#123" which we don't
    # capture in the simple number list.
    # This filter is a placeholder for future enhancement if we parse full refs.
    return None


def filter_issue_before_pr(issue: IssueData, pr: PRDetails) -> DropReason | None:
    """Keep only issues created before the PR was opened."""
    if issue.created_at > pr.created_at:
        return DropReason.ISSUE_AFTER_PR_OPENED
    return None


def filter_changed_file_count(files: list[ChangedFileData]) -> DropReason | None:
    """Keep only PRs with 1-10 changed files."""
    if len(files) < 1 or len(files) > 10:
        return DropReason.CHANGED_FILES_OUT_OF_RANGE
    return None


# Path patterns for filtering
DOC_PATTERNS = [
    r"^docs?/",
    r"^doc/",
    r"\.md$",
    r"\.rst$",
    r"\.txt$",
    r"^CHANGES",
    r"^HISTORY",
    r"^NEWS",
    r"^RELEASES",
    r"^changelog/",
    r"^changes/",
]

LOCKFILE_PATTERNS = [
    r"requirements.*\.txt$",
    r"^pyproject\.toml$",
    r"^poetry\.lock$",
    r"^Pipfile\.lock$",
    r"^uv\.lock$",
    r"^setup\.cfg$",
    r"^setup\.py$",
]

GENERATED_PATTERNS = [
    r"_pb2\.py$",
    r"_pb2\.pyi$",
    r"\.pb\.go$",
    r"^generated/",
    r"^dist/",
    r"^build/",
    r"^.*\.generated\.",
    r"^proto/",
]

TEST_FILE_PATTERNS = [
    r"^tests?/",
    r"^testing/",
    r"^test_.*\.py$",
    r".*_test\.py$",
    r"^conftest\.py$",
]

DOC_FILE_PATTERNS = [
    r"^docs?/",
    r"\.md$",
    r"\.rst$",
    r"\.txt$",
    r"^CHANGES",
    r"^HISTORY",
    r"^NEWS",
    r"^RELEASES",
    r"^changelog/",
    r"^changes/",
]


def _matches_any(path: str, patterns: list[str]) -> bool:
    """Check if path matches any regex pattern."""
    for pattern in patterns:
        if re.search(pattern, path, re.IGNORECASE):
            return True
    return False


def _is_test_file(path: str) -> bool:
    """Check if a file is a test file."""
    return _matches_any(path, TEST_FILE_PATTERNS)


def _is_doc_file(path: str) -> bool:
    """Check if a file is a documentation file."""
    return _matches_any(path, DOC_FILE_PATTERNS)


def _is_lockfile(path: str) -> bool:
    """Check if a file is a lockfile/dependency file."""
    return _matches_any(path, LOCKFILE_PATTERNS)


def _is_generated(path: str) -> bool:
    """Check if a file is generated."""
    return _matches_any(path, GENERATED_PATTERNS)


def filter_not_docs_only(files: list[ChangedFileData]) -> DropReason | None:
    """Drop if all changed files are documentation only."""
    if not files:
        return DropReason.DOCS_ONLY

    # Consider only modified/removed/renamed files at base commit
    # Added files are not locatable at base commit
    relevant_files = [f for f in files if f.status != FileStatus.ADDED]
    if not relevant_files:
        return DropReason.DOCS_ONLY

    if all(_is_doc_file(f.filename) for f in relevant_files):
        return DropReason.DOCS_ONLY
    return None


def filter_not_lockfile_only(files: list[ChangedFileData]) -> DropReason | None:
    """Drop if all changed files are lockfiles only."""
    if not files:
        return DropReason.LOCKFILE_ONLY

    relevant_files = [f for f in files if f.status != FileStatus.ADDED]
    if not relevant_files:
        return DropReason.LOCKFILE_ONLY

    if all(_is_lockfile(f.filename) for f in relevant_files):
        return DropReason.LOCKFILE_ONLY
    return None


def filter_not_generated_only(files: list[ChangedFileData]) -> DropReason | None:
    """Drop if all changed files are generated only."""
    if not files:
        return DropReason.GENERATED_ONLY

    relevant_files = [f for f in files if f.status != FileStatus.ADDED]
    if not relevant_files:
        return DropReason.GENERATED_ONLY

    if all(_is_generated(f.filename) for f in relevant_files):
        return DropReason.GENERATED_ONLY
    return None


def filter_non_empty_issue_body(issue: IssueData) -> DropReason | None:
    """Drop if issue body is empty or whitespace only."""
    if not issue.body or not issue.body.strip():
        return DropReason.EMPTY_ISSUE_BODY
    return None


def filter_gold_files_source_not_empty(changed_files: list[ChangedFileData]) -> DropReason | None:
    """Drop if gold_files_source would be empty (no locatable source files)."""
    gold_files_source = _compute_gold_files_source(changed_files)
    if not gold_files_source:
        return DropReason.GOLD_FILES_SOURCE_EMPTY
    return None


def filter_has_locatable_source_file(changed_files: list[ChangedFileData]) -> DropReason | None:
    """Drop if there are no locatable source files at the base commit."""
    has_locatable = any(
        f.status != FileStatus.ADDED
        and not _is_test_file(f.filename)
        and not _is_doc_file(f.filename)
        for f in changed_files
    )
    if not has_locatable:
        return DropReason.NO_LOCATABLE_SOURCE_FILE
    return None


def _compute_gold_files_all(changed_files: list[ChangedFileData]) -> list[str]:
    """Compute gold_files_all: all changed files at base commit."""
    gold = []
    for f in changed_files:
        if f.status == FileStatus.RENAMED and f.previous_filename:
            gold.append(f.previous_filename)
        elif f.status == FileStatus.REMOVED:
            gold.append(f.filename)
        elif f.status == FileStatus.ADDED:
            # Added files are not locatable at base commit
            continue
        else:  # modified, copied, changed
            gold.append(f.filename)
    return gold


def _compute_gold_files_source(changed_files: list[ChangedFileData]) -> list[str]:
    """Compute gold_files_source: excludes tests and docs."""
    gold_all = _compute_gold_files_all(changed_files)
    return [f for f in gold_all if not _is_test_file(f) and not _is_doc_file(f)]


def _compute_changed_files_with_locatable(
    changed_files: list[ChangedFileData],
) -> list[tuple[str, bool]]:
    """Compute changed files with locatable_at_base flag.

    For renamed files, returns TWO entries:
    - (old_path, True) - the old path exists at base commit
    - (new_path, False) - the new path does not exist at base commit
    """
    result = []
    for f in changed_files:
        if f.status == FileStatus.RENAMED and f.previous_filename:
            # Renamed files: old path exists at base, new path doesn't
            result.append((f.previous_filename, True))
            result.append((f.filename, False))
        elif f.status == FileStatus.REMOVED:
            result.append((f.filename, True))
        elif f.status == FileStatus.ADDED:
            result.append((f.filename, False))
        else:  # modified, copied, changed
            result.append((f.filename, True))
    return result


def apply_all_filters(
    issue: IssueData,
    pr: PRDetails,
    files: list[ChangedFileData],
    owner: str,
    repo: str,
) -> list[DropReason]:
    """Apply all filters and return list of drop reasons (empty if kept).

    File-based filters are only applied when files list is not empty,
    to allow early filtering before fetching files.
    """
    reasons = []

    # Issue-only filters
    if reason := filter_exactly_one_closing_issue(pr):
        reasons.append(reason)

    if reason := filter_closing_issue_same_repo(pr, owner, repo):
        reasons.append(reason)

    if reason := filter_issue_before_pr(issue, pr):
        reasons.append(reason)

    if reason := filter_non_empty_issue_body(issue):
        reasons.append(reason)

    # File-based filters (only if we have files)
    if files:
        if reason := filter_changed_file_count(files):
            reasons.append(reason)

        if reason := filter_not_docs_only(files):
            reasons.append(reason)

        if reason := filter_not_lockfile_only(files):
            reasons.append(reason)

        if reason := filter_not_generated_only(files):
            reasons.append(reason)

        if reason := filter_gold_files_source_not_empty(files):
            reasons.append(reason)

        if reason := filter_has_locatable_source_file(files):
            reasons.append(reason)

    return reasons


# Re-export for tests
__all__ = [
    "DropReason",
    "filter_exactly_one_closing_issue",
    "filter_closing_issue_same_repo",
    "filter_issue_before_pr",
    "filter_changed_file_count",
    "filter_not_docs_only",
    "filter_not_lockfile_only",
    "filter_not_generated_only",
    "filter_non_empty_issue_body",
    "filter_gold_files_source_not_empty",
    "filter_has_locatable_source_file",
    "apply_all_filters",
    "_is_test_file",
    "_is_doc_file",
    "_is_lockfile",
    "_is_generated",
    "_compute_gold_files_all",
    "_compute_gold_files_source",
    "_compute_changed_files_with_locatable",
]
