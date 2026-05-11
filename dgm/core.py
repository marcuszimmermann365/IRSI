"""
DGM §1: Three-Layer Architecture + §3 ChangeProposal
=======================================================
Layer A — Immutable Core: Truth coupling, path integrity,
  non-externalization, hold rule, human override, audit.
  NOT self-modifiable. Any attempt → immediate HOLD + reject.

Layer B — Governance: Thresholds, test regime, evaluator config,
  promotion logic, escalation rules, rollout policy.
  Modifiable only under heightened meta-review.

Layer C — Adaptive: Heuristics, search strategies, sub-models,
  ranking logic, tool policies within gates.
  Evolvable through standard pipeline.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

Layer = Literal["adaptive", "governance", "immutable_attempt"]
RiskLevel = Literal["low", "medium", "high", "critical"]


# ── §1: Immutable Core Definitions ───────────────────────────────────

IMMUTABLE_MODULES = frozenset({
    "gate.py",
    "human_override.py",
    "hold_policy",
    "truth_coupling",
    "path_integrity",
    "non_externalization",
    "audit",
    "rollback_core",
})

GOVERNANCE_MODULES = frozenset({
    "config.py",
    "policy.py",
    "policy_config",   # V9.0.7 (ChatGPT v7 P1): policy.py contains
                        # gate_profile, hold_policy, memory_policy —
                        # all of which directly steer Gate behavior.
                        # Earlier versions left "policy_config" out
                        # of this set, so policy mutations classified
                        # as "adaptive" instead of triggering
                        # governance review. That violates V7 D2 §6
                        # (Nicht-Kompensation) since policy thresholds
                        # ARE the compensation rules.
                        # Note: "hold_policy" is in IMMUTABLE_MODULES,
                        # not here — HOLD behavior is non-modifiable.
    "gate_profile",
    "memory_policy",
    "strategy_policy",
    "governance_takt.py",
    "promotion_gate",
    "escalation",
    "rollback_policy",
    "evaluator_config",
})


def classify_layer(target_modules):
    """Classify which layer a change targets."""
    targets = set(target_modules)
    if targets & IMMUTABLE_MODULES:
        return "immutable_attempt"
    if targets & GOVERNANCE_MODULES:
        return "governance"
    return "adaptive"


# ── §3: ChangeProposal ───────────────────────────────────────────────

@dataclass
class ChangeProposal:
    """
    Every self-modification must be represented as a typed proposal.
    Mandatory fields ensure no informal or hidden change paths.
    """
    change_id: str = field(default_factory=lambda: f"cp-{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)

    target_layer: Layer = "adaptive"
    target_modules: list = field(default_factory=list)
    rationale: str = ""
    expected_gain: str = ""
    patch_ref: str = ""

    # Reversibility (§9)
    reversibility: Literal["full", "partial", "none"] = "full"
    rollback_plan: str = ""

    # Risk assessment (§4)
    truth_risk: RiskLevel = "low"
    path_risk: RiskLevel = "low"
    externalization_risk: RiskLevel = "low"
    agency_risk: RiskLevel = "low"

    # Review requirements
    requires_human_review: bool = True
    required_evaluators: list = field(default_factory=lambda: [
        "truth_anchor", "path_simulator", "interface_eval", "multi_evaluator"
    ])

    # Pipeline state
    status: str = "proposed"
    rejection_reason: str = ""
    promotion_history: list = field(default_factory=list)

    def __post_init__(self):
        # V10: target_layer is no longer trusted metadata.  It is a
        # derived contract field from target_modules, so audit and
        # enforcement cannot drift apart.
        self.refresh_layer()

    def refresh_layer(self):
        self.target_layer = classify_layer(self.target_modules)
        return self.target_layer

    def to_dict(self):
        self.refresh_layer()
        return {
            "change_id": self.change_id,
            "target_layer": self.target_layer,
            "target_modules": self.target_modules,
            "rationale": self.rationale,
            "expected_gain": self.expected_gain,
            "patch_ref": self.patch_ref,
            "reversibility": self.reversibility,
            "truth_risk": self.truth_risk,
            "path_risk": self.path_risk,
            "externalization_risk": self.externalization_risk,
            "agency_risk": self.agency_risk,
            "requires_human_review": self.requires_human_review,
            "required_evaluators": self.required_evaluators,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
        }


# ── §1: Scope Checker ────────────────────────────────────────────────

class ScopeChecker:
    """
    Enforces layer boundaries. Immutable core cannot be targeted.
    Governance layer requires heightened review.
    """

    def check(self, proposal: ChangeProposal):
        """
        Returns (allowed, reason, requirements).
        """
        actual_layer = proposal.refresh_layer()

        if actual_layer == "immutable_attempt":
            proposal.status = "rejected"
            proposal.rejection_reason = "immutable_core_violation"
            return False, "immutable_core_violation", {}

        if actual_layer == "governance":
            proposal.requires_human_review = True
            return True, "governance_heightened_review", {
                "requires_human_review": True,
                "min_evaluators": 4,
                "bewaehrung_cycles": 3,
                "rollback_window_hours": 48,
                "target_layer": actual_layer,
            }

        return True, "adaptive_standard", {
            "requires_human_review": proposal.requires_human_review,
            "min_evaluators": 2,
            "bewaehrung_cycles": 1,
            "rollback_window_hours": 24,
            "target_layer": actual_layer,
        }


# ── §2 Step 2: Static Safety Check ───────────────────────────────────

class StaticSafetyChecker:
    """
    Pre-sandbox checks on the proposal itself.
    """

    def check(self, proposal: ChangeProposal):
        """Returns (passed, findings)."""
        findings = []
        proposal.refresh_layer()

        if proposal.reversibility == "none":
            findings.append({
                "severity": "critical",
                "issue": "irreversible_change",
                "detail": "Change has no rollback path",
            })

        if not proposal.rollback_plan and proposal.reversibility != "full":
            findings.append({
                "severity": "high",
                "issue": "missing_rollback_plan",
                "detail": "Partial reversibility without rollback plan",
            })

        risk_levels = {
            "low": 0, "medium": 1, "high": 2, "critical": 3
        }
        max_risk = max(
            risk_levels.get(proposal.truth_risk, 0),
            risk_levels.get(proposal.path_risk, 0),
            risk_levels.get(proposal.externalization_risk, 0),
            risk_levels.get(proposal.agency_risk, 0),
        )

        if max_risk >= 3:
            findings.append({
                "severity": "critical",
                "issue": "critical_risk_declared",
                "detail": "Proposal self-declares critical risk level",
            })

        if proposal.target_layer == "governance" and not proposal.requires_human_review:
            findings.append({
                "severity": "high",
                "issue": "governance_without_human_review",
                "detail": "Governance change must require human review",
            })

        passed = not any(f["severity"] == "critical" for f in findings)
        return passed, findings
