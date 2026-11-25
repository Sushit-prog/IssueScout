"""Candidate model for ranked issue localization results."""

from pydantic import BaseModel, ConfigDict, Field

from issuescout.models.citation import Citation


class Candidate(BaseModel):
    """A ranked candidate file/function with evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: Citation
    score: float = Field(ge=0.0, le=1.0, description="Confidence score [0, 1]")
    evidence: list[str] = Field(
        default_factory=list,
        description="Human-readable evidence strings supporting this candidate"
    )