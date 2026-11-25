"""Citation model for verified file/symbol references."""

from pydantic import BaseModel, ConfigDict, Field


class Citation(BaseModel):
    """A verified citation to a file and optional symbol at a specific commit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(description="Repository-relative file path")
    symbol: str | None = Field(default=None, description="Function/class name if applicable")
    line_start: int = Field(ge=1, description="Start line number (1-indexed)")
    line_end: int = Field(ge=1, description="End line number (1-indexed, inclusive)")
    commit_sha: str = Field(description="Full commit SHA where this citation was verified")
    rationale: str = Field(description="Why this citation is relevant to the issue")

    def __str__(self) -> str:
        loc = f"{self.path}:{self.line_start}-{self.line_end}"
        if self.symbol:
            return f"{loc}::{self.symbol} @ {self.commit_sha[:8]}"
        return f"{loc} @ {self.commit_sha[:8]}"
