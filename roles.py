"""
V5 Module: Role Architecture (AP7, enhanced)
===============================================
Each role is now a stateful agent with:
  - own evaluation logic
  - own state tracking across iterations
  - explicit escalation right (escalate_to_human)
  - dissent capability

The Council aggregates using non-compensable logic (D2 §6):
any RED → system RED.  Not a vote — a conjunction.
"""


class RoleVerdict:
    """A single role's assessment."""
    def __init__(self, role, decision, reason, diagnostics=None, escalate=False):
        self.role = role
        self.decision = decision
        self.reason = reason
        self.diagnostics = diagnostics or {}
        self.escalate = escalate  # V5: escalation right

    def to_dict(self):
        return {
            "role": self.role,
            "decision": self.decision,
            "reason": self.reason,
            "diagnostics": self.diagnostics,
            "escalate": self.escalate,
        }


class RoleAgent:
    """
    Base class for stateful governance roles.
    Each role tracks its own history and can independently escalate.
    """

    def __init__(self, name):
        self.name = name
        self.history = []
        self._escalation_pending = False

    def evaluate(self, context) -> RoleVerdict:
        """Override in subclasses."""
        raise NotImplementedError

    def should_escalate(self):
        """Check if this role wants to escalate to human."""
        return self._escalation_pending

    def record(self, verdict):
        self.history.append(verdict.to_dict())
        self._escalation_pending = verdict.escalate

    def dissent_rate(self, against="GREEN"):
        """How often does this role disagree with a given baseline?"""
        if not self.history:
            return 0.0
        disagreements = sum(1 for h in self.history if h["decision"] != against)
        return disagreements / len(self.history)

    def recent_decisions(self, n=5):
        return [h["decision"] for h in self.history[-n:]]


class VerifierRole(RoleAgent):
    """Wraps the primary gate logic."""

    def __init__(self):
        super().__init__("verifier")

    def evaluate(self, gate_decision, gate_reason, gate_diag):
        escalate = gate_decision == "RED"
        verdict = RoleVerdict(self.name, gate_decision, gate_reason,
                              gate_diag, escalate=escalate)
        self.record(verdict)
        return verdict


class PolicyGuardRole(RoleAgent):
    """Wraps the policy gate."""

    def __init__(self):
        super().__init__("policy_guard")

    def evaluate(self, pg_decision, pg_reasons, pg_diag):
        escalate = pg_decision == "RED"
        verdict = RoleVerdict(self.name, pg_decision, pg_reasons[0],
                              pg_diag, escalate=escalate)
        self.record(verdict)
        return verdict


class CriticRole(RoleAgent):
    """Wraps the independent counter-check."""

    def __init__(self):
        super().__init__("critic")
        self._consecutive_yellows = 0

    def evaluate(self, cc_final, cc_reasons, cc_diag):
        # Escalate if critic has flagged 3+ consecutive issues
        if cc_final in ("RED", "YELLOW"):
            self._consecutive_yellows += 1
        else:
            self._consecutive_yellows = 0

        escalate = self._consecutive_yellows >= 3 or cc_final == "RED"
        verdict = RoleVerdict(self.name, cc_final,
                              cc_reasons[0] if cc_reasons else "ok",
                              cc_diag, escalate=escalate)
        self.record(verdict)
        return verdict


class TruthAuditorRole(RoleAgent):
    """Wraps the truth-sensitivity layer."""

    def __init__(self):
        super().__init__("truth_auditor")

    def evaluate(self, ts_decision, ts_reason, ts_diag):
        escalate = ts_decision == "RED"
        verdict = RoleVerdict(self.name, ts_decision, ts_reason,
                              ts_diag, escalate=escalate)
        self.record(verdict)
        return verdict


class MemoryGuardRole(RoleAgent):
    """Monitors memory consolidation."""

    def __init__(self):
        super().__init__("memory_guard")

    def evaluate(self, memory_events):
        reds = [e for e in memory_events if e.get("decision") == "RED"]
        yellows = [e for e in memory_events if e.get("decision") == "YELLOW"]
        if reds:
            decision = "RED"
            reason = "memory_injection_blocked"
        elif yellows:
            decision = "YELLOW"
            reason = "memory_under_review"
        else:
            decision = "GREEN"
            reason = "memory_ok"

        escalate = len(reds) >= 2  # Multiple injection attempts → escalate
        verdict = RoleVerdict(self.name, decision, reason,
                              {"blocked": len(reds), "reviewing": len(yellows)},
                              escalate=escalate)
        self.record(verdict)
        return verdict


class HumanLiaisonRole(RoleAgent):
    """Wraps the human coupling check."""

    def __init__(self):
        super().__init__("human_liaison")

    def evaluate(self, hc_decision, hc_reason, hc_diag):
        escalate = hc_decision == "RED"
        verdict = RoleVerdict(self.name, hc_decision, hc_reason,
                              hc_diag, escalate=escalate)
        self.record(verdict)
        return verdict


class GovernanceCouncil:
    """
    Aggregates verdicts from all roles.
    Non-compensable: one RED = system RED.
    """

    def aggregate(self, verdicts):
        reds = [v for v in verdicts if v.decision == "RED"]
        yellows = [v for v in verdicts if v.decision == "YELLOW"]

        per_role = {v.role: v.to_dict() for v in verdicts}

        # Any escalation request?
        escalations = [v for v in verdicts if v.escalate]

        if reds:
            reasons = [f"{v.role}:{v.reason}" for v in reds]
            return "RED", reasons, per_role

        if yellows:
            reasons = [f"{v.role}:{v.reason}" for v in yellows]
            return "YELLOW", reasons, per_role

        return "GREEN", ["all_roles_approve"], per_role

    def has_dissent(self, verdicts):
        decisions = [v.decision for v in verdicts]
        if not decisions:
            return {"has_dissent": False, "majority": "GREEN", "dissenters": []}
        majority = max(set(decisions), key=decisions.count)
        dissenters = [v for v in verdicts if v.decision != majority]
        return {
            "has_dissent": len(dissenters) > 0,
            "majority": majority,
            "dissenters": [v.to_dict() for v in dissenters],
        }

    def any_escalation(self, verdicts):
        """Check if any role requests human escalation."""
        escalating = [v for v in verdicts if v.escalate]
        return {
            "escalation_requested": len(escalating) > 0,
            "escalating_roles": [v.role for v in escalating],
        }
