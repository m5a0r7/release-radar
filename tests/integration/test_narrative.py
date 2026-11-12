from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import Project, Release, Workspace
from radar.insights.drift import compute_drift
from radar.insights.evidence import build_evidence
from radar.insights.schemas import DriftReport
from radar.narrative.llm import LLMError
from radar.narrative.service import NarrativeService
from tests.factories import scenario


class FakeLLM:
    provider = "fake"
    model = "fake-1"

    def __init__(self, *responses: dict[str, Any] | Exception) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def generate(
        self, system: str, prompt: str, tool_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.prompts.append(prompt)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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
