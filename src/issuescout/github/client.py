"""GitHub API client with rate-limit handling, retry, and caching."""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from issuescout.github.cache import ResponseCache
from issuescout.github.errors import (
    AuthenticationError,
    GitHubAPIError,
    NotFoundError,
    RateLimitedError,
    SecondaryRateLimitError,
)
from issuescout.github.graphql import (
    GET_ISSUE,
    RATE_LIMIT_QUERY,
    SEARCH_MERGED_PRS,
)
from issuescout.github.models import (
    ChangedFileData,
    IssueData,
    PageInfo,
    PRDetails,
    PRPage,
    RateLimitInfo,
)

logger = logging.getLogger(__name__)

# Sentinel token for leak detection
_TOKEN_SENTINEL = "ghp_SENTINEL_TOKEN_FOR_TESTING"


class GitHubClient:
    """Synchronous GitHub API client with caching and rate-limit handling."""

    GRAPHQL_URL = "https://api.github.com/graphql"
    REST_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        *,
        cache: ResponseCache | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        self._token = token
        self._cache = cache or ResponseCache()
        self._clock = clock
        self._sleep = sleep
        self._max_retries = max_retries
        self._base_delay = base_delay

        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "issuescout-bench/0.1.0",
            },
        )

    def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute GraphQL query with cache and rate-limit handling."""
        params: dict[str, Any] = {"query": query}
        if variables:
            params["variables"] = variables

        return self._request_with_retry("POST", self.GRAPHQL_URL, json=params)

    def _rest_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute REST GET with cache and rate-limit handling."""
        url = f"{self.REST_URL}{path}"
        return self._request_with_retry("GET", url, params=params)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute request with retry, rate-limit handling, and caching."""
        # Check cache first
        cached = self._cache.get(method, url, json or params)
        if cached is not None:
            logger.debug("Cache hit: %s %s", method, url)
            return cached

        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                if method == "POST":
                    response = self._client.post(url, json=json)
                else:
                    response = self._client.get(url, params=params)

                # Handle rate limits
                self._handle_rate_limit(response)

                # Parse response
                try:
                    body: dict[str, Any] = response.json()
                except Exception:
                    body = {"raw": response.text}

                # Cache successful responses
                if response.status_code == 200:
                    self._cache.set(
                        method,
                        url,
                        json or params,
                        response.status_code,
                        dict(response.headers),
                        body,
                    )

                # Handle errors - 5xx will be retried
                if response.status_code == 401:
                    raise AuthenticationError("Invalid or missing GitHub token")
                elif response.status_code == 404:
                    raise NotFoundError(f"Resource not found: {url}")
                elif response.status_code >= 500:
                    raise Exception(f"Server error: {response.status_code}")  # Will be retried

                return body

            except (RateLimitedError, SecondaryRateLimitError) as e:
                last_exc = e
                if attempt < self._max_retries:
                    self._sleep_until(e.reset_at)
                    continue
                raise
            except (AuthenticationError, NotFoundError):
                raise
            except Exception as e:
                last_exc = e
                if attempt < self._max_retries:
                    delay = self._base_delay * (2**attempt)
                    logger.warning(
                        "Request failed (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt + 1,
                        self._max_retries + 1,
                        e,
                        delay,
                    )
                    self._sleep(delay)
                    continue
                raise GitHubAPIError(
                    f"Request failed after {self._max_retries + 1} attempts: {last_exc}",
                    status=500,
                ) from last_exc

        raise GitHubAPIError(f"Request failed: {last_exc}", status=500) from last_exc

    def _handle_rate_limit(self, response: httpx.Response) -> None:
        """Check and handle rate limit headers."""
        # Primary rate limit
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_str = response.headers.get("X-RateLimit-Reset")

        if remaining is not None and int(remaining) == 0 and reset_str:
            reset_at = datetime.fromtimestamp(int(reset_str), tz=UTC)
            raise RateLimitedError(
                "Primary rate limit exhausted",
                reset_at=reset_at,
            )

        # Secondary rate limit (403 with specific message)
        if response.status_code == 403:
            try:
                body = response.json()
                message = body.get("message", "").lower()
                if "secondary rate limit" in message or "rate limit" in message:
                    reset_at = (
                        datetime.fromtimestamp(int(reset_str), tz=UTC)
                        if reset_str
                        else datetime.now(UTC)
                    )
                    raise SecondaryRateLimitError(
                        f"Secondary rate limit: {body.get('message', 'Unknown')}",
                        reset_at=reset_at,
                    )
            except json.JSONDecodeError:
                pass

        # Retry-After header
        retry_after = response.headers.get("Retry-After")
        if retry_after and response.status_code in (403, 429):
            try:
                seconds = int(retry_after)
                reset_at = datetime.fromtimestamp(self._clock() + seconds, tz=UTC)
                raise RateLimitedError(
                    f"Rate limited, retry after {seconds}s",
                    reset_at=reset_at,
                    retry_after=seconds,
                )
            except ValueError:
                pass

    def _sleep_until(self, reset_at: datetime) -> None:
        """Sleep until reset time with buffer."""
        now = self._clock()
        reset_ts = reset_at.timestamp()
        wait = max(0, reset_ts - now) + 1  # 1 second buffer
        logger.info("Rate limited. Sleeping %.1f seconds until %s", wait, reset_at.isoformat())
        self._sleep(wait)

    # --- Public API methods ---

    def fetch_merged_prs_page(
        self,
        owner: str,
        repo: str,
        cursor: str | None = None,
        per_page: int = 100,
        since: str | None = None,
        until: str | None = None,
    ) -> PRPage:
        """Fetch a page of merged PRs with closing issues."""
        # Build search query
        query_parts = [f"repo:{owner}/{repo}", "is:pr", "is:merged"]
        if since:
            query_parts.append(f"merged:>={since}")
        if until:
            query_parts.append(f"merged:<={until}")
        query = " ".join(query_parts)

        variables = {"query": query, "first": per_page}
        if cursor:
            variables["after"] = cursor

        result = self._graphql(SEARCH_MERGED_PRS, variables)
        search_data = result.get("data", {}).get("search", {})

        # Parse nodes
        nodes = []
        for node in search_data.get("nodes", []):
            if not isinstance(node, dict):
                continue
            closing_issues = [
                n["number"]
                for n in node.get("closingIssuesReferences", {}).get("nodes", [])
                if isinstance(n, dict)
            ]
            pr = PRDetails(
                number=node["number"],
                title=node.get("title", ""),
                body=node.get("body"),
                state=node.get("state", ""),
                merged=node.get("merged", False),
                mergeable=node.get("mergeable"),
                created_at=datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(node["updatedAt"].replace("Z", "+00:00")),
                closed_at=datetime.fromisoformat(node["closedAt"].replace("Z", "+00:00"))
                if node.get("closedAt")
                else None,
                merged_at=datetime.fromisoformat(node["mergedAt"].replace("Z", "+00:00"))
                if node.get("mergedAt")
                else None,
                base_sha=node.get("baseRefOid", ""),
                head_sha=node.get("headRefOid", ""),
                base_ref=node.get("baseRefName", ""),
                head_ref=node.get("headRefName", ""),
                html_url=node.get("url", ""),
                closing_issues=closing_issues,
            )
            nodes.append(pr)

        page_info = PageInfo(
            has_next_page=search_data.get("pageInfo", {}).get("hasNextPage", False),
            end_cursor=search_data.get("pageInfo", {}).get("endCursor"),
        )

        return PRPage(
            nodes=nodes,
            page_info=page_info,
            total_count=search_data.get("issueCount", 0),
        )

    def fetch_issue(self, owner: str, repo: str, number: int) -> IssueData:
        """Fetch issue details."""
        result = self._graphql(GET_ISSUE, {"owner": owner, "repo": repo, "number": number})
        issue_data = result.get("data", {}).get("repository", {}).get("issue")
        if not issue_data:
            raise NotFoundError(f"Issue #{number} not found in {owner}/{repo}")

        return IssueData(
            number=issue_data["number"],
            title=issue_data.get("title", ""),
            body=issue_data.get("body"),
            created_at=datetime.fromisoformat(issue_data["createdAt"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(issue_data["updatedAt"].replace("Z", "+00:00")),
            closed_at=datetime.fromisoformat(issue_data["closedAt"].replace("Z", "+00:00"))
            if issue_data.get("closedAt")
            else None,
            state=issue_data.get("state", ""),
            html_url=issue_data.get("url", ""),
        )

    def fetch_pr_files(self, owner: str, repo: str, number: int) -> list[ChangedFileData]:
        """Fetch changed files for a PR using REST API (includes previous_filename for renames)."""
        # Use REST API with per_page=11 to detect >10 files
        path = f"/repos/{owner}/{repo}/pulls/{number}/files"
        params = {"per_page": 11}

        result = self._rest_get(path, params)

        files: list[ChangedFileData] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            files.append(
                ChangedFileData(
                    filename=item.get("filename", ""),
                    status=item.get("status", "modified"),
                    previous_filename=item.get("previous_filename"),
                    additions=item.get("additions", 0),
                    deletions=item.get("deletions", 0),
                    changes=item.get("changes", 0),
                    sha=item.get("sha"),
                    patch=item.get("patch"),
                )
            )

        return files

    def fetch_pr_details(self, owner: str, repo: str, number: int) -> PRDetails:
        """Fetch PR details including base SHA using REST API."""
        path = f"/repos/{owner}/{repo}/pulls/{number}"
        result = self._rest_get(path)

        closing_issues = []
        # Extract closing issues from body text (GraphQL search already gives
        # us this, but REST is fallback)
        if result.get("body"):
            import re

            for match in re.finditer(
                r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:#(\d+)|(\w+/\w+#\d+))",
                result["body"],
                re.IGNORECASE,
            ):
                if match.group(1):
                    closing_issues.append(int(match.group(1)))

        return PRDetails(
            number=result["number"],
            title=result.get("title", ""),
            body=result.get("body"),
            state=result.get("state", ""),
            merged=result.get("merged", False),
            mergeable=result.get("mergeable"),
            created_at=datetime.fromisoformat(result["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(result["updated_at"].replace("Z", "+00:00")),
            closed_at=datetime.fromisoformat(result["closed_at"].replace("Z", "+00:00"))
            if result.get("closed_at")
            else None,
            merged_at=datetime.fromisoformat(result["merged_at"].replace("Z", "+00:00"))
            if result.get("merged_at")
            else None,
            base_sha=result.get("base", {}).get("sha", ""),
            head_sha=result.get("head", {}).get("sha", ""),
            base_ref=result.get("base", {}).get("ref", ""),
            head_ref=result.get("head", {}).get("ref", ""),
            html_url=result.get("html_url", ""),
            closing_issues=closing_issues,
        )

    def get_rate_limit(self) -> RateLimitInfo:
        """Get current rate limit status."""
        result = self._graphql(RATE_LIMIT_QUERY)
        rl = result.get("data", {}).get("rateLimit", {})
        return RateLimitInfo(
            limit=rl.get("limit", 5000),
            remaining=rl.get("remaining", 5000),
            reset_at=datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00")),
            used=rl.get("used", 0),
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        self.close()
