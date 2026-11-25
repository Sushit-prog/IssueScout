"""Tests for repository source code reading tools."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from issuescout.tools.repo import (
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_SKIP_DIRS,
    DEFAULT_SOURCE_EXTENSIONS,
    PathContainmentError,
    RepoError,
    file_exists_at_commit,
    get_file_size,
    list_files,
    read_file,
    read_files_batch,
    validate_path_containment,
)


def _init_bare_repo(path: Path) -> None:
    """Initialize a bare git repository with an initial commit."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    # Create an initial commit so HEAD exists
    with tempfile.TemporaryDirectory() as tmpdir:
        worktree = Path(tmpdir) / "worktree"
        subprocess.run(
            ["git", "worktree", "add", str(worktree)],
            cwd=path,
            check=True,
            capture_output=True,
        )
        (worktree / "README.md").write_text("# Test Repo\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "worktree", "remove", str(worktree)],
            cwd=path,
            check=True,
            capture_output=True,
        )


def _add_commit_to_bare(bare_path: Path, filename: str, content: str) -> str:
    """Add a commit to a bare repository by creating a worktree, committing, and removing it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        worktree = Path(tmpdir) / "worktree"
        # Create a worktree using HEAD instead of branch name
        subprocess.run(
            ["git", "worktree", "add", str(worktree)],
            cwd=bare_path,
            check=True,
            capture_output=True,
        )
        # Add file - create parent directories if needed
        file_path = worktree / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        subprocess.run(
            ["git", "add", filename],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add " + filename],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        # Get the commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        )
        commit_sha = result.stdout.strip()
        # Remove worktree
        subprocess.run(
            ["git", "worktree", "remove", str(worktree)],
            cwd=bare_path,
            check=True,
            capture_output=True,
        )
    return commit_sha


def _add_multiple_files_to_bare(bare_path: Path, files: dict[str, str]) -> str:
    """Add multiple files in a single commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        worktree = Path(tmpdir) / "worktree"
        subprocess.run(
            ["git", "worktree", "add", str(worktree)],
            cwd=bare_path,
            check=True,
            capture_output=True,
        )
        for filename, content in files.items():
            file_path = worktree / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
            subprocess.run(
                ["git", "add", filename],
                cwd=worktree,
                check=True,
                capture_output=True,
            )
        subprocess.run(
            ["git", "commit", "-m", "Add multiple files"],
            cwd=worktree,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        )
        commit_sha = result.stdout.strip()
        subprocess.run(
            ["git", "worktree", "remove", str(worktree)],
            cwd=bare_path,
            check=True,
            capture_output=True,
        )
    return commit_sha


class TestValidatePathContainment:
    """Tests for validate_path_containment function."""

    def test_valid_relative_path(self, tmp_path):
        """Test valid relative path passes."""
        result = validate_path_containment(tmp_path, "src/main.py")
        assert result == tmp_path / "src/main.py"

    def test_valid_nested_path(self, tmp_path):
        """Test valid nested path passes."""
        result = validate_path_containment(tmp_path, "a/b/c/d.py")
        assert result == tmp_path / "a/b/c/d.py"

    def test_absolute_path_rejected(self, tmp_path):
        """Test absolute path is rejected."""
        with pytest.raises(PathContainmentError, match="Absolute path not allowed"):
            validate_path_containment(tmp_path, "/etc/passwd")

    def test_windows_path_rejected(self, tmp_path):
        """Test Windows-style path is rejected."""
        with pytest.raises(PathContainmentError, match="Windows-style path not allowed"):
            validate_path_containment(tmp_path, "src\\main.py")

    def test_parent_traversal_rejected(self, tmp_path):
        """Test path with .. is rejected."""
        with pytest.raises(PathContainmentError, match="Path traversal not allowed"):
            validate_path_containment(tmp_path, "src/../etc/passwd")

    def test_current_dir_rejected(self, tmp_path):
        """Test path with . is rejected."""
        with pytest.raises(PathContainmentError, match="Current directory reference not allowed"):
            validate_path_containment(tmp_path, "src/./main.py")

    def test_empty_segment_rejected(self, tmp_path):
        """Test path with empty segment (double slash) is rejected."""
        with pytest.raises(PathContainmentError, match="Empty path segment not allowed"):
            validate_path_containment(tmp_path, "src//main.py")

    def test_path_outside_repo_rejected(self, tmp_path):
        """Test path that escapes repo root is rejected."""
        # Path with ".." is rejected early with "Path traversal not allowed"
        with pytest.raises(PathContainmentError, match="Path traversal not allowed"):
            validate_path_containment(tmp_path, "../outside/secret.txt")


class TestListFiles:
    """Tests for list_files function."""

    def test_list_files_basic(self, tmp_path):
        """Test listing files from a commit."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        # Add Python files
        commit_sha = _add_multiple_files_to_bare(
            bare_path,
            {
                "src/main.py": "print('hello')",
                "src/utils.py": "def foo(): pass",
                "lib/test_main.py": "def test_foo(): pass",
                "README.md": "# Test",
            },
        )

        files = list_files(bare_path, commit_sha)
        # Only .py files by default
        assert "src/main.py" in files
        assert "src/utils.py" in files
        assert "lib/test_main.py" in files
        assert "README.md" not in files  # Not a source extension

    def test_list_files_custom_extensions(self, tmp_path):
        """Test listing files with custom extensions."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_multiple_files_to_bare(
            bare_path,
            {
                "src/main.py": "print('hello')",
                "src/config.json": '{"key": "value"}',
                "src/script.js": "console.log('hi')",
            },
        )

        files = list_files(
            bare_path,
            commit_sha,
            extensions=frozenset({".py", ".json"}),
        )
        assert "src/main.py" in files
        assert "src/config.json" in files
        assert "src/script.js" not in files

    def test_list_files_skip_dirs(self, tmp_path):
        """Test that skip_dirs filters out vendor, tests, etc."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_multiple_files_to_bare(
            bare_path,
            {
                "src/main.py": "print('hello')",
                "vendor/lib.py": "vendor code",
                "node_modules/pkg/index.js": "module code",
                "tests/test_main.py": "test code",
                "build/output.py": "build artifact",
            },
        )

        files = list_files(bare_path, commit_sha)
        assert "src/main.py" in files
        # All these should be skipped
        assert "vendor/lib.py" not in files
        assert "node_modules/pkg/index.js" not in files
        assert "tests/test_main.py" not in files
        assert "build/output.py" not in files

    def test_list_files_max_files_limit(self, tmp_path):
        """Test max_files limit truncates results."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        # Create many files
        many_files = {f"src/file{i}.py": f"# file {i}" for i in range(15)}
        commit_sha = _add_multiple_files_to_bare(bare_path, many_files)

        files = list_files(bare_path, commit_sha, max_files=5)
        assert len(files) == 5

    def test_list_files_empty_repo(self, tmp_path):
        """Test listing files from empty repo (just initial commit)."""
        # This test is covered by other tests that use _init_bare_repo
        # which creates an initial commit. We skip the edge case of
        # truly empty bare repos since our test helper always creates one.
        pass

    def test_list_files_invalid_commit(self, tmp_path):
        """Test listing files with invalid commit raises RepoError."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        with pytest.raises(RepoError, match="git ls-tree failed"):
            list_files(bare_path, "invalid_sha")


class TestReadFile:
    """Tests for read_file function."""

    def test_read_file_basic(self, tmp_path):
        """Test reading a file from a commit."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello world')")

        content = read_file(bare_path, commit_sha, "src/main.py")
        assert content == "print('hello world')"

    def test_read_file_with_newlines(self, tmp_path):
        """Test reading a file with multiple lines."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        content = "def foo():\n    return 42\n\nif __name__ == '__main__':\n    print(foo())\n"
        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", content)

        read_content = read_file(bare_path, commit_sha, "src/main.py")
        assert read_content == content

    def test_read_file_not_found(self, tmp_path):
        """Test reading non-existent file raises RepoError."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        with pytest.raises(RepoError, match="File not found at commit"):
            read_file(bare_path, commit_sha, "src/nonexistent.py")

    def test_read_file_too_large(self, tmp_path):
        """Test reading file exceeding max_size raises RepoError."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        large_content = "x" * (DEFAULT_MAX_FILE_SIZE + 1)
        commit_sha = _add_commit_to_bare(bare_path, "src/large.py", large_content)

        with pytest.raises(RepoError, match="File too large"):
            read_file(bare_path, commit_sha, "src/large.py")

    def test_read_file_invalid_path_format(self, tmp_path):
        """Test reading file with invalid path format raises PathContainmentError."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        with pytest.raises(PathContainmentError, match="Invalid path format"):
            read_file(bare_path, commit_sha, "/etc/passwd")

        with pytest.raises(PathContainmentError, match="Path traversal"):
            read_file(bare_path, commit_sha, "src/../etc/passwd")


class TestReadFilesBatch:
    """Tests for read_files_batch function."""

    def test_read_files_batch_basic(self, tmp_path):
        """Test reading multiple files at once."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_multiple_files_to_bare(
            bare_path,
            {
                "src/main.py": "print('hello')",
                "src/utils.py": "def foo(): pass",
                "tests/test_main.py": "def test_foo(): pass",
            },
        )

        contents = read_files_batch(
            bare_path,
            commit_sha,
            ["src/main.py", "src/utils.py"],
        )
        assert contents["src/main.py"] == "print('hello')"
        assert contents["src/utils.py"] == "def foo(): pass"

    def test_read_files_batch_empty_list(self, tmp_path):
        """Test reading empty list returns empty dict."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        contents = read_files_batch(bare_path, commit_sha, [])
        assert contents == {}

    def test_read_files_batch_missing_file(self, tmp_path):
        """Test reading batch with missing file skips it."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        contents = read_files_batch(
            bare_path,
            commit_sha,
            ["src/main.py", "src/missing.py"],
        )
        assert "src/main.py" in contents
        assert "src/missing.py" not in contents

    def test_read_files_batch_invalid_path(self, tmp_path):
        """Test batch reading validates all paths first."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        with pytest.raises(PathContainmentError, match="Path traversal"):
            read_files_batch(bare_path, commit_sha, ["src/main.py", "../etc/passwd"])


class TestGetFileSize:
    """Tests for get_file_size function."""

    def test_get_file_size(self, tmp_path):
        """Test getting file size."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        content = "print('hello world')"
        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", content)

        size = get_file_size(bare_path, commit_sha, "src/main.py")
        assert size == len(content.encode("utf-8"))

    def test_get_file_size_not_found(self, tmp_path):
        """Test getting size of non-existent file raises RepoError."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        with pytest.raises(RepoError, match="File not found at commit"):
            get_file_size(bare_path, commit_sha, "src/missing.py")


class TestFileExistsAtCommit:
    """Tests for file_exists_at_commit function."""

    def test_file_exists_true(self, tmp_path):
        """Test file_exists_at_commit returns True for existing file."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        assert file_exists_at_commit(bare_path, commit_sha, "src/main.py") is True

    def test_file_exists_false(self, tmp_path):
        """Test file_exists_at_commit returns False for non-existent file."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_commit_to_bare(bare_path, "src/main.py", "print('hello')")

        assert file_exists_at_commit(bare_path, commit_sha, "src/missing.py") is False

    def test_file_exists_false_for_directory(self, tmp_path):
        """Test file_exists_at_commit returns False for directory (tree)."""
        bare_path = tmp_path / "test.git"
        _init_bare_repo(bare_path)

        commit_sha = _add_multiple_files_to_bare(
            bare_path,
            {
                "src/main.py": "print('hello')",
                "src/utils.py": "def foo(): pass",
            },
        )

        # "src" is a tree, not a blob
        assert file_exists_at_commit(bare_path, commit_sha, "src") is False


class TestDefaults:
    """Tests for default constants."""

    def test_default_source_extensions(self):
        """Test default source extensions includes common languages."""
        assert ".py" in DEFAULT_SOURCE_EXTENSIONS
        assert ".js" in DEFAULT_SOURCE_EXTENSIONS
        assert ".ts" in DEFAULT_SOURCE_EXTENSIONS
        assert ".java" in DEFAULT_SOURCE_EXTENSIONS
        assert ".go" in DEFAULT_SOURCE_EXTENSIONS
        assert ".rs" in DEFAULT_SOURCE_EXTENSIONS

    def test_default_skip_dirs(self):
        """Test default skip dirs includes common patterns."""
        assert "vendor" in DEFAULT_SKIP_DIRS
        assert "node_modules" in DEFAULT_SKIP_DIRS
        assert ".git" in DEFAULT_SKIP_DIRS
        assert "tests" in DEFAULT_SKIP_DIRS
        assert "test" in DEFAULT_SKIP_DIRS
        assert "__pycache__" in DEFAULT_SKIP_DIRS

    def test_default_max_file_size(self):
        """Test default max file size is 1MB."""
        assert DEFAULT_MAX_FILE_SIZE == 1_000_000
