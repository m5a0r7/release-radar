import hashlib
import json
from datetime import UTC, datetime

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import Narrative
from radar.insights.evidence import Evidence, build_evidence
from radar.insights.schemas import DriftReport
from radar.narrative.confidence import ConfidenceCap, calibrate, data_support_cap
from radar.narrative.llm import LLMError, StructuredLLM
from radar.narrative.prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_NAME,
    output_schema,
    repair_message,
    user_message,
)
from radar.narrative.schemas import (
    Finding,
    NarrativeDraft,
    NarrativeMeta,
    NarrativeResponse,
    Recommendation,
)
from radar.narrative.template import template_draft
from radar.narrative.verifier import verify

log = structlog.get_logger(__name__)

MAX_ATTEMPTS = 2


class NarrativeService:
    """Evidence -> LLM draft -> grounding verification -> calibrated, cached response.

    The LLM never sees raw upstream text (titles, descriptions), only computed evidence, which
    keeps the prompt-injection surface minimal. Any failure degrades to the template narrator.
    """

    def __init__(self, llm: StructuredLLM | None) -> None:
        self._llm = llm

    @property
    def _identity(self) -> tuple[str, str]:
        if self._llm is None:
            return "template", "template"
        return self._llm.provider, self._llm.model

    async def narrate(
        self, session: AsyncSession, report: DriftReport, *, refresh: bool = False
    ) -> NarrativeResponse:
        evidence = build_evidence(report)
        cap = data_support_cap(report)
        provider, model = self._identity
        cache_key = _cache_key(report, evidence, provider, model)

        if not refresh:
            cached = await session.scalar(select(Narrative).where(Narrative.cache_key == cache_key))
            if cached is not None:
                response = NarrativeResponse.model_validate(cached.payload)
                response.meta.cached = True
                return response

        draft, errors, degraded = await self._draft(report, evidence)
        response = _assemble(report, evidence, draft, cap, provider, model, degraded, errors)
        if not degraded:
            await session.execute(
                insert(Narrative)
                .values(
                    cache_key=cache_key,
                    release_id=report.release.id,
                    model=f"{provider}:{model}",
                    prompt_version=PROMPT_VERSION,
                    payload=response.model_dump(mode="json"),
                )
                .on_conflict_do_nothing(index_elements=[Narrative.cache_key])
            )
        return response

    async def _draft(
        self, report: DriftReport, evidence: list[Evidence]
    ) -> tuple[NarrativeDraft, list[str], bool]:
        if self._llm is None:
            return template_draft(report, evidence), [], False

        allowed_keys = _allowed_keys(evidence)
        dates = [report.period.start.isoformat(), report.period.end.isoformat()]
        prompt = user_message(report, evidence)
        errors: list[str] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                raw = await self._llm.generate(SYSTEM_PROMPT, prompt, TOOL_NAME, output_schema())
                draft = NarrativeDraft.model_validate(raw)
            except LLMError as exc:
                errors = [str(exc)]
                break
            except ValidationError as exc:
                errors = [f"schema: {e['loc']}: {e['msg']}" for e in exc.errors()][:10]
                prompt = f"{user_message(report, evidence)}\n\n{repair_message(errors)}"
                continue

            errors = verify(draft, evidence, allowed_keys, dates, [report.release.name])
            if not errors:
                return draft, [], False
            log.warning("narrative_verification_failed", attempt=attempt, errors=errors)
            previous = draft.model_dump_json(exclude={"analysis"})
            prompt = (
                f"{user_message(report, evidence)}\n\n<previous_answer>\n{previous}\n"
                f"</previous_answer>\n\n{repair_message(errors)}"
            )

        log.warning("narrative_degraded", errors=errors)
        return template_draft(report, evidence), errors, True


def _assemble(
    report: DriftReport,
    evidence: list[Evidence],
    draft: NarrativeDraft,
    cap: ConfidenceCap,
    provider: str,
    model: str,
    degraded: bool,
    errors: list[str],
) -> NarrativeResponse:
    by_id = {e.id: e for e in evidence}

    def resolve(ids: list[str]) -> list[Evidence]:
        return [by_id[i] for i in dict.fromkeys(ids) if i in by_id]

    rec = draft.recommendation
    return NarrativeResponse(
        project=report.project,
        release=report.release.name,
        period=report.period,
        status=report.status,
        summary=draft.summary,
        findings=[
            Finding(
                claim=f.claim,
                hypothesis=f.hypothesis,
                confidence=calibrate(f.confidence, cap),
                model_confidence=f.confidence,
                evidence=resolve(f.evidence_ids),
            )
            for f in draft.findings
        ],
        recommendation=Recommendation(
            action=rec.action,
            rationale=rec.rationale,
            item_keys=rec.item_keys,
            evidence=resolve(rec.evidence_ids),
        )
        if rec
        else None,
        caveats=cap.reasons,
        meta=NarrativeMeta(
            provider="template" if degraded else provider,
            model="template" if degraded else model,
            prompt_version=PROMPT_VERSION,
            generated_at=datetime.now(UTC),
            cached=False,
            degraded=degraded,
            confidence_cap=cap.value,
            verification_errors=errors,
        ),
    )


def _allowed_keys(evidence: list[Evidence]) -> set[str]:
    return {key for e in evidence for key in e.keys}


def _cache_key(report: DriftReport, evidence: list[Evidence], provider: str, model: str) -> str:
    material = {
        "prompt": PROMPT_VERSION,
        "llm": f"{provider}:{model}",
        "release": report.release.id,
        "period": [report.period.start.isoformat(), report.period.end.isoformat()],
        "status": report.status.value,
        "evidence": [e.model_dump(mode="json") for e in evidence],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
