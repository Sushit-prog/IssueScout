"""Benchmark mining configuration."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class RepoConfig(BaseModel):
    """Configuration for a single repository."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str = Field(description="Repository owner")
    name: str = Field(description="Repository name")
    max_prs: int = Field(default=500, ge=1, description="Maximum PRs to process")
    since: datetime | None = Field(default=None, description="Start date for merged PRs")
    until: datetime | None = Field(default=None, description="End date for merged PRs")


class BenchConfig(BaseModel):
    """Benchmark mining configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repos: list[RepoConfig] = Field(min_length=1, description="Repositories to mine")
    leakage_cutoff: datetime = Field(
        description="Cutoff date for train/test split (must be after model training cutoff)"
    )
    out_path: Path = Field(default=Path("data/bench.jsonl"), description="Output JSONL path")
    cache_dir: Path = Field(default=Path(".cache/github"), description="Cache directory")
    max_concurrent: int = Field(
        default=1, ge=1, description="Max concurrent requests (1 = synchronous)"
    )

    @property
    def cache_dir_abs(self) -> Path:
        return self.cache_dir
