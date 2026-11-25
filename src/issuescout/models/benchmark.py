"""Benchmark example model."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from issuescout.models.issue_ref import IssueRef


class SplitTag(StrEnum):
    """Split tag for train/test leakage control."""

    PRE_CUTOFF = "pre_cutoff"
    POST_CUTOFF = "post_cutoff"


class ChangedFile(BaseModel):
    """Changed file with locatability at base commit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    status: str  # added, modified, removed, renamed
    old_path: str | None = None
    additions: int = 0
    deletions: int = 0
    locatable_at_base: bool = True


class BenchmarkExample(BaseModel):
    """A single benchmark example from a real GitHub PR."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue: IssueRef
    base_commit_sha: str
    issue_title: str
    issue_body: str
    gold_files_all: list[str]
    gold_files_source: list[str]
    pr_number: int
    merged_at: datetime
    issue_created_at: datetime
    pr_opened_at: datetime
    changed_files: list[ChangedFile]
    split_tag: SplitTag
