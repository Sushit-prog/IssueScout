"""GitHub HTTP client - ONLY place GitHub HTTP calls happen."""

from issuescout.github.client import GitHubClient
from issuescout.github.cache import ResponseCache
from issuescout.github.errors import (
    AuthenticationError,
    GitHubAPIError,
    NotFoundError,
    RateLimitedError,
    SecondaryRateLimitError,
)
from issuescout.github.models import (
    ChangedFileData,
    IssueData,
    PRDetails,
    PRPage,
    PageInfo,
    RateLimitInfo,
    FileStatus,
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
]