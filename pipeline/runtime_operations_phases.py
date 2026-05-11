"""
LRSI V11.6 — Runtime Operations Phases
=======================================

This module migrates the operational runtime seams into the declarative phase
model introduced in V11.2:

* EvaluationPhase makes LLM/runtime evaluation explicit and auditable.
* MemoryConsolidationPhase moves post-decision memory writes out of the
  candidate-application method and into a typed phase.
* ObservabilityPhase emits structured trace/metric events and propagates a
  trace id through the phase/audit chain.

The classes intentionally do not introduce new safety heuristics. They package
existing runtime operations into immutable PhaseResult objects with explicit
inputs and audit entries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from pipeline.phase_runtime import ContextRegistry, PhaseResult
from version import SCHEMA_VERSION


@dataclass(frozen=True)
class EvaluationPhaseInput:
    iteration: int
    trace_id: str
    evaluation_stage: Any
    candidate: Any | None
    child_metrics: dict[str, Any] | None
    parent_metrics: dict[str, Any]
    mode: str | None = None


@dataclass(frozen=True)
class EvaluationPhaseOutput:
    parent_metrics: dict[str, Any]
    child_metrics: dict[str, Any]
    mode: str | None
    llm_error_count: int
    llm_error_rate: float
    fixture_miss_count: int
    fixture_miss_rate: float
    output_count: int
    reused_existing_child_metrics: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvaluationPhase:
    """Expose candidate evaluation as an operational declarative phase.

    DGMPrecheckPhase still owns candidate construction and may already have run
    the evaluator for historical compatibility. This phase is the authoritative
    runtime seam: it reuses existing child metrics when present and otherwise
    invokes the evaluator. Either way, LLM/fixture failure metrics become an
    explicit phase output and audit entry.
    """

    name = "evaluation_phase"
    input_type: ClassVar[type] = EvaluationPhaseInput
    required_keys: ClassVar[tuple[str, ...]] = (
        "iteration",
        "trace_id",
        "evaluation_stage",
        "candidate",
        "child_metrics",
        "parent_metrics",
    )

    def build_input(self, registry: ContextRegistry) -> EvaluationPhaseInput:
        values = registry.require(self.required_keys)
        return EvaluationPhaseInput(**values)

    @staticmethod
    def evaluate(phase_input: EvaluationPhaseInput) -> EvaluationPhaseOutput:
        reused = bool(phase_input.child_metrics)
        child_metrics = dict(phase_input.child_metrics or {})
        if not child_metrics and phase_input.candidate is not None:
            child_metrics = phase_input.evaluation_stage.run(
                agent=phase_input.candidate,
                mode=phase_input.mode,
            ).metrics
        outputs = child_metrics.get("outputs", []) or []
        llm_error_count = int(child_metrics.get(
            "llm_error_count", sum(1 for o in outputs if o.get("llm_error"))
        ))
        fixture_miss_count = int(child_metrics.get(
            "fixture_miss_count", sum(1 for o in outputs if o.get("fixture_miss"))
        ))
        output_count = len(outputs)
        llm_error_rate = float(child_metrics.get(
            "llm_error_rate", llm_error_count / output_count if output_count else 0.0
        ))
        fixture_miss_rate = float(child_metrics.get(
            "fixture_miss_rate", fixture_miss_count / output_count if output_count else 0.0
        ))
        child_metrics.setdefault("llm_error_count", llm_error_count)
        child_metrics.setdefault("llm_error_rate", llm_error_rate)
        child_metrics.setdefault("fixture_miss_count", fixture_miss_count)
        child_metrics.setdefault("fixture_miss_rate", fixture_miss_rate)
        return EvaluationPhaseOutput(
            parent_metrics=dict(phase_input.parent_metrics),
            child_metrics=child_metrics,
            mode=phase_input.mode,
            llm_error_count=llm_error_count,
            llm_error_rate=llm_error_rate,
            fixture_miss_count=fixture_miss_count,
            fixture_miss_rate=fixture_miss_rate,
            output_count=output_count,
            reused_existing_child_metrics=reused,
        )

    def run(self, phase_input: EvaluationPhaseInput | None = None, **kwargs: Any) -> PhaseResult | EvaluationPhaseOutput:
        if phase_input is None:
            phase_input = EvaluationPhaseInput(**kwargs)
            return self.evaluate(phase_input)
        out = self.evaluate(phase_input)
        decision = "RED" if out.llm_error_rate >= 1.0 and out.output_count else "GREEN"
        reason = (
            f"llm_error_rate={out.llm_error_rate:.3f};"
            f"fixture_miss_rate={out.fixture_miss_rate:.3f};"
            f"reused={out.reused_existing_child_metrics}"
        )
        return PhaseResult(
            phase=self.name,
            decision=decision,
            reason=reason,
            diagnostics={"trace_id": phase_input.trace_id, **out.to_dict()},
            patch={
                "child_metrics": out.child_metrics,
                "evaluation_diagnostics_v11_6": out.to_dict(),
            },
            trace_entries=(
                {
                    "trace_id": phase_input.trace_id,
                    "stage": "evaluation",
                    "decision": decision,
                    "reason": reason,
                },
            ),
        )


@dataclass(frozen=True)
class MemoryConsolidationPhaseInput:
    iteration: int
    trace_id: str
    accepted: bool
    mode_adjustments: dict[str, Any]
    prompt_meta: dict[str, Any]
    policy_meta: dict[str, Any]
    child_metrics: dict[str, Any]
    memory: Any
    memory_gate: Any
    role_memory: Any
    extract_fn: Any


@dataclass(frozen=True)
class MemoryConsolidationPhaseOutput:
    memory_events: list[dict[str, Any]]
    memory_changed: bool
    extracted_count: int
    consolidated_count: int
    review_count: int
    rejected_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryConsolidationPhase:
    """Post-final-gate memory consolidation with explicit input/result shape."""

    name = "memory_consolidation_phase"
    input_type: ClassVar[type] = MemoryConsolidationPhaseInput
    required_keys: ClassVar[tuple[str, ...]] = (
        "iteration",
        "trace_id",
        "accepted",
        "mode_adj",
        "prompt_meta",
        "policy_meta",
        "child_metrics",
        "memory",
        "memory_gate",
        "role_memory",
        "extract_candidate_memory_fn",
    )

    def build_input(self, registry: ContextRegistry) -> MemoryConsolidationPhaseInput:
        values = registry.require(self.required_keys)
        return MemoryConsolidationPhaseInput(
            iteration=values["iteration"],
            trace_id=values["trace_id"],
            accepted=values["accepted"],
            mode_adjustments=values["mode_adj"],
            prompt_meta=values["prompt_meta"],
            policy_meta=values["policy_meta"],
            child_metrics=values["child_metrics"],
            memory=values["memory"],
            memory_gate=values["memory_gate"],
            role_memory=values["role_memory"],
            extract_fn=values["extract_candidate_memory_fn"],
        )

    @staticmethod
    def evaluate(phase_input: MemoryConsolidationPhaseInput) -> tuple[MemoryConsolidationPhaseOutput, Any]:
        events: list[dict[str, Any]] = []
        extracted_count = 0
        if phase_input.mode_adjustments.get("allow_memory_consolidation") and phase_input.accepted:
            extracted = phase_input.extract_fn(
                {"prompt_meta": phase_input.prompt_meta, "policy_meta": phase_input.policy_meta},
                phase_input.child_metrics,
            )
            extracted_count = len(extracted)
            for mem in extracted:
                phase_input.memory.auto_challenge_contradictions(mem["content"], mem["kind"])
                existing = phase_input.memory.reinforce_candidate(mem["content"])
                if existing is None:
                    ce = phase_input.memory.add_candidate(
                        content=mem["content"],
                        source=mem["source"],
                        kind=mem["kind"],
                        metadata=mem["metadata"],
                    )
                else:
                    ce = existing
                md, mr, mdiag = phase_input.memory_gate.check(ce, phase_input.memory.data["consolidated"])
                event = {"candidate_memory": ce, "decision": md, "reason": mr, "diagnostics": mdiag}
                if md == "GREEN":
                    if not phase_input.memory.is_already_consolidated(ce["content"]):
                        event["consolidated"] = phase_input.memory.add_consolidated(
                            ce, {"decision": md, "reason": mr, "diagnostics": mdiag}
                        )
                    phase_input.memory.mark_candidate_status(ce["id"], "consolidated")
                elif md == "YELLOW":
                    phase_input.memory.mark_candidate_status(ce["id"], "review")
                    phase_input.memory.increment_review_count(ce["id"])
                else:
                    phase_input.memory.mark_candidate_status(ce["id"], "rejected")
                events.append(event)
        consolidated_count = sum(1 for e in events if e.get("decision") == "GREEN")
        review_count = sum(1 for e in events if e.get("decision") == "YELLOW")
        rejected_count = sum(1 for e in events if e.get("decision") == "RED")
        out = MemoryConsolidationPhaseOutput(
            memory_events=events,
            memory_changed=bool(consolidated_count),
            extracted_count=extracted_count,
            consolidated_count=consolidated_count,
            review_count=review_count,
            rejected_count=rejected_count,
        )
        verdict = phase_input.role_memory.evaluate(events)
        return out, verdict

    def run(self, phase_input: MemoryConsolidationPhaseInput | None = None, **kwargs: Any) -> PhaseResult | MemoryConsolidationPhaseOutput:
        if phase_input is None:
            phase_input = MemoryConsolidationPhaseInput(**kwargs)
            return self.evaluate(phase_input)[0]
        out, verdict = self.evaluate(phase_input)
        decision = "GREEN" if not out.rejected_count else "YELLOW"
        reason = (
            f"extracted={out.extracted_count};consolidated={out.consolidated_count};"
            f"review={out.review_count};rejected={out.rejected_count}"
        )
        return PhaseResult(
            phase=self.name,
            decision=decision,
            reason=reason,
            diagnostics={"trace_id": phase_input.trace_id, **out.to_dict()},
            patch={
                "memory_events": out.memory_events,
                "memory_diagnostics_v11_6": out.to_dict(),
                "verdicts": ("__append__", [verdict]),
            },
            trace_entries=(
                {
                    "trace_id": phase_input.trace_id,
                    "stage": "memory_consolidation",
                    "decision": decision,
                    "reason": reason,
                },
            ),
        )


@dataclass(frozen=True)
class ObservabilityPhaseInput:
    iteration: int
    trace_id: str
    final_decision: str
    accepted: bool
    phase_audit: list[dict[str, Any]]
    decision_trace: list[dict[str, Any]]
    evaluation_diagnostics: dict[str, Any]
    memory_diagnostics: dict[str, Any]
    logger: Any


@dataclass(frozen=True)
class ObservabilityPhaseOutput:
    trace_id: str
    spans: tuple[dict[str, Any], ...]
    metrics: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "spans": [dict(s) for s in self.spans],
            "metrics": [dict(m) for m in self.metrics],
            "events": [dict(e) for e in self.events],
        }


class ObservabilityPhase:
    """Emit structured operational events without changing business decisions."""

    name = "observability_phase"
    input_type: ClassVar[type] = ObservabilityPhaseInput
    required_keys: ClassVar[tuple[str, ...]] = (
        "iteration",
        "trace_id",
        "final_decision",
        "accepted",
        "phase_audit",
        "decision_trace",
        "evaluation_diagnostics_v11_6",
        "memory_diagnostics_v11_6",
        "logger",
    )

    def build_input(self, registry: ContextRegistry) -> ObservabilityPhaseInput:
        values = registry.require(self.required_keys)
        return ObservabilityPhaseInput(
            iteration=values["iteration"],
            trace_id=values["trace_id"],
            final_decision=values["final_decision"],
            accepted=values["accepted"],
            phase_audit=values["phase_audit"],
            decision_trace=values["decision_trace"],
            evaluation_diagnostics=values["evaluation_diagnostics_v11_6"],
            memory_diagnostics=values["memory_diagnostics_v11_6"],
            logger=values["logger"],
        )

    @staticmethod
    def evaluate(phase_input: ObservabilityPhaseInput) -> ObservabilityPhaseOutput:
        spans = tuple(
            {
                "trace_id": phase_input.trace_id,
                "span_id": f"{phase_input.trace_id}:{idx}",
                "phase": entry.get("phase"),
                "decision": entry.get("decision"),
                "terminal": bool(entry.get("terminal")),
            }
            for idx, entry in enumerate(phase_input.phase_audit)
        )
        metrics = (
            {
                "trace_id": phase_input.trace_id,
                "name": "llm_error_rate",
                "value": float(phase_input.evaluation_diagnostics.get("llm_error_rate", 0.0)),
            },
            {
                "trace_id": phase_input.trace_id,
                "name": "fixture_miss_rate",
                "value": float(phase_input.evaluation_diagnostics.get("fixture_miss_rate", 0.0)),
            },
            {
                "trace_id": phase_input.trace_id,
                "name": "memory_consolidated_count",
                "value": int(phase_input.memory_diagnostics.get("consolidated_count", 0)),
            },
        )
        events = (
            {
                "schema_version": SCHEMA_VERSION,
                "event_type": "iteration_completed",
                "trace_id": phase_input.trace_id,
                "iteration": phase_input.iteration,
                "final_decision": phase_input.final_decision,
                "accepted": phase_input.accepted,
                "phase_count": len(phase_input.phase_audit),
                "decision_trace_count": len(phase_input.decision_trace),
            },
        )
        return ObservabilityPhaseOutput(
            trace_id=phase_input.trace_id,
            spans=spans,
            metrics=metrics,
            events=events,
        )

    def run(self, phase_input: ObservabilityPhaseInput | None = None, **kwargs: Any) -> PhaseResult | ObservabilityPhaseOutput:
        if phase_input is None:
            phase_input = ObservabilityPhaseInput(**kwargs)
            return self.evaluate(phase_input)
        out = self.evaluate(phase_input)
        for event in out.events:
            phase_input.logger.info("runtime_event=%s", event)
        return PhaseResult(
            phase=self.name,
            decision="EMITTED",
            reason="structured_runtime_events_emitted",
            diagnostics={"trace_id": phase_input.trace_id, "span_count": len(out.spans), "metric_count": len(out.metrics)},
            patch={
                "runtime_events_v11_6": [dict(e) for e in out.events],
                "observability_v11_6": out.to_dict(),
            },
            trace_entries=(
                {
                    "trace_id": phase_input.trace_id,
                    "stage": "observability",
                    "decision": "EMITTED",
                    "reason": f"spans={len(out.spans)} metrics={len(out.metrics)}",
                },
            ),
        )
