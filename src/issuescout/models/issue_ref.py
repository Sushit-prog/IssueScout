"""Issue reference model."""

from pydantic import BaseModel, ConfigDict


class IssueRef(BaseModel):
    """Reference to a GitHub issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: str
    repo: str
    number: int

    def __str__(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"