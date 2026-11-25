"""On-disk response cache for GitHub API."""

import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any


class ResponseCache:
    """File-based response cache with gzip compression."""

    def __init__(self, cache_dir: Path = Path(".cache/github")) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(self, method: str, url: str, params: dict[str, Any] | None) -> str:
        """Generate cache key from request."""
        if params is None:
            params = {}
        # Sort params for consistent keys
        param_str = json.dumps(params, sort_keys=True, separators=(",", ":"))
        raw = f"{method.upper()}|{url}|{param_str}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json.gz"

    def get(self, method: str, url: str, params: dict[str, Any] | None) -> dict[str, Any] | None:
        """Get cached response if exists and not expired (30 days TTL)."""
        key = self._make_key(method, url, params)
        path = self._cache_path(key)

        if not path.exists():
            return None

        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                entry = json.load(f)

            # Check TTL (30 days)
            cached_at = entry.get("cached_at")
            if cached_at:
                from datetime import datetime, UTC
                cached_time = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                if time.time() - cached_time.timestamp() > 30 * 86400:
                    return None

            return entry.get("body")
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def set(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        status: int,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> None:
        """Cache response if status is 200 and no GraphQL errors."""
        # Don't cache non-200 responses
        if status != 200:
            return

        # Don't cache GraphQL responses with errors
        if isinstance(body, dict) and "errors" in body:
            return

        key = self._make_key(method, url, params)
        path = self._cache_path(key)

        entry = {
            "key": key,
            "method": method.upper(),
            "url": url,
            "params": params,
            "status": status,
            # Never cache Authorization headers
            "headers": {k: v for k, v in headers.items() if k.lower() != "authorization"},
            "body": body,
            "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        try:
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(entry, f, separators=(",", ":"))
        except OSError:
            pass  # Cache write failures are non-fatal

    def make_key(self, method: str, url: str, params: dict[str, Any] | None) -> str:
        """Public method to generate cache key."""
        return self._make_key(method, url, params)