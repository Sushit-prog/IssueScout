"""Benchmark example model."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict

from issuescout.models.issue_ref import IssueRef


class BenchmarkExample(BaseModel):
    """A single benchmark example from a real GitHub PR."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue: IssueRef
    base_commit_sha: str
    issue_title: str
    issue_body: str
    gold_files_changed: list[str]
    pr_number: int
    merged_at: datetime