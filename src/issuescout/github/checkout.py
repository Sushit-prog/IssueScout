"""Bare repository checkout management for GitHub repos."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    """Raised when bare repository checkout fails."""

    pass


def get_bare_repo_path(cache_dir: Path, owner: str, repo: str) -> Path:
    """Get the bare repository path for a given owner/repo."""
    # Use double underscore to avoid collisions with repo names containing hyphens
    safe_name = f"{owner}__{repo}.git"
    return cache_dir / safe_name


def ensure_bare_repo(cache_dir: Path, owner: str, repo: str, timeout: float = 60.0) -> Path:
    """Ensure a bare repository exists and is up to date.

    Creates the bare repo if it doesn't exist, then fetches the latest
    from origin. Idempotent - safe to call multiple times.

    Args:
        cache_dir: Base cache directory (e.g., .cache/repos)
        owner: Repository owner
        repo: Repository name
        timeout: Timeout in seconds for git operations

    Returns:
        Path to the bare repository

    Raises:
        CheckoutError: If git operations fail
    """
    repo_path = get_bare_repo_path(cache_dir, owner, repo)
    origin_url = f"https://github.com/{owner}/{repo}.git"

    # Ensure cache directory exists
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not repo_path.exists():
        logger.info(f"Cloning bare repository: {owner}/{repo}")
        try:
            _run_git(
                ["clone", "--bare", origin_url, str(repo_path)],
                timeout=timeout,
                cwd=cache_dir,
            )
        except subprocess.CalledProcessError as e:
            raise CheckoutError(f"Failed to clone {owner}/{repo}: {e.stderr}") from e
    else:
        logger.debug(f"Bare repository exists: {repo_path}")

    # Always fetch to update refs (idempotent)
    logger.debug(f"Fetching updates for {owner}/{repo}")
    try:
        _run_git(
            ["fetch", "origin", "--prune", "--tags"],
            timeout=timeout,
            cwd=repo_path,
        )
    except subprocess.CalledProcessError as e:
        raise CheckoutError(f"Failed to fetch {owner}/{repo}: {e.stderr}") from e

    return repo_path


def fetch_commit(
    bare_repo_path: Path,
    commit_sha: str,
    timeout: float = 60.0,
) -> None:
    """Fetch a specific commit SHA into the bare repository.

    Uses `git fetch --depth 1 origin <sha>` for efficiency.
    Idempotent - safe to call multiple times.

    Args:
        bare_repo_path: Path to the bare repository
        commit_sha: Full 40-character commit SHA to fetch
        timeout: Timeout in seconds for git operations

    Raises:
        CheckoutError: If git fetch fails or commit not found
    """
    if not bare_repo_path.exists():
        raise CheckoutError(f"Bare repository does not exist: {bare_repo_path}")

    logger.debug(f"Fetching commit {commit_sha[:12]} into {bare_repo_path}")
    try:
        _run_git(
            ["fetch", "--depth", "1", "origin", commit_sha],
            timeout=timeout,
            cwd=bare_repo_path,
        )
    except subprocess.CalledProcessError as e:
        raise CheckoutError(f"Failed to fetch commit {commit_sha}: {e.stderr}") from e


def commit_exists(bare_repo_path: Path, commit_sha: str) -> bool:
    """Check if a commit exists in the bare repository.

    Args:
        bare_repo_path: Path to the bare repository
        commit_sha: Commit SHA to check

    Returns:
        True if commit exists, False otherwise
    """
    if not bare_repo_path.exists():
        return False

    try:
        result = _run_git(
            ["cat-file", "-t", commit_sha],
            timeout=10.0,
            cwd=bare_repo_path,
            capture_output=True,
        )
        return result.returncode == 0 and "commit" in result.stdout
    except Exception:
        return False


def _run_git(
    args: list[str],
    timeout: float,
    cwd: Path,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command with the given arguments.

    Args:
        args: Git command arguments (without 'git')
        timeout: Timeout in seconds
        cwd: Working directory
        capture_output: Whether to capture stdout/stderr

    Returns:
        CompletedProcess result

    Raises:
        subprocess.CalledProcessError: If command fails
    """
    cmd = ["git", *args]
    logger.debug(f"Running: {' '.join(cmd)} in {cwd}")
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        text=True,
        timeout=timeout,
        check=True,
    )


def get_repo_size(bare_repo_path: Path) -> int:
    """Get the size of the bare repository in bytes.

    Args:
        bare_repo_path: Path to the bare repository

    Returns:
        Size in bytes, or 0 if not found
    """
    if not bare_repo_path.exists():
        return 0

    try:
        result = _run_git(
            ["count-objects", "-v"],
            timeout=10.0,
            cwd=bare_repo_path,
            capture_output=True,
        )
        # Parse output for size-pack
        for line in result.stdout.splitlines():
            if line.startswith("size-pack:"):
                return int(line.split(":", 1)[1].strip()) * 1024  # Convert KB to bytes
    except Exception:
        pass
    return 0
