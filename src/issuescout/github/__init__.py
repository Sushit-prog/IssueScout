"""GitHub HTTP client - ONLY place GitHub HTTP calls happen."""

from issuescout.github.cache import ResponseCache
from issuescout.github.checkout import (
    CheckoutError,
    commit_exists,
    ensure_bare_repo,
    fetch_commit,
    get_bare_repo_path,
    get_repo_size,
)
from issuescout.github.client import GitHubClient
from issuescout.github.errors import (
    AuthenticationError,
    GitHubAPIError,
    NotFoundError,
    RateLimitedError,
    SecondaryRateLimitError,
)
from issuescout.github.models import (
    ChangedFileData,
    FileStatus,
    IssueData,
    PageInfo,
    PRDetails,
    PRPage,
    RateLimitInfo,
)

__all__ = [
    "GitHubClient",
    "ResponseCache",
    "AuthenticationError",
    "GitHubAPIError",
    "NotFoundError",
    "RateLimitedError",
    "SecondaryRateLimitError",
    "ChangedFileData",
    "IssueData",
    "PRDetails",
    "PRPage",
    "PageInfo",
    "RateLimitInfo",
    "FileStatus",
    "ensure_bare_repo",
    "fetch_commit",
    "commit_exists",
    "get_bare_repo_path",
    "get_repo_size",
    "CheckoutError",
]
