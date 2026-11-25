"""Repository source code reading tools using git cat-file/ls-tree (no working tree)."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class RepoError(Exception):
    """Raised when repository operations fail."""

    pass


class PathContainmentError(RepoError):
    """Raised when a path escapes the repository root."""

    pass


DEFAULT_SOURCE_EXTENSIONS = frozenset(
    {".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".cc", ".c", ".h", ".hpp"}
)
DEFAULT_SKIP_DIRS = frozenset(
    {
        "vendor",
        "node_modules",
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
        "out",
        "bin",
        "obj",
        ".venv",
        "venv",
        "env",
        "test",
        "tests",
        "testing",
        "spec",
        "specs",
        "fixtures",
        "fixture",
    }
)
DEFAULT_MAX_FILE_SIZE = 1_000_000  # 1 MB


def _run_git(args: list[str], cwd: Path, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    """Run a git command."""
    cmd = ["git", *args]
    logger.debug(f"Running: {' '.join(cmd)} in {cwd}")
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


def validate_path_containment(repo_root: Path, target_path: str) -> Path:
    """Validate that a repo-relative path stays within the repository.

    Args:
        repo_root: Absolute path to repository root
        target_path: Repo-relative POSIX-style path (no ".." segments)

    Returns:
        Resolved absolute Path within repo_root

    Raises:
        PathContainmentError: If path escapes repo or contains invalid segments
    """
    # Reject absolute paths
    if target_path.startswith("/"):
        raise PathContainmentError(f"Absolute path not allowed: {target_path}")

    # Reject Windows-style paths
    if "\\" in target_path:
        raise PathContainmentError(f"Windows-style path not allowed: {target_path}")

    # Reject ".." segments
    parts = target_path.split("/")
    if ".." in parts:
        raise PathContainmentError(f"Path traversal not allowed: {target_path}")

    # Reject "." segments
    if "." in parts:
        raise PathContainmentError(f"Current directory reference not allowed: {target_path}")

    # Reject empty segments (double slashes)
    if "" in parts:
        raise PathContainmentError(f"Empty path segment not allowed: {target_path}")

    # Resolve and check containment
    resolved = (repo_root / target_path).resolve()
    repo_root_resolved = repo_root.resolve()

    try:
        resolved.relative_to(repo_root_resolved)
    except ValueError:
        raise PathContainmentError(f"Path escapes repository: {target_path}") from None

    return resolved


def list_files(
    bare_repo_path: Path,
    commit_sha: str,
    *,
    extensions: frozenset[str] = DEFAULT_SOURCE_EXTENSIONS,
    skip_dirs: frozenset[str] = DEFAULT_SKIP_DIRS,
    max_files: int = 10_000,
) -> list[str]:
    """List source files at a commit using git ls-tree.

    Args:
        bare_repo_path: Path to bare repository
        commit_sha: Commit SHA to list files from
        extensions: File extensions to include (default: source code extensions)
        skip_dirs: Directory names to skip (default: vendor, tests, build dirs)
        max_files: Maximum number of files to return

    Returns:
        List of repo-relative POSIX-style file paths

    Raises:
        RepoError: If git command fails
    """
    try:
        result = _run_git(
            ["ls-tree", "-r", "--name-only", commit_sha],
            cwd=bare_repo_path,
        )
    except subprocess.CalledProcessError as e:
        raise RepoError(f"git ls-tree failed: {e.stderr}") from e

    files = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if not path:
            continue

        # Check skip directories
        path_parts = path.split("/")
        if any(part in skip_dirs for part in path_parts):
            continue

        # Check extension
        if not any(path.endswith(ext) for ext in extensions):
            continue

        files.append(path)

        if len(files) >= max_files:
            logger.warning(f"Hit max_files limit ({max_files}), truncating")
            break

    return files


def read_file(
    bare_repo_path: Path,
    commit_sha: str,
    file_path: str,
    *,
    max_size: int = DEFAULT_MAX_FILE_SIZE,
) -> str:
    """Read a file at a commit using git cat-file.

    Args:
        bare_repo_path: Path to bare repository
        commit_sha: Commit SHA
        file_path: Repo-relative POSIX-style file path
        max_size: Maximum file size in bytes

    Returns:
        File contents as string (UTF-8 decoded)

    Raises:
        RepoError: If file not found, too large, or git command fails
        PathContainmentError: If file_path escapes repository
    """
    # Validate path containment
    # We use a dummy root since bare repos don't have working tree paths,
    # but we still validate the path format
    try:
        # Validate path format only (no actual filesystem check needed)
        if file_path.startswith("/") or "\\" in file_path:
            raise PathContainmentError(f"Invalid path format: {file_path}")
        if (
            ".." in file_path.split("/")
            or "." in file_path.split("/")
            or "" in file_path.split("/")
        ):
            raise PathContainmentError(f"Path traversal or invalid segment: {file_path}")
    except PathContainmentError:
        raise

    # Use git cat-file --batch for efficient reading
    try:
        # First check the object type and size
        result = _run_git(
            ["cat-file", "-t", f"{commit_sha}:{file_path}"],
            cwd=bare_repo_path,
        )
        if result.stdout.strip() != "blob":
            raise RepoError(f"Not a file (blob): {file_path}")

        # Check size
        result = _run_git(
            ["cat-file", "-s", f"{commit_sha}:{file_path}"],
            cwd=bare_repo_path,
        )
        size = int(result.stdout.strip())
        if size > max_size:
            raise RepoError(f"File too large: {file_path} ({size} bytes > {max_size})")

        # Read content
        result = _run_git(
            ["cat-file", "blob", f"{commit_sha}:{file_path}"],
            cwd=bare_repo_path,
        )
        return result.stdout

    except subprocess.CalledProcessError as e:
        if "not a valid object name" in e.stderr or "does not exist" in e.stderr:
            raise RepoError(f"File not found at commit: {file_path}") from e
        raise RepoError(f"git cat-file failed: {e.stderr}") from e


def read_files_batch(
    bare_repo_path: Path,
    commit_sha: str,
    file_paths: list[str],
    *,
    max_size: int = DEFAULT_MAX_FILE_SIZE,
) -> dict[str, str]:
    """Read multiple files efficiently using git cat-file --batch.

    Args:
        bare_repo_path: Path to bare repository
        commit_sha: Commit SHA
        file_paths: List of repo-relative POSIX-style file paths
        max_size: Maximum file size in bytes per file

    Returns:
        Dict mapping file_path -> content (only successfully read files)

    Raises:
        RepoError: If git command fails
    """
    if not file_paths:
        return {}

    # Validate all paths first
    for fp in file_paths:
        if fp.startswith("/") or "\\" in fp:
            raise PathContainmentError(f"Invalid path format: {fp}")
        parts = fp.split("/")
        if ".." in parts or "." in parts or "" in parts:
            raise PathContainmentError(f"Path traversal or invalid segment: {fp}")

    # Build input for cat-file --batch
    # Format: <sha>:<path>
    input_data = "\n".join(f"{commit_sha}:{fp}" for fp in file_paths) + "\n"

    try:
        # Use binary mode to handle raw blob data correctly
        result = subprocess.run(
            ["git", "cat-file", "--batch"],
            cwd=bare_repo_path,
            input=input_data.encode("utf-8"),
            capture_output=True,
            timeout=60.0,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RepoError(
            f"git cat-file --batch failed: {e.stderr.decode('utf-8', errors='replace')}"
        ) from e

    contents = {}
    stdout = result.stdout
    file_idx = 0
    offset = 0

    while offset < len(stdout) and file_idx < len(file_paths):
        # Find end of header line (newline)
        header_end = stdout.find(b"\n", offset)
        if header_end == -1:
            break
        header_line = stdout[offset:header_end].decode("utf-8", errors="replace").strip()
        offset = header_end + 1

        if not header_line:
            continue

        # Header line: <sha> <type> <size>
        parts = header_line.split()
        if len(parts) != 3:
            logger.warning(f"Unexpected cat-file output: {header_line}")
            file_idx += 1
            continue

        obj_sha, obj_type, size_str = parts
        try:
            size = int(size_str)
        except ValueError:
            logger.warning(f"Invalid size in cat-file output: {size_str}")
            file_idx += 1
            continue

        if obj_type != "blob":
            # Missing or not a blob - skip
            file_idx += 1
            continue

        if size > max_size:
            logger.warning(f"File too large, skipping: {file_paths[file_idx]} ({size} bytes)")
            # Skip the blob data
            offset += size
            # Skip trailing newline after blob data
            if offset < len(stdout) and stdout[offset : offset + 1] == b"\n":
                offset += 1
            file_idx += 1
            continue

        # Read blob data (exact size bytes)
        if offset + size > len(stdout):
            logger.warning(f"Truncated blob data for {file_paths[file_idx]}")
            break

        blob_data = stdout[offset : offset + size]
        offset += size

        # Skip trailing newline after blob data
        if offset < len(stdout) and stdout[offset : offset + 1] == b"\n":
            offset += 1

        # Decode blob content
        try:
            content = blob_data.decode("utf-8")
        except UnicodeDecodeError:
            content = blob_data.decode("utf-8", errors="replace")
            logger.warning(f"Non-UTF-8 content in {file_paths[file_idx]}, replaced invalid chars")

        contents[file_paths[file_idx]] = content
        file_idx += 1

    return contents


def get_file_size(
    bare_repo_path: Path,
    commit_sha: str,
    file_path: str,
) -> int:
    """Get the size of a file at a commit without reading its content.

    Args:
        bare_repo_path: Path to bare repository
        commit_sha: Commit SHA
        file_path: Repo-relative POSIX-style file path

    Returns:
        File size in bytes

    Raises:
        RepoError: If file not found or git command fails
    """
    try:
        result = _run_git(
            ["cat-file", "-s", f"{commit_sha}:{file_path}"],
            cwd=bare_repo_path,
        )
        return int(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        if "not a valid object name" in e.stderr or "does not exist" in e.stderr:
            raise RepoError(f"File not found at commit: {file_path}") from e
        raise RepoError(f"git cat-file -s failed: {e.stderr}") from e


def file_exists_at_commit(
    bare_repo_path: Path,
    commit_sha: str,
    file_path: str,
) -> bool:
    """Check if a file exists at a commit.

    Args:
        bare_repo_path: Path to bare repository
        commit_sha: Commit SHA
        file_path: Repo-relative POSIX-style file path

    Returns:
        True if file exists as a blob at that commit
    """
    try:
        result = _run_git(
            ["cat-file", "-t", f"{commit_sha}:{file_path}"],
            cwd=bare_repo_path,
        )
        return result.stdout.strip() == "blob"
    except subprocess.CalledProcessError:
        return False
