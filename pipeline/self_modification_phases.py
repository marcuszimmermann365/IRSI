"""
LRSI V11.5 — Self-Modification Boundary Phases
================================================

This module migrates the self-modification boundary from the legacy
``run_mutation_contract`` method into explicit, declarative phases:

* ``MutationPhase`` creates candidate prompt/policy mutations.
* ``PreProposalAdversarialPhase`` runs semantic drift + pre-proposal attacks.
* ``DGMPrecheckPhase`` wraps mutations in a ChangeProposal and gates entry into
  the governance pipeline.
* ``DGMPostcheckPhase`` makes the Pareto/DGM post-check an explicit audit phase
  after safety diagnostics and before the final gate.

The phases use explicit input dataclasses and immutable ``PhaseResult`` patches.
They preserve the V11.4 runtime semantics while making every self-modification
boundary step visible in ``phase_audit`` and final iteration records.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

from config import BASE_PROMPT
from invariants import (
    assert_dgm_precheck_respects_block,
    assert_mutation_blocked_has_terminal,
    assert_preproposal_not_red_and_accepted,
)
from pipeline.phase_runtime import ContextRegistry, PhaseResult
from pipeline.records import build_dgm_pre_reject_record, build_preproposal_reject_record


def _proposal_to_dict(proposal: Any) -> dict[str, Any] | Any:
    return proposal.to_dict() if hasattr(proposal, "to_dict") else proposal


@dataclass(frozen=True)
class MutationBoundaryOutput:
    prompt_meta: dict[str, Any]
    policy_meta: dict[str, Any]
    prompt_diff: dict[str, Any]
    policy_diff: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationPhaseInput:
    iteration: int
    agent: Any
    mutation_stage: Any
    allow_policy_change: bool
    previous_policy: dict[str, Any]


class MutationPhase:
    """Create the candidate mutation as an explicit self-modification phase."""

    name = "mutation_phase"
    input_type: ClassVar[type] = MutationPhaseInput
    required_keys: ClassVar[tuple[str, ...]] = (
        "iteration",
        "agent",
        "mutation_stage",
        "allow_policy_change",
        "previous_policy",
    )

    def build_input(self, registry: ContextRegistry) -> MutationPhaseInput:
        values = registry.require(self.required_keys)
        return MutationPhaseInput(**values)

    @staticmethod
    def evaluate(phase_input: MutationPhaseInput) -> MutationBoundaryOutput:
        mutation = phase_input.mutation_stage.run(
            agent=phase_input.agent,
            iteration=phase_input.iteration,
            allow_policy_change=phase_input.allow_policy_change,
            previous_policy=phase_input.previous_policy,
        )
        prompt_meta = dict(mutation.prompt_meta)
        policy_meta = dict(mutation.policy_meta)
        prompt_diff = {
            "original_prompt": prompt_meta.get("original_prompt"),
            "new_prompt": prompt_meta.get("new_prompt"),
            "changed": prompt_meta.get("original_prompt") != prompt_meta.get("new_prompt"),
        }
        policy_diff = {
            "description": policy_meta.get("description"),
            "section": policy_meta.get("section"),
            "changed_sections": list(policy_meta.get("changed_sections") or []),
            "policy_changed": policy_meta.get("old_policy") != policy_meta.get("new_policy"),
        }
        return MutationBoundaryOutput(
            prompt_meta=prompt_meta,
            policy_meta=policy_meta,
            prompt_diff=prompt_diff,
            policy_diff=policy_diff,
        )

    def run(self, phase_input: MutationPhaseInput | None = None, **kwargs: Any) -> PhaseResult | MutationBoundaryOutput:
        if phase_input is None:
            phase_input = MutationPhaseInput(**kwargs)
            return self.evaluate(phase_input)
        out = self.evaluate(phase_input)
        return PhaseResult(
            phase=self.name,
            decision="PROPOSED",
            reason=out.policy_meta.get("description") or "prompt_mutation",
            diagnostics={
                "prompt_diff": out.prompt_diff,
                "policy_diff": out.policy_diff,
            },
            patch={
                "prompt_meta": out.prompt_meta,
                "policy_meta": out.policy_meta,
                "selfmod_mutation_v11_5": out.to_dict(),
            },
            trace_entries=(
                {
                    "stage": "mutation",
                    "decision": "PROPOSED",
                    "reason": out.policy_meta.get("description") or "prompt_mutation",
                },
            ),
        )


@dataclass(frozen=True)
class PreProposalAdversarialOutput:
    semantic_drift: dict[str, Any]
    preproposal_adversarial: dict[str, Any]
    prompt_meta: dict[str, Any]
    max_severity: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_drift": self.semantic_drift,
            "preproposal_adversarial": self.preproposal_adversarial,
            "max_severity": self.max_severity,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PreProposalAdversarialPhaseInput:
    prompt_meta: dict[str, Any]
    policy_meta: dict[str, Any]
    semantic_drift_monitor: Any
    preproposal_adversarial_orchestrator: Any
    baseline_prompt: str = BASE_PROMPT
    iteration: int | None = None
    governance_mode: str = "unknown"
    parent_metrics: dict[str, Any] | None = None
    baseline_metrics: dict[str, Any] | None = None
    previous_policy: dict[str, Any] | None = None
    audit_recorder: Any | None = None
    storage: Any | None = None
    persistence_stage: Any | None = None
    history: list[dict[str, Any]] | None = None
    phase_audit: list[dict[str, Any]] | None = None
    trace_id: str | None = None


class PreProposalAdversarialPhase:
    """Run pre-DGM semantic drift and mutation attack checks."""

    name = "preproposal_adversarial_phase"
    input_type: ClassVar[type] = PreProposalAdversarialPhaseInput
    required_keys: ClassVar[tuple[str, ...]] = (
        "prompt_meta",
        "policy_meta",
        "semantic_drift_monitor",
        "preproposal_adversarial_orchestrator",
        "baseline_prompt",
    )

    def build_input(self, registry: ContextRegistry) -> PreProposalAdversarialPhaseInput:
        values = registry.require(self.required_keys)
        values.update(
            {
                "iteration": registry.get("iteration"),
                "governance_mode": registry.get("governance_mode", "unknown"),
                "parent_metrics": registry.get("parent_metrics", {}),
                "baseline_metrics": registry.get("baseline_metrics", {}),
                "previous_policy": registry.get("previous_policy", {}),
                "audit_recorder": registry.get("audit_recorder"),
                "storage": registry.get("storage"),
                "persistence_stage": registry.get("persistence_stage"),
                "history": registry.get("history", []),
                "phase_audit": registry.get("phase_audit", []),
                "trace_id": registry.get("trace_id"),
            }
        )
        return PreProposalAdversarialPhaseInput(**values)

    @staticmethod
    def evaluate(phase_input: PreProposalAdversarialPhaseInput) -> PreProposalAdversarialOutput:
        prompt_meta = dict(phase_input.prompt_meta)
        semantic_drift = phase_input.semantic_drift_monitor.compare(
            phase_input.baseline_prompt,
            prompt_meta.get("new_prompt", ""),
        ).to_dict()
        preproposal = phase_input.preproposal_adversarial_orchestrator.attack(
            prompt_meta=prompt_meta,
            policy_meta=phase_input.policy_meta,
        )
        prompt_meta["semantic_drift"] = semantic_drift
        prompt_meta["preproposal_adversarial"] = preproposal
        blockers: list[str] = []
        warnings: list[str] = []
        if semantic_drift.get("decision") == "RED":
            blockers.append("semantic_drift_red")
        elif semantic_drift.get("decision") == "YELLOW":
            warnings.append("semantic_drift_yellow")
        if preproposal.get("max_severity") == "red":
            blockers.append("preproposal_attack_red")
        elif preproposal.get("max_severity") == "yellow":
            warnings.append("preproposal_attack_yellow")
        return PreProposalAdversarialOutput(
            semantic_drift=semantic_drift,
            preproposal_adversarial=preproposal,
            prompt_meta=prompt_meta,
            max_severity=preproposal.get("max_severity", "green"),
            blockers=tuple(blockers),
            warnings=tuple(warnings),
        )

    def run(self, phase_input: PreProposalAdversarialPhaseInput | None = None, **kwargs: Any) -> PhaseResult | PreProposalAdversarialOutput:
        if phase_input is None:
            phase_input = PreProposalAdversarialPhaseInput(**kwargs)
            return self.evaluate(phase_input)

        out = self.evaluate(phase_input)
        decision = "RED" if out.blockers else "YELLOW" if out.warnings else "GREEN"
        reason = ",".join(out.blockers or out.warnings or ("preproposal_clear",))
        terminal = decision == "RED"
        block_reason = reason if terminal else ""

        patch: dict[str, Any] = {
            "semantic_drift": out.semantic_drift,
            "preproposal_adversarial": out.preproposal_adversarial,
            "prompt_meta": out.prompt_meta,
            "selfmod_preproposal_v11_5": out.to_dict(),
            "mutation_blocked": terminal,
            "block_reason": block_reason,
        }
        trace_entries = (
            {
                "stage": "semantic_drift",
                "decision": out.semantic_drift.get("decision", "UNKNOWN"),
                "reason": f"distance={out.semantic_drift.get('distance', 0.0):.3f}",
                "mutation_blocked": terminal and out.semantic_drift.get("decision") == "RED",
            },
            {
                "stage": "preproposal_adversarial",
                "decision": decision,
                "reason": reason,
                "blockers": list(out.blockers),
                "warnings": list(out.warnings),
                "max_severity": out.max_severity,
                "mutation_blocked": terminal,
            },
            {
                "stage": "preproposal_kill_switch",
                "decision": "REJECT" if terminal else "PASS",
                "reason": block_reason or "no_preproposal_block",
                "terminal": terminal,
                "mutation_blocked": terminal,
            },
        )
        result = PhaseResult(
            phase=self.name,
            decision=decision,
            reason=reason,
            diagnostics=out.to_dict(),
            patch=patch,
            trace_entries=trace_entries,
            terminal=terminal,
        )

        assert_preproposal_not_red_and_accepted(result, accepted=False)
        assert_mutation_blocked_has_terminal(result)

        if (
            terminal
            and phase_input.audit_recorder is not None
            and phase_input.storage is not None
            and phase_input.persistence_stage is not None
            and phase_input.iteration is not None
        ):
            record = build_preproposal_reject_record(
                iteration=phase_input.iteration,
                mode=phase_input.governance_mode,
                parent_metrics=phase_input.parent_metrics or {},
                baseline_metrics=phase_input.baseline_metrics or {},
                previous_policy=phase_input.previous_policy or {},
                candidate_policy=phase_input.policy_meta.get("new_policy"),
                block_reason=block_reason,
                semantic_drift=out.semantic_drift,
                preproposal_adversarial=out.preproposal_adversarial,
                trace_id=phase_input.trace_id,
            )
            record["phase_audit"] = list(phase_input.phase_audit or []) + [
                result.audit_entry(iteration=phase_input.iteration)
            ]
            persisted = phase_input.audit_recorder.persist(
                storage=phase_input.storage,
                persistence_stage=phase_input.persistence_stage,
                record=record,
                history=phase_input.history if phase_input.history is not None else [],
            ).record
            patch["record"] = persisted

        return result


@dataclass(frozen=True)
class DGMPrecheckOutputV115:
    proposal: Any
    allowed: bool
    reason: str
    requirements: dict[str, Any]
    trace_entry: dict[str, Any]
    candidate: Any | None = None
    child_metrics: dict[str, Any] | None = None
    reject_record: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal": _proposal_to_dict(self.proposal),
            "allowed": self.allowed,
            "reason": self.reason,
            "requirements": self.requirements,
            "trace_entry": self.trace_entry,
            "candidate_created": self.candidate is not None,
            "child_metrics_present": self.child_metrics is not None,
            "persisted_reject_record_hash": (
                self.reject_record or {}
            ).get("record_hash"),
        }


@dataclass(frozen=True)
class DGMPrecheckPhaseInput:
    iteration: int
    dgm_pre_stage: Any
    dgm_bridge: Any
    prompt_meta: dict[str, Any]
    policy_meta: dict[str, Any]
    agent: Any
    memory: Any
    evaluation_stage: Any
    build_agent_fn: Any
    previous_policy: dict[str, Any]
    parent_metrics: dict[str, Any]
    baseline_metrics: dict[str, Any]
    governance_mode: str
    effective_attractor_state: Any
    baseline_attractor_state: Any
    audit_recorder: Any
    storage: Any
    persistence_stage: Any
    history: list[dict[str, Any]]
    phase_audit: list[dict[str, Any]]
    mutation_blocked: bool = False
    block_reason: str = ""


class DGMPrecheckPhase:
    """Explicit DGM pre-check boundary before governance evaluation."""

    name = "dgm_precheck_phase"
    input_type: ClassVar[type] = DGMPrecheckPhaseInput
    required_keys: ClassVar[tuple[str, ...]] = (
        "iteration", "dgm_pre_stage", "dgm_bridge", "prompt_meta", "policy_meta",
        "agent", "memory", "evaluation_stage", "build_agent_fn", "previous_policy",
        "parent_metrics", "baseline_metrics", "governance_mode", "effective_attractor_state",
        "baseline_attractor_state", "audit_recorder", "storage", "persistence_stage", "history", "phase_audit",
    )

    def build_input(self, registry: ContextRegistry) -> DGMPrecheckPhaseInput:
        values = registry.require(self.required_keys)
        values["mutation_blocked"] = bool(registry.get("mutation_blocked", False))
        values["block_reason"] = registry.get("block_reason", "")
        return DGMPrecheckPhaseInput(**values)

    @staticmethod
    def evaluate(phase_input: DGMPrecheckPhaseInput) -> DGMPrecheckOutputV115:
        if phase_input.mutation_blocked:
            reason = phase_input.block_reason or "preproposal_mutation_blocked"
            gating_anchor = (
                phase_input.effective_attractor_state
                if phase_input.effective_attractor_state is not None
                else phase_input.baseline_attractor_state
            )
            gating_anchor_source = (
                "effective" if phase_input.effective_attractor_state is not None
                else "baseline" if phase_input.baseline_attractor_state is not None
                else "none"
            )
            proposal = {
                "change_id": f"preproposal-blocked-{phase_input.iteration}",
                "blocked_by": "preproposal_adversarial_phase",
                "reason": reason,
            }
            requirements = {
                "mutation_blocked": True,
                "blocked_by": "preproposal_adversarial_phase",
                "block_reason": reason,
            }
            record = build_dgm_pre_reject_record(
                iteration=phase_input.iteration,
                mode=phase_input.governance_mode,
                parent_metrics=phase_input.parent_metrics,
                baseline_metrics=phase_input.baseline_metrics,
                previous_policy=phase_input.previous_policy,
                candidate_policy=phase_input.policy_meta.get("new_policy"),
                proposal=proposal,
                dgm_reason=f"mutation_blocked:{reason}",
                dgm_requirements=requirements,
                gating_anchor_source=gating_anchor_source,
                gating_anchor=gating_anchor,
            )
            return DGMPrecheckOutputV115(
                proposal=proposal,
                allowed=False,
                reason=f"mutation_blocked:{reason}",
                requirements=requirements,
                trace_entry={
                    "stage": "dgm_precheck_block_guard",
                    "decision": "REJECT",
                    "reason": reason,
                    "mutation_blocked": True,
                    "terminal": True,
                },
                reject_record=record,
            )

        dgm_pre = phase_input.dgm_pre_stage.run(
            bridge=phase_input.dgm_bridge,
            prompt_meta=phase_input.prompt_meta,
            policy_meta=phase_input.policy_meta,
            iteration=phase_input.iteration,
        )
        trace_entry = dgm_pre.trace.trace_entry()
        if not dgm_pre.allowed:
            gating_anchor = (
                phase_input.effective_attractor_state
                if phase_input.effective_attractor_state is not None
                else phase_input.baseline_attractor_state
            )
            gating_anchor_source = (
                "effective" if phase_input.effective_attractor_state is not None
                else "baseline" if phase_input.baseline_attractor_state is not None
                else "none"
            )
            record = build_dgm_pre_reject_record(
                iteration=phase_input.iteration,
                mode=phase_input.governance_mode,
                parent_metrics=phase_input.parent_metrics,
                baseline_metrics=phase_input.baseline_metrics,
                previous_policy=phase_input.previous_policy,
                candidate_policy=phase_input.policy_meta.get("new_policy"),
                proposal=dgm_pre.proposal,
                dgm_reason=dgm_pre.reason,
                dgm_requirements=dgm_pre.requirements,
                gating_anchor_source=gating_anchor_source,
                gating_anchor=gating_anchor,
            )
            return DGMPrecheckOutputV115(
                proposal=dgm_pre.proposal,
                allowed=False,
                reason=dgm_pre.reason,
                requirements=dgm_pre.requirements,
                trace_entry=trace_entry,
                reject_record=record,
            )

        candidate = phase_input.build_agent_fn(
            phase_input.prompt_meta["new_prompt"],
            phase_input.memory,
            phase_input.policy_meta["new_policy"],
            llm_client=phase_input.agent.llm,
        )
        child_metrics = phase_input.evaluation_stage.run(agent=candidate).metrics
        return DGMPrecheckOutputV115(
            proposal=dgm_pre.proposal,
            allowed=True,
            reason=dgm_pre.reason,
            requirements=dgm_pre.requirements,
            trace_entry=trace_entry,
            candidate=candidate,
            child_metrics=child_metrics,
        )

    def run(self, phase_input: DGMPrecheckPhaseInput | None = None, **kwargs: Any) -> PhaseResult | DGMPrecheckOutputV115:
        if phase_input is None:
            phase_input = DGMPrecheckPhaseInput(**kwargs)
            return self.evaluate(phase_input)
        out = self.evaluate(phase_input)
        patch = {
            "dgm_pre": out,
            "dgm_proposal": out.proposal,
            "dgm_allowed": out.allowed,
            "dgm_reason": out.reason,
            "dgm_reqs": out.requirements,
            "selfmod_dgm_precheck_v11_5": out.to_dict(),
        }
        result = PhaseResult(
            phase=self.name,
            decision="PASS" if out.allowed else "REJECT",
            reason=out.reason,
            diagnostics=out.to_dict(),
            patch=patch,
            trace_entries=(out.trace_entry,),
            terminal=not out.allowed,
        )
        assert_dgm_precheck_respects_block(
            {"mutation_blocked": phase_input.mutation_blocked},
            result,
        )

        if out.allowed:
            patch.update({"candidate": out.candidate, "child_metrics": out.child_metrics or {}})
            return result

        reject_record = dict(out.reject_record or {})
        reject_record["phase_audit"] = list(phase_input.phase_audit) + [
            result.audit_entry(iteration=phase_input.iteration)
        ]
        persisted = phase_input.audit_recorder.persist(
            storage=phase_input.storage,
            persistence_stage=phase_input.persistence_stage,
            record=reject_record,
            history=phase_input.history,
        ).record
        patch.update({"record": persisted})
        return result


@dataclass(frozen=True)
class DGMPostcheckOutputV115:
    admissible: bool
    quality: dict[str, Any]
    diagnostics: dict[str, Any]
    drel_status: str
    a3_status: str
    a4_max: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DGMPostcheckPhaseInput:
    dgm_bridge: Any
    curr_state: Any
    prev_attractor_state: Any
    dgm_proposal: Any
    drel_status: str
    ss_risk: float
    a4_max: float


class DGMPostcheckPhase:
    """Authoritative DGM post-check audit seam after safety diagnostics."""

    name = "dgm_postcheck_phase"
    input_type: ClassVar[type] = DGMPostcheckPhaseInput
    required_keys: ClassVar[tuple[str, ...]] = (
        "dgm_bridge", "curr_state", "prev_attractor_state", "dgm_proposal",
        "drel_status", "ss_risk", "a4_max",
    )

    def build_input(self, registry: ContextRegistry) -> DGMPostcheckPhaseInput:
        values = registry.require(self.required_keys)
        return DGMPostcheckPhaseInput(**values)

    @staticmethod
    def evaluate(phase_input: DGMPostcheckPhaseInput) -> DGMPostcheckOutputV115:
        a3_status = "RED" if phase_input.ss_risk >= 0.65 else "GREEN"
        admissible, quality, diagnostics = phase_input.dgm_bridge.post_check(
            phase_input.curr_state,
            phase_input.prev_attractor_state or phase_input.curr_state,
            phase_input.dgm_proposal,
            drel_status=phase_input.drel_status,
            a3_status=a3_status,
            a4_max=phase_input.a4_max,
        )
        return DGMPostcheckOutputV115(
            admissible=admissible,
            quality=quality,
            diagnostics=diagnostics,
            drel_status=phase_input.drel_status,
            a3_status=a3_status,
            a4_max=phase_input.a4_max,
        )

    def run(self, phase_input: DGMPostcheckPhaseInput | None = None, **kwargs: Any) -> PhaseResult | DGMPostcheckOutputV115:
        if phase_input is None:
            phase_input = DGMPostcheckPhaseInput(**kwargs)
            return self.evaluate(phase_input)
        out = self.evaluate(phase_input)
        decision = "GREEN" if out.admissible else "RED"
        reason = "pareto_eligible" if out.admissible else f"pareto_inadmissible:{out.diagnostics.get('violations', [])}"
        return PhaseResult(
            phase=self.name,
            decision=decision,
            reason=reason,
            diagnostics=out.to_dict(),
            patch={
                "dgm_admissible": out.admissible,
                "dgm_quality": out.quality,
                "dgm_post_diag": out.diagnostics,
                "selfmod_dgm_postcheck_v11_5": out.to_dict(),
            },
            trace_entries=(
                {"stage": "dgm_postcheck", "decision": decision, "reason": reason},
            ),
        )
