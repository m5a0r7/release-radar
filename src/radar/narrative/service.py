import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import Narrative
from radar.insights.evidence import Evidence, build_evidence
from radar.insights.schemas import DriftReport
from radar.narrative.budget import Fitted, estimate_tokens, fit_evidence, schema_tokens
from radar.narrative.confidence import ConfidenceCap, calibrate, data_support_cap
from radar.narrative.llm import LLMError, LLMResult, StructuredLLM
from radar.narrative.prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    TOOL_NAME,
    output_schema,
    repair_message,
    user_message,
)
from radar.narrative.quota import QuotaExceededError, UsageLedger
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


@dataclass(frozen=True, slots=True)
class NarrativeLimits:
    max_input_tokens: int = 12_000
    max_output_tokens: int = 2048
    max_concurrency: int = 4
    queue_timeout_seconds: float = 30.0


class NarrativeService:
    """Evidence -> LLM draft -> grounding verification -> calibrated, cached response.

    The LLM never sees raw upstream text (titles, descriptions), only computed evidence, which
    keeps the prompt-injection surface minimal. Any failure degrades to the template narrator.
    Prompts are trimmed to a token budget, calls are capped per process (`max_concurrency`) and
    metered per workspace (`ledger`), so ticket volume and traffic cannot run up the bill.
    """

    def __init__(
        self,
        llm: StructuredLLM | None,
        *,
        ledger: UsageLedger | None = None,
        limits: NarrativeLimits | None = None,
    ) -> None:
        self._llm = llm
        self._ledger = ledger
        self._limits = limits or NarrativeLimits()
        self._slots = asyncio.Semaphore(self._limits.max_concurrency)

    @property
    def _identity(self) -> tuple[str, str]:
        if self._llm is None:
            return "template", "template"
        return self._llm.provider, self._llm.model

    async def narrate(
        self,
        session: AsyncSession,
        report: DriftReport,
        *,
        workspace_id: int | None = None,
        refresh: bool = False,
    ) -> NarrativeResponse:
        """Raises `QuotaExceededError` when the workspace is out of LLM budget."""
        full = build_evidence(report)
        cap = data_support_cap(report)
        provider, model = self._identity
        fitted = self._fit(report, full)
        evidence = fitted.evidence if fitted else full
        notes = fitted.notes if fitted else []
        cache_key = _cache_key(report, evidence, provider, model)

        if not refresh:
            cached = await session.scalar(select(Narrative).where(Narrative.cache_key == cache_key))
            if cached is not None:
                response = NarrativeResponse.model_validate(cached.payload)
                response.meta.cached = True
                log.info(
                    "narrative_served",
                    provider=response.meta.provider,
                    model=response.meta.model,
                    cached=True,
                    degraded=response.meta.degraded,
                )
                return response

        if self._llm is not None and fitted is None:
            log.warning("narrative_over_budget", evidence=len(full))
            draft = template_draft(report, full)
            errors, degraded = ["evidence exceeds the LLM input budget"], True
        else:
            draft, errors, degraded = await self._draft(report, evidence, workspace_id)
        response = _assemble(report, evidence, draft, cap, provider, model, degraded, errors)
        response.caveats += [] if degraded else notes
        log.info(
            "narrative_served",
            provider=response.meta.provider,
            model=response.meta.model,
            cached=False,
            degraded=response.meta.degraded,
        )
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

    def _fit(self, report: DriftReport, evidence: list[Evidence]) -> Fitted | None:
        # A repair turn re-sends the prompt plus the previous answer (at most max_output_tokens).
        fixed = estimate_tokens(SYSTEM_PROMPT) + schema_tokens(output_schema()) + 300
        budget = self._limits.max_input_tokens - self._limits.max_output_tokens - fixed
        return fit_evidence(evidence, lambda ev: estimate_tokens(user_message(report, ev)), budget)

    async def _draft(
        self, report: DriftReport, evidence: list[Evidence], workspace_id: int | None
    ) -> tuple[NarrativeDraft, list[str], bool]:
        if self._llm is None:
            return template_draft(report, evidence), [], False

        allowed_keys = _allowed_keys(evidence)
        dates = [report.period.start.isoformat(), report.period.end.isoformat()]
        prompt = user_message(report, evidence)
        errors: list[str] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = await self._call(prompt, report, workspace_id, first=attempt == 1)
                draft = NarrativeDraft.model_validate(result.arguments)
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

    async def _call(
        self, prompt: str, report: DriftReport, workspace_id: int | None, *, first: bool
    ) -> LLMResult:
        llm, ledger = self._llm, self._ledger
        assert llm is not None
        try:
            async with asyncio.timeout(self._limits.queue_timeout_seconds):
                await self._slots.acquire()
        except TimeoutError as exc:
            raise LLMError("LLM is at capacity") from exc
        try:
            if ledger is None or workspace_id is None:
                return await llm.generate(SYSTEM_PROMPT, prompt, TOOL_NAME, output_schema())
            try:
                call_id = await ledger.reserve(workspace_id, report.release.id, llm.model)
            except QuotaExceededError as exc:
                if first:
                    raise
                raise LLMError(f"repair skipped: {exc}") from exc
            try:
                result = await llm.generate(SYSTEM_PROMPT, prompt, TOOL_NAME, output_schema())
            except LLMError as exc:
                await ledger.complete(call_id, "error", exc.input_tokens, exc.output_tokens)
                raise
            await ledger.complete(call_id, "ok", result.input_tokens, result.output_tokens)
            return result
        finally:
            self._slots.release()


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
