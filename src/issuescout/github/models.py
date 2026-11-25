"""Typed request/response models for GitHub API."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PRState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"
    COPIED = "copied"
    CHANGED = "changed"


class IssueData(BaseModel):
    """Issue data from GitHub API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int
    title: str
    body: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    state: str
    html_url: str


class PRDetails(BaseModel):
    """PR details from GitHub API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int
    title: str
    body: str | None
    state: str
    merged: bool
    mergeable: bool | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    merged_at: datetime | None
    base_sha: str
    head_sha: str
    base_ref: str
    head_ref: str
    html_url: str
    closing_issues: list[int]  # issue numbers this PR closes

    @field_validator("closing_issues", mode="before")
    @classmethod
    def _parse_closing_issues(cls, v: Any) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        return []


class ChangedFileData(BaseModel):
    """Changed file from GitHub API (REST /pulls/{n}/files)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str
    status: FileStatus
    previous_filename: str | None = None
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    sha: str | None = None
    patch: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: str) -> FileStatus:
        mapping = {
            "added": FileStatus.ADDED,
            "modified": FileStatus.MODIFIED,
            "removed": FileStatus.REMOVED,
            "renamed": FileStatus.RENAMED,
            "copied": FileStatus.COPIED,
            "changed": FileStatus.CHANGED,
        }
        return mapping.get(v.lower(), FileStatus.MODIFIED)


class PRPage(BaseModel):
    """Paginated PR list from GraphQL search."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: list[PRDetails]
    page_info: "PageInfo"
    total_count: int


class PageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    has_next_page: bool
    end_cursor: str | None = None


class RateLimitInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit: int
    remaining: int
    reset_at: datetime
    used: int


# Update forward refs
PageInfo.model_rebuild()
PRPage.model_rebuild()