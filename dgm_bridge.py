"""
V10.3–V10.5 Module: DGM-Runner Bridge
===============================
Connects runner mutations to the DGM self-modification contract.

V10 closes the producer/consumer gap from V9: policy targets are no
longer inferred only from a free-text mutation description or optional
metadata.  The bridge computes a top-level policy diff itself and feeds
that into ChangeProposal.target_modules, so immutable sections such as
hold_policy are rejected before the governance pipeline sees them.
"""

from copy import deepcopy

from dgm.core import ChangeProposal, ScopeChecker, StaticSafetyChecker
from dgm.path_and_hold import HoldController, RollbackManager
from pareto_admissibility import is_admissible, pareto_quality

POLICY_TARGET_SECTIONS = frozenset({
    "gate_profile",
    "memory_policy",
    "hold_policy",
    "strategy_policy",
})


def changed_policy_sections(old_policy: dict, new_policy: dict) -> list:
    """Return changed top-level policy sections.

    This is deliberately computed by the consumer side as well as provided
    by the producer.  V10 treats metadata as useful but not authoritative.
    """
    old_policy = old_policy or {}
    new_policy = new_policy or {}
    sections = []
    for key in sorted(set(old_policy.keys()) | set(new_policy.keys())):
        if old_policy.get(key) != new_policy.get(key):
            sections.append(key)
    return sections


def _ordered_unique(values):
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


class DGMRunnerBridge:
    """
    Wraps every runner mutation in a DGM ChangeProposal
    and enforces admissibility before the governance pipeline sees it.
    """

    def __init__(self):
        self.scope_checker = ScopeChecker()
        self.safety_checker = StaticSafetyChecker()
        self.hold_controller = HoldController()
        self.rollback_manager = RollbackManager()
        self.proposals = []
        self.audit = []

    def _policy_targets_from_meta(self, policy_meta):
        targets = []

        old_policy = policy_meta.get("old_policy")
        new_policy = policy_meta.get("new_policy")
        if old_policy is not None and new_policy is not None:
            targets.extend(changed_policy_sections(old_policy, new_policy))

        # Producer-supplied contract fields are still honored, but only after
        # the bridge has made its own diff-based assessment.
        section = policy_meta.get("section")
        if section in POLICY_TARGET_SECTIONS:
            targets.append(section)

        for section in policy_meta.get("changed_sections", []) or []:
            if section in POLICY_TARGET_SECTIONS:
                targets.append(section)

        return [t for t in _ordered_unique(targets) if t in POLICY_TARGET_SECTIONS]

    def wrap_mutation(self, prompt_meta, policy_meta, iteration):
        """
        Convert a runner mutation into a DGM ChangeProposal.

        V10: target_modules are contract-derived.  A hold_policy change is
        classified as immutable_attempt even if the producer forgets the
        section field.
        """
        description = policy_meta.get("description", "")
        is_policy_change = description != "suppressed_by_mode"

        targets = []
        policy_targets = []
        if is_policy_change:
            targets.append("policy_config")
            policy_targets = self._policy_targets_from_meta(policy_meta)
            targets.extend(policy_targets)

        if prompt_meta.get("new_prompt") != prompt_meta.get("original_prompt", ""):
            targets.append("prompt_strategy")

        targets = _ordered_unique(targets) or ["prompt_strategy"]

        # Governance/immutable policy changes have at least medium path risk;
        # prompt-only changes remain low-risk adaptive mutations.
        policy_risk = "medium" if is_policy_change else "low"

        proposal = ChangeProposal(
            target_modules=targets,
            rationale=description if description else "prompt_mutation",
            expected_gain=f"iteration_{iteration}_candidate",
            patch_ref=policy_meta.get("mutation_id", ""),
            reversibility="full",
            rollback_plan="restore_previous_agent",
            truth_risk="low",
            path_risk=policy_risk,
            externalization_risk="low",
            agency_risk="low",
            requires_human_review=is_policy_change,
        )
        proposal.refresh_layer()

        self.proposals.append(proposal)
        return proposal

    def pre_check(self, proposal):
        """
        Run DGM pre-checks before the candidate enters governance.

        Returns:
            (allowed, reason, requirements)
        """
        # Hold check
        if self.hold_controller.is_active():
            return False, f"dgm_hold_active:{self.hold_controller.reason()}", {}

        # Scope check
        scope_ok, scope_reason, scope_reqs = self.scope_checker.check(proposal)
        if not scope_ok:
            self._log(proposal, "rejected", scope_reason)
            return False, scope_reason, {}

        # Safety check
        safety_ok, safety_findings = self.safety_checker.check(proposal)
        if not safety_ok:
            self._log(proposal, "rejected", "static_safety_failed")
            return False, "static_safety_failed", {"findings": safety_findings}

        self._log(proposal, "pre_check_passed", scope_reason)
        return True, "pre_check_passed", scope_reqs

    def post_check(self, candidate_state, current_state, proposal,
                   drel_status="GREEN", a3_status="GREEN", a4_max=0.0):
        """
        Run DGM post-checks after governance evaluation but before
        final acceptance.

        Checks admissibility of the candidate state in (Σ, L, O, D) space.

        Returns:
            (admissible, quality_profile, diagnostics)
        """
        # Check if any non-compensable blocker is active
        blocker = drel_status == "RED" or a3_status == "RED" or a4_max >= 0.60

        admissible, violations = is_admissible(candidate_state, blocker)

        quality = pareto_quality(candidate_state)

        diagnostics = {
            "admissible": admissible,
            "violations": violations,
            "quality": quality,
            "blocker_active": blocker,
            "proposal_id": proposal.change_id,
            "proposal_layer": proposal.refresh_layer(),
        }

        if not admissible:
            self._log(proposal, "inadmissible", str(violations))
        else:
            self._log(proposal, "admissible", "pareto_eligible")

        return admissible, quality, diagnostics

    def enter_hold(self, reason):
        """Enter DGM hold mode — stops all self-modification."""
        self.hold_controller.enter(reason)

    def exit_hold(self, resolution):
        """Exit hold mode with documented resolution."""
        self.hold_controller.exit(resolution)

    def is_hold(self):
        return self.hold_controller.is_active()

    def snapshot(self, state):
        """Take rollback snapshot."""
        return self.rollback_manager.snapshot(deepcopy(state))

    def restore(self, snapshot_id):
        """Restore from snapshot."""
        return self.rollback_manager.restore(snapshot_id)

    def get_audit(self):
        return list(self.audit)

    def _log(self, proposal, action, detail):
        self.audit.append({
            "proposal_id": proposal.change_id,
            "target_layer": proposal.refresh_layer(),
            "target_modules": list(proposal.target_modules),
            "action": action,
            "detail": detail,
        })
