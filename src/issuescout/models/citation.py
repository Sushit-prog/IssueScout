"""Citation model for verified file/symbol references."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import core_schema


def _validate_path(path: str) -> str:
    """Validate that path is non-empty, repo-relative, POSIX-style, no '..' segments."""
    if not path:
        raise ValueError("path must be non-empty")
    if path.startswith("/"):
        raise ValueError("path must be repo-relative (not absolute)")
    if "\\" in path:
        raise ValueError("path must use POSIX-style forward slashes")
    parts = path.split("/")
    if any(part == ".." for part in parts):
        raise ValueError("path must not contain '..' segments")
    if any(part == "." for part in parts):
        raise ValueError("path must not contain '.' segments")
    return path


def _validate_line_end(line_end: int, values: core_schema.ValidationInfo) -> int:
    """Validate that line_end >= line_start."""
    line_start = values.data.get("line_start")
    if line_start is not None and line_end < line_start:
        raise ValueError("line_end must be >= line_start")
    return line_end


class Citation(BaseModel):
    """A verified citation to a file and optional symbol at a specific commit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(description="Repository-relative file path")
    symbol: str | None = Field(default=None, description="Function/class name if applicable")
    line_start: int = Field(ge=1, description="Start line number (1-indexed)")
    line_end: int = Field(ge=1, description="End line number (1-indexed, inclusive)")
    commit_sha: str = Field(description="Full commit SHA where this citation was verified")
    rationale: str = Field(description="Why this citation is relevant to the issue")

    _validate_path = field_validator("path", mode="before")(_validate_path)
    _validate_line_end = field_validator("line_end", mode="after")(_validate_line_end)

    def __str__(self) -> str:
        loc = f"{self.path}:{self.line_start}-{self.line_end}"
        if self.symbol:
            return f"{loc}::{self.symbol} @ {self.commit_sha[:8]}"
        return f"{loc} @ {self.commit_sha[:8]}"
