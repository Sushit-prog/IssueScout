"""Custom exceptions for GitHub client."""

from datetime import datetime
from typing import Any


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""

    def __init__(self, message: str, status: int, response: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.response = response


class RateLimitedError(GitHubAPIError):
    """Raised when rate limited (403/429)."""

    def __init__(
        self,
        message: str,
        reset_at: datetime,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, 429)
        self.reset_at = reset_at
        self.retry_after = retry_after


class SecondaryRateLimitError(GitHubAPIError):
    """Raised when secondary rate limit hit."""

    def __init__(self, message: str, reset_at: datetime) -> None:
        super().__init__(message, 403)
        self.reset_at = reset_at


class NotFoundError(GitHubAPIError):
    """Raised when resource not found (404)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 404)


class AuthenticationError(GitHubAPIError):
    """Raised when authentication fails (401)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 401)