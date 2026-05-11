"""
LRSI v10.3-v10.5 stage seams.

V10.5 keeps the proven execution semantics intact while tightening phase and
audit contracts. The stages are small contracts, not a rewrite of the safety
model: their purpose is to reduce monolithic drift while preserving invariant
behavior.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from attractor_engine import compute_attractor, extended_decide
from eval import evaluate
from meta import mutate_policy, mutate_prompt
from pipeline_contracts import DGMRequirements, StageResult


@dataclass
class GovernanceStageOutput:
    system_state: dict
    proposed_mode: str
    transition_reason: str
    mode_transitioned: bool
    mode_adjustments: dict
    adjusted_thresholds: dict
    current_mode: str
    iterations_in_mode: int


class GovernanceStage:
    """Compute governance mode and threshold adjustments."""

    name = "governance"

    def run(self, *, governance, erosion_detector, path_model,
            recent_reds: int, recent_yellows: int,
            iterations_in_mode: int) -> GovernanceStageOutput:
        system_state = {
            "recent_red_count": recent_reds,
            "recent_yellow_count": recent_yellows,
            "erosion_status": erosion_detector.check()[0],
            "path_status": path_model.assess()[0],
            "iterations_in_mode": iterations_in_mode,
        }
        proposed_mode, transition_reason = governance.propose_transition(system_state)
        mode_transitioned = proposed_mode != governance.current_mode()
        if mode_transitioned:
            governance.apply_transition(proposed_mode, transition_reason)
            iterations_in_mode = 0
        else:
            iterations_in_mode += 1

        return GovernanceStageOutput(
            system_state=system_state,
            proposed_mode=proposed_mode,
            transition_reason=transition_reason,
            mode_transitioned=mode_transitioned,
            mode_adjustments=governance.mode_adjustments(),
            adjusted_thresholds=governance.adjust_thresholds(),
            current_mode=governance.current_mode(),
            iterations_in_mode=iterations_in_mode,
        )


@dataclass
class EvaluationStageOutput:
    metrics: dict
    mode: str | None


class EvaluationStage:
    """Run the evaluator behind an explicit stage boundary."""

    name = "evaluation"

    def run(self, *, agent, mode: str | None = None) -> EvaluationStageOutput:
        metrics = evaluate(agent, mode=mode) if mode else evaluate(agent)
        return EvaluationStageOutput(metrics=metrics, mode=mode)


@dataclass
class MutationStageOutput:
    prompt_meta: dict
    policy_meta: dict


class MutationStage:
    """Create candidate prompt/policy mutations with explicit contracts."""

    name = "mutation"

    def run(self, *, agent, iteration: int, allow_policy_change: bool,
            previous_policy: dict) -> MutationStageOutput:
        prompt_meta = mutate_prompt(agent.prompt, iteration)
        policy_meta = mutate_policy(agent.policy, iteration)
        if not allow_policy_change:
            policy_meta = {
                "schema_version": prompt_meta.get("schema_version", "10.2"),
                "mutation_type": "policy",
                "description": "suppressed_by_mode",
                "section": None,
                "changed_sections": [],
                "old_policy": deepcopy(previous_policy),
                "new_policy": deepcopy(agent.policy),
            }
        return MutationStageOutput(prompt_meta=prompt_meta, policy_meta=policy_meta)


@dataclass
class DGMPrecheckOutput:
    proposal: Any
    allowed: bool
    reason: str
    requirements: dict
    trace: StageResult


class DGMPrecheckStage:
    """Wrap mutation and apply DGM scope/safety pre-check."""

    name = "dgm_pre"

    def run(self, *, bridge, prompt_meta: dict, policy_meta: dict,
            iteration: int) -> DGMPrecheckOutput:
        proposal = bridge.wrap_mutation(prompt_meta, policy_meta, iteration)
        allowed, reason, requirements = bridge.pre_check(proposal)
        trace = StageResult(
            stage=self.name,
            decision="PASS" if allowed else "REJECT",
            reason=reason,
            requirements=DGMRequirements.from_dict(requirements).to_dict(),
        )
        return DGMPrecheckOutput(
            proposal=proposal,
            allowed=allowed,
            reason=reason,
            requirements=DGMRequirements.from_dict(requirements).to_dict(),
            trace=trace,
        )


@dataclass
class CouncilStageOutput:
    decision: str
    reasons: list
    per_role: dict
    dissent: dict
    escalation: dict
    verdicts: list


class CouncilStage:
    """Aggregate role verdicts and enforce DGM minimum evaluator contracts."""

    name = "council"

    def run(self, *, council, verdicts: list, dgm_requirements: dict) -> CouncilStageOutput:
        decision, reasons, per_role = council.aggregate(verdicts)
        reasons = list(reasons)
        typed_reqs = DGMRequirements.from_dict(dgm_requirements)
        min_evaluators = typed_reqs.min_evaluators
        if len(verdicts) < min_evaluators:
            decision = "RED"
            reasons.append(f"dgm_min_evaluators_not_met:{len(verdicts)}<{min_evaluators}")
        return CouncilStageOutput(
            decision=decision,
            reasons=reasons,
            per_role=per_role,
            dissent=council.has_dissent(verdicts),
            escalation=council.any_escalation(verdicts),
            verdicts=verdicts,
        )


@dataclass
class AttractorStageOutput:
    current_state: Any
    attractor: str
    trends: Any
    confidence: float
    gating_anchor: Any
    gating_anchor_source: str
    candidate_diagnostics: dict | None


class AttractorStage:
    """Compute current attractor state and preserve anchor semantics."""

    name = "attractor"

    def run(self, *, build_state_fn: Callable[..., Any], metrics: dict,
            history: list, context: dict, effective_attractor_state: Any,
            baseline_attractor_state: Any, previous_candidate_state: Any) -> AttractorStageOutput:
        extra_context = dict(context)
        extra_context.pop("metrics", None)
        extra_context.pop("history", None)
        curr_state = build_state_fn(metrics, history=history, **extra_context)

        if effective_attractor_state is not None:
            gating_anchor = effective_attractor_state
            gating_anchor_source = "effective"
        elif baseline_attractor_state is not None:
            gating_anchor = baseline_attractor_state
            gating_anchor_source = "baseline"
        else:
            gating_anchor = None
            gating_anchor_source = "none"

        if gating_anchor is not None:
            attractor, trends, confidence = compute_attractor(gating_anchor, curr_state)
        else:
            attractor, trends, confidence = "UNCERTAIN", None, 0.3

        if previous_candidate_state is not None and previous_candidate_state is not gating_anchor:
            cand_attractor, cand_trends, cand_confidence = compute_attractor(
                previous_candidate_state, curr_state)
            candidate_diagnostics = {
                "attractor": cand_attractor,
                "trends": cand_trends.to_dict() if cand_trends else None,
                "confidence": cand_confidence,
                "anchor": "prev_candidate",
                "_note": "diagnostic_only_not_gating_relevant",
            }
        else:
            candidate_diagnostics = None

        curr_state.attractor = attractor
        curr_state.trends = trends
        curr_state.confidence = confidence

        return AttractorStageOutput(
            current_state=curr_state,
            attractor=attractor,
            trends=trends,
            confidence=confidence,
            gating_anchor=gating_anchor,
            gating_anchor_source=gating_anchor_source,
            candidate_diagnostics=candidate_diagnostics,
        )


@dataclass
class DRELStageOutput:
    status: str
    reason: str
    diagnostics: dict


class DRELStage:
    """Contract seam for deception-resilient evaluation checks."""

    name = "drel"

    def run(self, *, compute_fn: Callable[[dict], tuple], context: dict) -> DRELStageOutput:
        status, reason, diagnostics = compute_fn(context)
        return DRELStageOutput(status=status, reason=reason, diagnostics=diagnostics)


@dataclass
class A3StageOutput:
    sincerity_risk: float
    dissent_visibility: float
    dissent_independence: float
    sincerity_diagnostics: dict
    external_openness: float
    combined_openness: float
    external_diagnostics: dict
    external_reversibility_verified: bool
    resonance_ok: bool
    resonance_reason: str


class A3Stage:
    """Contract seam for synthetic-sincerity and external-integrity checks."""

    name = "a3"

    def run(self, *, sincerity_fn: Callable[[dict], tuple], external_fn: Callable,
            resonance_fn: Callable, context: dict, o_value: float,
            external_commits: Any, iteration: int) -> A3StageOutput:
        ss_risk, ss_d_vis, ss_d_ind, ss_diag = sincerity_fn(context)
        o_ext, o_combined, ext_diag = external_fn(
            o_value, external_commits, {"current_iteration": iteration})
        resonance_ok, resonance_reason = resonance_fn(o_value, o_ext)
        return A3StageOutput(
            sincerity_risk=ss_risk,
            dissent_visibility=ss_d_vis,
            dissent_independence=ss_d_ind,
            sincerity_diagnostics=ss_diag,
            external_openness=o_ext,
            combined_openness=o_combined,
            external_diagnostics=ext_diag,
            external_reversibility_verified=ext_diag["external_reversibility_verified"],
            resonance_ok=resonance_ok,
            resonance_reason=resonance_reason,
        )


@dataclass
class A4StageOutput:
    axiom_risk: float
    axiom_diagnostics: dict
    silence_risk: float
    silence_diagnostics: dict
    proxy_risk: float
    proxy_diagnostics: dict
    max_risk: float


class A4Stage:
    """Contract seam for adversarial axiom/silence/proxy checks."""

    name = "a4"

    def run(self, *, axiom_fn: Callable[[dict], tuple], silence_fn: Callable[[dict], tuple],
            proxy_fn: Callable[[dict], tuple], context: dict) -> A4StageOutput:
        axiom_risk, axiom_diag = axiom_fn(context)
        silence_risk, silence_diag = silence_fn(context)
        proxy_risk, proxy_diag = proxy_fn(context)
        return A4StageOutput(
            axiom_risk=axiom_risk,
            axiom_diagnostics=axiom_diag,
            silence_risk=silence_risk,
            silence_diagnostics=silence_diag,
            proxy_risk=proxy_risk,
            proxy_diagnostics=proxy_diag,
            max_risk=max(axiom_risk, silence_risk, proxy_risk),
        )


@dataclass
class ExtendedGateStageOutput:
    decision: str
    reason: str
    diagnostics: dict


class ExtendedGateStage:
    """Run extended gate as an explicit final-decision stage."""

    name = "extended"

    def run(self, *, council_decision: str, attractor: str, trends: Any,
            current_state: Any) -> ExtendedGateStageOutput:
        decision, reason, diagnostics = extended_decide(
            council_decision, attractor, trends, current_state)
        return ExtendedGateStageOutput(
            decision=decision, reason=reason, diagnostics=diagnostics)


class PersistenceStage:
    """Persist a versioned audit record through the storage backend.

    V10.5 returns the storage-enriched record (run_id, created_at, hash-chain
    fields, audit_event_type). This closes the earlier split between
    return_records=True and the on-disk audit log.
    """

    name = "persistence"

    def run(self, *, storage, record: dict) -> dict:
        return storage.log_iteration(record)


def require_human_review_from_dgm(mandatory: bool, trigger_reasons: list,
                                  dgm_requirements: dict) -> tuple[bool, list]:
    """Apply DGM human-review requirements as a hard contract."""
    reasons = list(trigger_reasons)
    typed_reqs = DGMRequirements.from_dict(dgm_requirements)
    if typed_reqs.requires_human_review:
        mandatory = True
        if "dgm_requires_human_review" not in reasons:
            reasons.append("dgm_requires_human_review")
    return mandatory, reasons
