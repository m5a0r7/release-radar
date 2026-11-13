from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.container import Container
from radar.db.models import LlmCall, Project, Release, Workspace
from radar.insights.drift import compute_drift
from radar.insights.evidence import build_evidence
from radar.insights.schemas import DriftReport
from radar.narrative.llm import LLMError, LLMResult
from radar.narrative.quota import LlmLimits, QuotaExceededError, UsageLedger
from radar.narrative.service import NarrativeLimits, NarrativeService
from tests.factories import scenario


class FakeLLM:
    provider = "fake"
    model = "fake-1"

    def __init__(self, *responses: dict[str, Any] | Exception) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def generate(
        self, system: str, prompt: str, tool_name: str, schema: dict[str, Any]
    ) -> LLMResult:
        self.prompts.append(prompt)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return LLMResult(response, input_tokens=1_000, output_tokens=200)


async def report(session: AsyncSession) -> DriftReport:
    workspace = Workspace(name="Test")
    session.add(workspace)
    await session.flush()
    project = Project(workspace_id=workspace.id, slug="demo", tracker="jira", tracker_key="DEMO")
    session.add(project)
    await session.flush()
    release = Release(
        project_id=project.id, external_id="100", name="1.0", released=False, archived=False
    )
    session.add(release)
    await session.flush()
    base = compute_drift(scenario())
    return base.model_copy(update={"release": base.release.model_copy(update={"id": release.id})})


def answer(report: DriftReport, claim: str, confidence: float = 0.95) -> dict[str, Any]:
    ids = {e.metric: e.id for e in build_evidence(report)}
    return {
        "analysis": "Scope churn is small; one item was tagged at resolution.",
        "summary": "Release 1.0 is at risk.",
        "findings": [
            {
                "claim": claim,
                "hypothesis": "Work is tagged to the release when it is resolved.",
                "confidence": confidence,
                "evidence_ids": [ids["planning.unplanned_share"], ids["progress.completed"]],
            }
        ],
        "recommendation": {
            "action": "Defer K-C to the next release.",
            "rationale": "It has been idle.",
            "item_keys": ["K-C"],
            "evidence_ids": [ids["idle.items"]],
        },
    }


async def test_hallucinated_number_is_repaired(session: AsyncSession) -> None:
    drift = await report(session)
    llm = FakeLLM(
        answer(drift, "73% of the 2 completed items were unplanned."),
        answer(drift, "50% of the 2 completed items were unplanned."),
    )

    result = await NarrativeService(llm).narrate(session, drift)

    assert not result.meta.degraded
    assert result.meta.verification_errors == []
    assert "number 73 does not match" in llm.prompts[1]
    assert result.findings[0].model_confidence == 0.95
    assert result.findings[0].confidence == result.meta.confidence_cap < 0.95
    assert result.recommendation is not None and result.recommendation.item_keys == ["K-C"]


async def test_persistent_hallucination_degrades_to_template(session: AsyncSession) -> None:
    drift = await report(session)
    bad = answer(drift, "99 items were unplanned.")

    result = await NarrativeService(FakeLLM(bad, bad)).narrate(session, drift)

    assert result.meta.degraded
    assert result.meta.provider == "template"
    assert result.meta.verification_errors


async def test_llm_outage_degrades_and_is_not_cached(session: AsyncSession) -> None:
    drift = await report(session)
    good = answer(drift, "50% of the 2 completed items were unplanned.")
    llm = FakeLLM(LLMError("timeout"), good)
    service = NarrativeService(llm)

    degraded = await service.narrate(session, drift)
    recovered = await service.narrate(session, drift)
    cached = await service.narrate(session, drift)

    assert degraded.meta.degraded
    assert not recovered.meta.degraded and not recovered.meta.cached
    assert cached.meta.cached
    assert len(llm.prompts) == 2


async def test_malformed_output_is_retried(session: AsyncSession) -> None:
    drift = await report(session)
    llm = FakeLLM({"summary": "x"}, answer(drift, "50% of completed items were unplanned."))

    result = await NarrativeService(llm).narrate(session, drift)

    assert not result.meta.degraded
    assert "schema:" in llm.prompts[1]


async def test_workspace_quota_is_enforced_and_usage_recorded(
    session: AsyncSession, container: Container
) -> None:
    drift = await report(session)
    workspace_id = await session.scalar(select(Workspace.id))
    await session.commit()
    good = answer(drift, "50% of the 2 completed items were unplanned.")
    ledger = UsageLedger(container.sessions, LlmLimits(requests_per_hour=1, tokens_per_day=10**6))
    service = NarrativeService(FakeLLM(good, good), ledger=ledger)

    first = await service.narrate(session, drift, workspace_id=workspace_id)
    with pytest.raises(QuotaExceededError) as exceeded:
        await service.narrate(session, drift, workspace_id=workspace_id, refresh=True)
    cached = await service.narrate(session, drift, workspace_id=workspace_id)

    assert not first.meta.degraded and cached.meta.cached
    assert 0 < exceeded.value.retry_after_seconds <= 3600
    calls = (await session.execute(select(LlmCall))).scalars().all()
    assert [(c.outcome, c.input_tokens, c.output_tokens) for c in calls] == [("ok", 1_000, 200)]


async def test_prompt_over_budget_falls_back_without_calling_the_llm(
    session: AsyncSession,
) -> None:
    drift = await report(session)
    llm = FakeLLM()
    limits = NarrativeLimits(max_input_tokens=2_000, max_output_tokens=1_000)

    result = await NarrativeService(llm, limits=limits).narrate(session, drift)

    assert result.meta.degraded and llm.prompts == []
    assert result.meta.verification_errors == ["evidence exceeds the LLM input budget"]
