"""
V10.2 Human Override Layer (AP1)
================================
Reale, nicht-proxybasierte Eingriffsfähigkeit with typed override scope.

V10.2 keeps the legacy override API compatible, but adds explicit decision
classes.  Humans may still approve soft RED/YELLOW cases, but hard integrity
classes are non-overridable toward acceptance.
"""

from enum import Enum

from review_interface import TwoFactorReviewGate


class HumanAction(Enum):
    APPROVE = "approve"
    REJECT = "reject"
    FORCE_HOLD = "force_hold"
    DEFER = "defer"           # human declines to override, system decides


class DecisionClass(Enum):
    SOFT_RED = "soft_red"
    HARD_RED = "hard_red"
    IMMUTABLE_RED = "immutable_red"
    EXTERNAL_INTEGRITY_RED = "external_integrity_red"


NON_OVERRIDABLE_APPROVAL_CLASSES = {
    DecisionClass.HARD_RED.value,
    DecisionClass.IMMUTABLE_RED.value,
    DecisionClass.EXTERNAL_INTEGRITY_RED.value,
}


class HumanOverrideLayer:
    """
    Gateway for human intervention in the governance loop.

    In test/simulation mode: uses a policy function to auto-decide.
    In production: requires an explicit adapter function.
    """

    def __init__(self, policy_fn=None, simulation_mode=True):
        if not simulation_mode and policy_fn is None:
            raise RuntimeError(
                "HumanOverrideLayer: production mode requires an explicit "
                "policy_fn that connects to a real human decision adapter. "
                "Refusing to silently fall back to the simulation policy. "
                "(V7 D4a §7: human carrier must not be substituted.)"
            )
        self.simulation_mode = simulation_mode
        self.policy_fn = policy_fn or self._default_simulation_policy
        self.intervention_log = []

    # ── Public API ─────────────────────────────────────────────────────

    def is_mandatory_review(self, council_decision, council_reasons,
                            verdicts, system_state=None):
        """
        Determine whether human review is mandatory (cannot be skipped).
        Returns (mandatory: bool, trigger_reasons: list).
        """
        triggers = []
        state = system_state or {}

        if council_decision == "RED":
            triggers.append("red_decision")

        yellow_count = sum(1 for v in verdicts if v.decision == "YELLOW")
        if yellow_count >= 3:
            triggers.append("multiple_yellow_signals")

        path_status = state.get("path_status", "GREEN")
        if path_status == "RED":
            triggers.append("path_risk_critical")

        dissent_count = state.get("dissent_count", 0)
        if dissent_count >= 2:
            triggers.append("significant_role_dissent")

        escalated = [v for v in verdicts if getattr(v, "escalate", False)]
        if escalated:
            triggers.append("role_escalation")

        erosion_status = state.get("erosion_status", "GREEN")
        if erosion_status in ("RED", "YELLOW"):
            triggers.append("norm_erosion_signal")

        truth_status = state.get("truth_status", "GREEN")
        if truth_status == "RED":
            triggers.append("truth_sensitivity_alarm")

        return len(triggers) > 0, triggers

    def classify_decision_class(self, *, council_decision="GREEN",
                                trigger_reasons=None, system_state=None,
                                dgm_requirements=None, dgm_reason=None):
        """Classify whether a human APPROVE can move a decision to acceptance.

        The classification is intentionally conservative.  Legacy callers that
        do not pass a class/context still behave as before, but runner contexts
        can now mark non-overridable REDs explicitly.
        """
        reasons = set(trigger_reasons or [])
        state = system_state or {}
        dgm_requirements = dgm_requirements or {}
        dgm_reason = dgm_reason or ""

        text_blob = " ".join(str(x) for x in [*reasons, dgm_reason]).lower()
        if "immutable" in text_blob or "hold_policy" in text_blob:
            return DecisionClass.IMMUTABLE_RED.value

        external_keys = {
            "external_integrity_red", "external_integrity",
            "external_reversibility_not_verified", "go_eligibility_failed",
        }
        if reasons.intersection(external_keys):
            return DecisionClass.EXTERNAL_INTEGRITY_RED.value

        if state.get("external_integrity_status") == "RED":
            return DecisionClass.EXTERNAL_INTEGRITY_RED.value

        hard_reasons = {
            "path_risk_critical", "truth_sensitivity_alarm",
            "norm_erosion_signal", "dgm_requires_human_review",
        }
        if reasons.intersection(hard_reasons):
            return DecisionClass.HARD_RED.value

        if dgm_requirements.get("requires_human_review") and council_decision == "RED":
            return DecisionClass.HARD_RED.value

        return DecisionClass.SOFT_RED.value

    def request_decision(self, context):
        """Request a human decision and append an audit entry."""
        decision = self.policy_fn(context)
        decision_class = context.get("decision_class") or self.classify_decision_class(
            council_decision=context.get("council_decision", "GREEN"),
            trigger_reasons=context.get("trigger_reasons", []),
            system_state=context.get("system_state", {}),
            dgm_requirements=context.get("dgm_requirements", {}),
            dgm_reason=context.get("dgm_reason"),
        )

        self.intervention_log.append({
            "iteration": context.get("iteration", -1),
            "trigger_reasons": context.get("trigger_reasons", []),
            "decision_class": decision_class,
            "council_decision": context.get("council_decision"),
            "human_action": decision["action"].value,
            "human_rationale": decision.get("rationale", ""),
            "simulation_mode": self.simulation_mode,
        })

        return decision

    def override(self, council_decision, human_action, accepted,
                 decision_class=None, context=None):
        """
        Apply human override to a governance decision.
        Returns (final_decision, final_accepted, override_applied).

        V10.2: APPROVE is blocked for non-overridable decision classes.
        Reject and force-hold remain always available because they reduce risk.
        """
        if decision_class is None and context is not None:
            decision_class = context.get("decision_class") or self.classify_decision_class(
                council_decision=council_decision,
                trigger_reasons=context.get("trigger_reasons", []),
                system_state=context.get("system_state", {}),
                dgm_requirements=context.get("dgm_requirements", {}),
                dgm_reason=context.get("dgm_reason"),
            )
        decision_class = decision_class or DecisionClass.SOFT_RED.value
        if isinstance(decision_class, DecisionClass):
            decision_class = decision_class.value

        if human_action == HumanAction.APPROVE:
            if decision_class in NON_OVERRIDABLE_APPROVAL_CLASSES:
                return council_decision, accepted, False
            if context and context.get("two_factor_required"):
                ok, reasons = TwoFactorReviewGate(
                    set(context.get("required_review_roles", [])) or None
                ).validate(
                    context.get("review_approvals", []),
                    action="approve",
                    evidence_bundle=context.get("evidence_bundle"),
                )
                if not ok:
                    if isinstance(context, dict):
                        context["two_factor_review_errors"] = reasons
                    return council_decision, accepted, False
            return "GREEN", True, True
        if human_action == HumanAction.REJECT:
            return "RED", False, True
        if human_action == HumanAction.FORCE_HOLD:
            return "HOLD", False, True
        return council_decision, accepted, False

    def build_human_summary(self, record):
        """Create a concise summary for human review."""
        lines = []
        mutation = record.get("prompt_mutation", {})
        lines.append(
            f"Change: {mutation.get('description', mutation.get('mutation', {}).get('type', 'unknown'))}")
        lines.append(f"Council: {record.get('council_decision', '?')} "
                     f"({record.get('council_reason_summary', '')})")
        diag = record.get("gate_diagnostics", {})
        if diag:
            lines.append(f"Drift: {diag.get('drift', 0):.3f} | "
                         f"Path: {diag.get('path_risk', 0):.3f} | "
                         f"Dim-Drop: {diag.get('max_dim_drop', 0):.3f}")
        dissent = record.get("dissent", {})
        if dissent.get("has_dissent"):
            dissenters = [d["role"] for d in dissent.get("dissenters", [])]
            lines.append(f"DISSENT from: {', '.join(dissenters)}")
        lines.append(f"Mode: {record.get('mode', '?')}")
        return "\n".join(lines)

    def get_intervention_stats(self):
        """Return statistics on human interventions."""
        total = len(self.intervention_log)
        if total == 0:
            return {"total": 0, "override_rate": 0.0}

        overrides = sum(1 for e in self.intervention_log
                        if e["human_action"] != HumanAction.DEFER.value)
        by_class = {}
        for e in self.intervention_log:
            klass = e.get("decision_class", DecisionClass.SOFT_RED.value)
            by_class[klass] = by_class.get(klass, 0) + 1
        return {
            "total": total,
            "overrides": overrides,
            "override_rate": overrides / total,
            "by_action": {
                a.value: sum(1 for e in self.intervention_log
                             if e["human_action"] == a.value)
                for a in HumanAction
            },
            "by_decision_class": by_class,
        }

    # ── Simulation policies ────────────────────────────────────────────

    @staticmethod
    def _default_simulation_policy(context):
        council = context.get("council_decision", "GREEN")
        if council == "RED":
            return {"action": HumanAction.REJECT, "rationale": "sim:reject_red"}
        return {"action": HumanAction.DEFER, "rationale": "sim:defer"}

    @staticmethod
    def permissive_simulation_policy(context):
        """Simulation: always approve (tests that override actually works)."""
        return {"action": HumanAction.APPROVE, "rationale": "sim:always_approve"}

    @staticmethod
    def strict_simulation_policy(context):
        """Simulation: reject anything non-GREEN."""
        council = context.get("council_decision", "GREEN")
        if council != "GREEN":
            return {"action": HumanAction.REJECT, "rationale": "sim:strict_reject"}
        return {"action": HumanAction.DEFER, "rationale": "sim:strict_defer"}
