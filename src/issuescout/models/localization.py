"""Localization result model."""

from pydantic import BaseModel, ConfigDict, Field

from issuescout.models.candidate import Candidate


class LocalizationResult(BaseModel):
    """Result of issue localization with ranked candidates and metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: list[Candidate] = Field(description="Ranked candidate list")
    budget_used: dict[str, float] = Field(
        default_factory=dict,
        description="Token/cost budget consumed (e.g., 'tokens', 'usd')"
    )
    trace_id: str = Field(description="Unique trace ID for this localization run")