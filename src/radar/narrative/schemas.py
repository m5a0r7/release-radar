from datetime import datetime

from pydantic import BaseModel, Field

from radar.insights.evidence import Evidence
from radar.insights.schemas import DriftStatus, Period


class DraftFinding(BaseModel):
    claim: str = Field(max_length=500)
    hypothesis: str | None = Field(default=None, max_length=500)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class DraftRecommendation(BaseModel):
    action: str = Field(max_length=300)
    rationale: str = Field(max_length=500)
    item_keys: list[str] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class NarrativeDraft(BaseModel):
    """What the model must return (via a forced tool call). `analysis` is its scratchpad."""

    analysis: str = Field(default="", max_length=6000)
    summary: str = Field(max_length=800)
    findings: list[DraftFinding] = Field(min_length=1, max_length=5)
    recommendation: DraftRecommendation | None = None


class Finding(BaseModel):
    claim: str
    hypothesis: str | None
    confidence: float = Field(description="Calibrated: min(model confidence, data-support cap).")
    model_confidence: float
    evidence: list[Evidence]


class Recommendation(BaseModel):
    action: str
    rationale: str
    item_keys: list[str]
    evidence: list[Evidence]
    requires_approval: bool = True


class NarrativeMeta(BaseModel):
    provider: str
    model: str
    prompt_version: str
    generated_at: datetime
    cached: bool
    degraded: bool = Field(description="True when the LLM failed and a template was used.")
    confidence_cap: float
    verification_errors: list[str]


class NarrativeResponse(BaseModel):
    project: str
    release: str
    period: Period
    status: DriftStatus
    summary: str
    findings: list[Finding]
    recommendation: Recommendation | None
    caveats: list[str]
    meta: NarrativeMeta
