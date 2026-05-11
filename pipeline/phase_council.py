"""Council governance phase service.

P1 split from the former monolithic ``pipeline.phase_services`` module.
"""

from dataclasses import dataclass
from typing import Any

from gate import decide
from pipeline.phase_runtime import ContextRegistry, PhaseResult
from policy_gate import check_policy_change


@dataclass(frozen=True)
class CouncilPhaseInput:
    iteration: int
    parent_metrics: dict[str, Any]
    child_metrics: dict[str, Any]
    baseline_metrics: dict[str, Any]
    governance_mode: str
    adjusted_thresholds: dict[str, Any]
    agent: Any
    candidate: Any
    role_verifier: Any
    role_policy: Any
    role_critic: Any
    role_truth: Any
    counter_checker: Any
    truth_layer: Any
    council_stage: Any
    council: Any
    dgm_requirements: dict[str, Any]


@dataclass
class CouncilPhaseResult:
    verdicts: list[Any]
    gate_decision: str
    gate_reason: Any
    gate_diagnostics: dict[str, Any]
    policy_decision: str
    policy_reasons: list[str]
    policy_diagnostics: dict[str, Any]
    counter_decision: str
    counter_reasons: list[str]
    counter_diagnostics: dict[str, Any]
    truth_decision: str
    truth_reason: str
    truth_diagnostics: dict[str, Any]
    council_decision: str
    council_reasons: list[str]
    per_role: dict[str, Any]
    dissent: dict[str, Any]
    escalation: dict[str, Any]
    trace_entry: dict[str, Any]


class CouncilPhase:
    """Evaluate verifier/policy/critic/truth roles through an explicit input contract.

    V11.2 migrates CouncilPhase from "imperative call with many kwargs" to a
    declarative phase shape:

      ContextRegistry -> CouncilPhaseInput -> CouncilPhaseResult -> PhaseResult.patch

    The returned ``PhaseResult`` is immutable and contains the exact patch that
    the runner must merge into ``IterationContext``. Business logic does not
    write audit entries; the PhaseExecutor derives them from the result.
    """

    name = "council_phase"
    input_type = CouncilPhaseInput
    required_keys = (
        "iteration", "parent_metrics", "child_metrics", "baseline_metrics",
        "governance_mode", "adjusted_thresholds", "agent", "candidate",
        "role_verifier", "role_policy", "role_critic", "role_truth",
        "counter_checker", "truth_layer", "council_stage", "council",
        "dgm_requirements",
    )

    def build_input(self, registry: ContextRegistry) -> CouncilPhaseInput:
        values = registry.require(self.required_keys)
        return CouncilPhaseInput(**values)

    @staticmethod
    def _legacy_input_from_kwargs(kwargs: dict[str, Any]) -> CouncilPhaseInput:
        return CouncilPhaseInput(**{key: kwargs[key] for key in CouncilPhase.required_keys})

    def evaluate(self, phase_input: CouncilPhaseInput) -> CouncilPhaseResult:
        verdicts: list[Any] = []
        gate_d, gate_r, gate_diag = decide(
            phase_input.parent_metrics,
            phase_input.child_metrics,
            baseline=phase_input.baseline_metrics,
        )
        if phase_input.governance_mode == "hold":
            if gate_d == "GREEN" and gate_diag.get("drift", 0) > phase_input.adjusted_thresholds["max_drift"]:
                gate_d, gate_r = "YELLOW", "hold_mode_drift_tightened"
            path_risk_high = (
                gate_diag.get("path_risk", 0) > phase_input.adjusted_thresholds["max_path_risk"]
            )
            if gate_d == "GREEN" and path_risk_high:
                gate_d, gate_r = "YELLOW", "hold_mode_path_risk_tightened"
        verdicts.append(phase_input.role_verifier.evaluate(gate_d, gate_r, gate_diag))

        pg_d, pg_reasons, pg_diag = check_policy_change(
            phase_input.agent.policy,
            phase_input.candidate.policy,
        )
        verdicts.append(phase_input.role_policy.evaluate(pg_d, pg_reasons, pg_diag))

        cc_pol = phase_input.counter_checker.check_policy_change(
            phase_input.agent.policy,
            phase_input.candidate.policy,
            iteration_context={
                "parent_metrics": phase_input.parent_metrics,
                "child_metrics": phase_input.child_metrics,
            },
        )
        cc_beh = phase_input.counter_checker.check_behavior_change(
            phase_input.parent_metrics,
            phase_input.child_metrics,
            gate_diag,
        )
        cc_decisions = [cc_pol[0], cc_beh[0]]
        cc_final = "RED" if "RED" in cc_decisions else (
            "YELLOW" if "YELLOW" in cc_decisions else "GREEN"
        )
        cc_reasons = cc_pol[1] + cc_beh[1]
        cc_diag = {"policy": cc_pol[2], "behavior": cc_beh[2]}
        phase_input.counter_checker.record_disagreement(phase_input.iteration, gate_d, cc_final)
        verdicts.append(phase_input.role_critic.evaluate(cc_final, cc_reasons, cc_diag))

        ts_d, ts_r, ts_diag = phase_input.truth_layer.check(
            phase_input.child_metrics,
            phase_input.parent_metrics,
        )
        verdicts.append(phase_input.role_truth.evaluate(ts_d, ts_r, ts_diag))

        council_out = phase_input.council_stage.run(
            council=phase_input.council,
            verdicts=verdicts,
            dgm_requirements=phase_input.dgm_requirements,
        )
        trace_entry = {
            "stage": "council",
            "decision": council_out.decision,
            "reason": "|".join(council_out.reasons),
        }
        return CouncilPhaseResult(
            verdicts=verdicts,
            gate_decision=gate_d,
            gate_reason=gate_r,
            gate_diagnostics=gate_diag,
            policy_decision=pg_d,
            policy_reasons=pg_reasons,
            policy_diagnostics=pg_diag,
            counter_decision=cc_final,
            counter_reasons=cc_reasons,
            counter_diagnostics=cc_diag,
            truth_decision=ts_d,
            truth_reason=ts_r,
            truth_diagnostics=ts_diag,
            council_decision=council_out.decision,
            council_reasons=council_out.reasons,
            per_role=council_out.per_role,
            dissent=council_out.dissent,
            escalation=council_out.escalation,
            trace_entry=trace_entry,
        )

    @staticmethod
    def result_patch(result: CouncilPhaseResult) -> dict[str, Any]:
        return {
            "verdicts": result.verdicts,
            "gate_d": result.gate_decision,
            "gate_r": result.gate_reason,
            "gate_diag": result.gate_diagnostics,
            "pg_d": result.policy_decision,
            "pg_reasons": result.policy_reasons,
            "pg_diag": result.policy_diagnostics,
            "cc_final": result.counter_decision,
            "cc_reasons": result.counter_reasons,
            "cc_diag": result.counter_diagnostics,
            "ts_d": result.truth_decision,
            "ts_r": result.truth_reason,
            "ts_diag": result.truth_diagnostics,
            "council_decision": result.council_decision,
            "council_reasons": result.council_reasons,
            "per_role": result.per_role,
            "dissent_info": result.dissent,
            "escalation_info": result.escalation,
        }

    def run(self, phase_input: CouncilPhaseInput | None = None, **kwargs: Any) -> PhaseResult | CouncilPhaseResult:
        """Run council logic.

        New declarative callers pass ``CouncilPhaseInput`` and receive
        ``PhaseResult``. Legacy keyword callers are still supported and receive
        the historical ``CouncilPhaseResult`` to avoid breaking old tests during
        the migration window.
        """
        if phase_input is None:
            legacy_input = self._legacy_input_from_kwargs(kwargs)
            return self.evaluate(legacy_input)
        result = self.evaluate(phase_input)
        return PhaseResult(
            phase=self.name,
            decision=result.council_decision,
            reason="|".join(result.council_reasons),
            diagnostics={
                "gate_decision": result.gate_decision,
                "policy_decision": result.policy_decision,
                "counter_decision": result.counter_decision,
                "truth_decision": result.truth_decision,
                "dissent": result.dissent,
                "escalation": result.escalation,
            },
            patch=self.result_patch(result),
            trace_entries=(result.trace_entry,),
        )
