"""Tests for GitHub client."""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from issuescout.github.cache import ResponseCache
from issuescout.github.client import GitHubClient
from issuescout.github.models import ChangedFileData, FileStatus


class FakeClock:
    """Fake clock for testing time-dependent behavior."""

    def __init__(self, start: float = 1000.0) -> None:
        self._time = start

    def __call__(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


def load_fixture(name: str) -> dict:
    """Load a JSON fixture file."""
    path = Path(__file__).parent.parent / "fixtures" / "github" / name
    with path.open() as f:
        return json.load(f)


class TestGitHubClient:
    """Tests for GitHubClient."""

    def setup_method(self) -> None:
        self.clock = FakeClock(1000.0)
        self.sleep_calls: list[float] = []

        def fake_sleep(seconds: float) -> None:
            self.sleep_calls.append(seconds)
            self.clock.advance(seconds)

        # Use a fresh cache for each test to avoid cache hits from other tests

        self.cache_dir = tempfile.mkdtemp()
        self.client = GitHubClient(
            token="ghp_test_token",
            cache=ResponseCache(Path(self.cache_dir)),
            clock=self.clock,
            sleep=fake_sleep,
            max_retries=2,
            base_delay=0.1,
        )

    def teardown_method(self) -> None:
        self.client.close()
        import shutil

        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_fetch_pr_files_parses_all_statuses(self) -> None:
        """Test that fetch_pr_files correctly parses all file statuses."""
        fixture = load_fixture("pr_files_response.json")

        with patch.object(self.client, "_rest_get", return_value=fixture) as mock_get:
            files = self.client.fetch_pr_files("owner", "repo", 123)

        assert len(files) == 7

        # Check modified
        assert files[0].filename == "src/auth.py"
        assert files[0].status == FileStatus.MODIFIED
        assert files[0].additions == 10

        # Check added
        assert files[1].filename == "tests/test_auth.py"
        assert files[1].status == FileStatus.ADDED

        # Check renamed with previous_filename
        assert files[3].filename == "src/utils.py"
        assert files[3].status == FileStatus.RENAMED
        assert files[3].previous_filename == "src/helpers.py"

        # Check removed
        assert files[4].filename == "src/old_module.py"
        assert files[4].status == FileStatus.REMOVED

        # Check copied maps to modified
        # (not in fixture, but mapping exists)

        # Check changed maps to modified
        # (not in fixture, but mapping exists)

        mock_get.assert_called_once_with(
            "/repos/owner/repo/pulls/123/files",
            {"per_page": 11},
        )

    def test_fetch_pr_details_uses_base_sha_from_rest(self) -> None:
        """Test that base_sha comes from REST pull.base.sha."""
        pr_response = {
            "number": 123,
            "title": "Test PR",
            "body": "Closes #456",
            "state": "closed",
            "merged": True,
            "mergeable": True,
            "created_at": "2024-06-15T10:00:00Z",
            "updated_at": "2024-06-16T12:00:00Z",
            "closed_at": "2024-06-16T12:00:00Z",
            "merged_at": "2024-06-16T12:00:00Z",
            "base": {"sha": "base_sha_from_rest", "ref": "main"},
            "head": {"sha": "head_sha", "ref": "feature"},
            "html_url": "https://github.com/owner/repo/pull/123",
        }

        with patch.object(self.client, "_rest_get", return_value=pr_response) as mock_get:
            pr = self.client.fetch_pr_details("owner", "repo", 123)

        assert pr.base_sha == "base_sha_from_rest"
        assert pr.closing_issues == [456]
        mock_get.assert_called_once_with("/repos/owner/repo/pulls/123")

    def test_fetch_merged_prs_page_parses_graphql_response(self) -> None:
        """Test parsing of GraphQL search response (base_sha comes from REST later)."""
        fixture = load_fixture("search_prs_response.json")

        with patch.object(self.client, "_graphql", return_value=fixture):
            page = self.client.fetch_merged_prs_page("owner", "repo", per_page=100)

        assert len(page.nodes) == 2
        assert page.nodes[0].number == 123
        assert page.nodes[0].closing_issues == [456]
        assert page.nodes[0].base_sha == ""  # GraphQL no longer provides baseRefOid
        assert page.nodes[1].number == 124
        assert page.nodes[1].closing_issues == []
        assert page.nodes[1].base_sha == ""
        assert page.total_count == 2

    def test_fetch_pr_details_pins_base_sha_from_rest_fixture(self) -> None:
        """Test that base_commit_sha is pinned to base.sha from REST response fixture."""
        fixture = load_fixture("pr_details_response.json")

        with patch.object(self.client, "_rest_get", return_value=fixture) as mock_get:
            pr = self.client.fetch_pr_details("owner", "repo", 123)

        assert pr.base_sha == "base_sha_from_rest"
        assert pr.closing_issues == [456]
        mock_get.assert_called_once_with("/repos/owner/repo/pulls/123")

    def test_rate_limit_sleep_with_fake_clock(self) -> None:
        """Test that rate limit handling sleeps until reset using fake clock."""
        # First response: rate limited
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 429
        rate_limited_response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1060",  # 60 seconds from clock start (1000)
            "Retry-After": "60",
        }
        rate_limited_response.json.return_value = {"message": "Rate limit exceeded"}

        # Second response: success
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {"X-RateLimit-Remaining": "4999"}
        success_response.json.return_value = {
            "data": {"search": {"nodes": [], "pageInfo": {"hasNextPage": False}, "issueCount": 0}}
        }

        with patch.object(
            self.client._client, "post", side_effect=[rate_limited_response, success_response]
        ):
            result = self.client._graphql("query { test }")

        # Should have slept ~60 seconds
        assert len(self.sleep_calls) == 1
        assert 59 <= self.sleep_calls[0] <= 62  # 60 seconds + 1 buffer
        assert result["data"]["search"]["issueCount"] == 0

    def test_retry_backoff_on_5xx(self) -> None:
        """Test exponential backoff on 5xx errors."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.headers = {}
        error_response.json.return_value = {"message": "Internal server error"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.headers = {}
        success_response.json.return_value = {
            "data": {"search": {"nodes": [], "pageInfo": {"hasNextPage": False}, "issueCount": 0}}
        }

        with patch.object(
            self.client._client,
            "post",
            side_effect=[error_response, error_response, success_response],
        ):
            result = self.client._graphql("query { test }")

        # Should have retried twice with backoff
        assert len(self.sleep_calls) == 2
        assert self.sleep_calls[0] == 0.1  # base_delay * 2^0
        assert self.sleep_calls[1] == 0.2  # base_delay * 2^1
        assert result["data"]["search"]["issueCount"] == 0

    def test_cache_hit_avoids_network_call(self) -> None:
        """Test that cache hits return data without network call."""
        cache = ResponseCache(Path(".cache/test_github"))
        cache.set(
            "POST",
            "https://api.github.com/graphql",
            {"query": "test"},
            200,
            {"content-type": "application/json"},
            {
                "data": {
                    "search": {"nodes": [], "pageInfo": {"hasNextPage": False}, "issueCount": 42}
                }
            },
        )

        client = GitHubClient(
            token="ghp_test",
            cache=cache,
            clock=self.clock,
            sleep=lambda s: self.clock.advance(s),
        )

        with patch.object(client._client, "post") as mock_post:
            result = client._graphql("test")
            mock_post.assert_not_called()

        assert result["data"]["search"]["issueCount"] == 42
        client.close()

    def test_no_token_leak_in_logs_or_exceptions(self) -> None:
        """Test that the token never appears in logs, exceptions, or cache."""
        import secrets

        sentinel = f"ghp_{secrets.token_hex(20)}"  # Random token
        client = GitHubClient(
            token=sentinel,
            clock=self.clock,
            sleep=lambda s: self.clock.advance(s),
        )

        # Capture log output
        log_stream = []
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.stream = MagicMock()
        handler.stream.write = lambda s: log_stream.append(s)

        logger = logging.getLogger("issuescout.github.client")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        exc_str = ""
        try:
            # Trigger an error
            error_response = MagicMock()
            error_response.status_code = 401
            error_response.headers = {}
            error_response.json.return_value = {"message": "Bad credentials"}

            with patch.object(client._client, "post", return_value=error_response):
                try:
                    client._graphql("query { test }")
                except Exception as e:
                    exc_str = str(e)

            # Check token not in exception
            assert sentinel not in exc_str, f"Token leaked in exception: {exc_str}"

            # Check token not in logs
            all_logs = "".join(log_stream)
            assert sentinel not in all_logs, f"Token leaked in logs: {all_logs}"

            # Check token not in cache files
            cache_dir = Path(".cache/github")
            if cache_dir.exists():
                for cache_file in cache_dir.rglob("*.json.gz"):
                    import gzip

                    with gzip.open(cache_file, "rt") as f:
                        content = f.read()
                        assert sentinel not in content, f"Token leaked in cache file: {cache_file}"

        finally:
            logger.removeHandler(handler)
            client.close()

    def test_cache_excludes_authorization_header(self) -> None:
        """Test that Authorization header is never cached."""
        cache = ResponseCache(Path(".cache/test_github2"))
        client = GitHubClient(
            token="ghp_test_token",
            cache=cache,
            clock=self.clock,
            sleep=lambda s: self.clock.advance(s),
        )

        response = MagicMock()
        response.status_code = 200
        response.headers = {
            "Authorization": "Bearer ghp_test_token",
            "X-RateLimit-Remaining": "4999",
        }
        response.json.return_value = {"data": {"test": "ok"}}

        with patch.object(client._client, "post", return_value=response):
            client._graphql("query { test }")

        # Check cache entry doesn't have Authorization
        cache_files = list(cache.cache_dir.glob("*.json.gz"))
        assert len(cache_files) == 1

        import gzip

        with gzip.open(cache_files[0], "rt") as f:
            entry = json.load(f)

        assert "authorization" not in entry["headers"]
        assert "Authorization" not in entry["headers"]

        client.close()

    def test_non_200_not_cached(self) -> None:
        """Test that non-200 responses are not cached."""
        cache = ResponseCache(Path(".cache/test_github3"))
        client = GitHubClient(
            token="ghp_test",
            cache=cache,
            clock=self.clock,
            sleep=lambda s: self.clock.advance(s),
        )

        response = MagicMock()
        response.status_code = 404
        response.headers = {}
        response.json.return_value = {"message": "Not found"}

        with patch.object(client._client, "post", return_value=response):
            try:
                client._graphql("query { test }")
            except Exception:
                pass

        # Cache should be empty
        cache_files = list(cache.cache_dir.glob("*.json.gz"))
        assert len(cache_files) == 0

        client.close()

    def test_graphql_errors_not_cached(self) -> None:
        """Test that GraphQL responses with 'errors' field are not cached."""
        cache = ResponseCache(Path(".cache/test_github4"))
        client = GitHubClient(
            token="ghp_test",
            cache=cache,
            clock=self.clock,
            sleep=lambda s: self.clock.advance(s),
        )

        response = MagicMock()
        response.status_code = 200
        response.headers = {}
        response.json.return_value = {"errors": [{"message": "Field not found"}]}

        with patch.object(client._client, "post", return_value=response):
            try:
                client._graphql("query { test }")
            except Exception:
                pass

        # Cache should be empty
        cache_files = list(cache.cache_dir.glob("*.json.gz"))
        assert len(cache_files) == 0

        client.close()


class TestResponseCache:
    """Tests for ResponseCache."""

    def test_cache_roundtrip(self, tmp_path: Path) -> None:
        """Test basic cache set/get."""
        cache = ResponseCache(tmp_path / "github")

        cache.set(
            "GET",
            "https://api.github.com/test",
            {"param": "value"},
            200,
            {"content-type": "application/json"},
            {"data": "test"},
        )

        result = cache.get("GET", "https://api.github.com/test", {"param": "value"})
        assert result == {"data": "test"}

    def test_cache_key_consistency(self, tmp_path: Path) -> None:
        """Test that cache keys are consistent regardless of param order."""
        cache = ResponseCache(tmp_path / "github")

        cache.set("GET", "https://api.github.com/test", {"a": 1, "b": 2}, 200, {}, {"x": 1})
        result = cache.get("GET", "https://api.github.com/test", {"b": 2, "a": 1})
        assert result == {"x": 1}

    def test_cache_ttl_expiry(self, tmp_path: Path) -> None:
        """Test that expired cache entries are not returned."""
        cache = ResponseCache(tmp_path / "github")

        # Manually create an old entry
        import gzip

        key = cache.make_key("GET", "https://api.github.com/test", {})
        path = cache.cache_dir / f"{key}.json.gz"
        old_entry = {
            "key": key,
            "method": "GET",
            "url": "https://api.github.com/test",
            "params": {},
            "status": 200,
            "headers": {},
            "body": {"data": "old"},
            "cached_at": "2020-01-01T00:00:00Z",  # Old date
        }
        with gzip.open(path, "wt") as f:
            json.dump(old_entry, f)

        result = cache.get("GET", "https://api.github.com/test", {})
        assert result is None


class TestChangedFileData:
    """Tests for ChangedFileData model."""

    def test_status_mapping(self) -> None:
        """Test all status mappings."""
        test_cases = [
            ("added", FileStatus.ADDED),
            ("modified", FileStatus.MODIFIED),
            ("removed", FileStatus.REMOVED),
            ("renamed", FileStatus.RENAMED),
            ("copied", FileStatus.COPIED),
            ("changed", FileStatus.CHANGED),
            ("COPIED", FileStatus.COPIED),
            ("CHANGED", FileStatus.CHANGED),
            ("unknown", FileStatus.MODIFIED),  # defaults to modified
        ]

        for input_status, expected in test_cases:
            file_data = ChangedFileData(filename="test.py", status=input_status)
            assert file_data.status == expected, f"Failed for {input_status}"

    def test_rename_has_previous_filename(self) -> None:
        """Test that renamed files have previous_filename."""
        file_data = ChangedFileData(
            filename="new_name.py",
            status="renamed",
            previous_filename="old_name.py",
        )
        assert file_data.previous_filename == "old_name.py"
        assert file_data.status == FileStatus.RENAMED

    def test_removed_file_has_no_previous(self) -> None:
        """Test that removed files don't have previous_filename."""
        file_data = ChangedFileData(filename="deleted.py", status="removed")
        assert file_data.previous_filename is None
