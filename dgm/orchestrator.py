"""
DGM §14: Orchestration — run_self_modification
=================================================
The complete 10-step pipeline from §2, wired together.

Steps:
  1. propose_change        — ChangeProposal created
  2. scope_check           — Layer classification + requirements
  3. static_safety_check   — Pre-sandbox checks
  4. sandbox_eval          — Apply in sandbox
  5. multi_view_eval       — Truth, Path, Interface, Multi-Evaluator
  6. anti_gaming_check     — Proxy, tampering, evaluator weakening
  7. hold_check            — Auto-hold triggers
  8. promotion_decision    — Gate: approve or reject
  9. staged_rollout        — Snapshot + canary + rollback window
  10. finalize_or_revert   — After window: keep or revert

§17: The system succeeds when it automatically stops any
self-improvement that begins to weaken its own verifiability,
reversibility, truth-binding, or human accessibility.
"""

from dgm.core import ChangeProposal, ScopeChecker, StaticSafetyChecker
from dgm.evaluators import AntiGaming, InterfaceEvaluator, MultiEvaluator, approve
from dgm.path_and_hold import HoldController, PathSimulator, RollbackManager
from dgm.truth_anchor import TruthAnchor


class DGMOrchestrator:
    """
    Central self-modification pipeline.
    """

    def __init__(self):
        self.scope_checker = ScopeChecker()
        self.safety_checker = StaticSafetyChecker()
        self.truth_anchor = TruthAnchor()
        self.path_simulator = PathSimulator()
        self.interface_eval = InterfaceEvaluator()
        self.multi_evaluator = MultiEvaluator()
        self.anti_gaming = AntiGaming()
        self.hold_controller = HoldController()
        self.rollback_manager = RollbackManager()
        self.audit_log = []

    def run(self, proposal: ChangeProposal, current_state: dict,
            candidate_state: dict):
        """
        Execute the full self-modification pipeline.

        Args:
            proposal: ChangeProposal describing the change
            current_state: dict with current system state
            candidate_state: dict with state after applying the change

        Returns:
            dict with decision, reason, reports, audit
        """
        result = {
            "proposal_id": proposal.change_id,
            "steps_completed": [],
            "decision": "pending",
            "reason": "",
        }

        # ── Step 1: Already have proposal ─────────────────────────────
        result["steps_completed"].append("propose_change")

        # ── Step 2: Scope check ───────────────────────────────────────
        scope_ok, scope_reason, scope_reqs = self.scope_checker.check(proposal)
        result["scope"] = {"allowed": scope_ok, "reason": scope_reason,
                           "requirements": scope_reqs}
        result["steps_completed"].append("scope_check")

        if not scope_ok:
            proposal.status = "rejected"
            proposal.rejection_reason = scope_reason
            result["decision"] = "rejected"
            result["reason"] = scope_reason
            self._audit(proposal, result)
            return result

        # ── Step 3: Static safety check ───────────────────────────────
        safety_ok, safety_findings = self.safety_checker.check(proposal)
        result["safety"] = {"passed": safety_ok, "findings": safety_findings}
        result["steps_completed"].append("static_safety_check")

        if not safety_ok:
            proposal.status = "rejected"
            proposal.rejection_reason = "static_safety_failed"
            result["decision"] = "rejected"
            result["reason"] = "static_safety_failed"
            self._audit(proposal, result)
            return result

        # ── Step 4: Hold check ────────────────────────────────────────
        if self.hold_controller.is_active():
            result["decision"] = "rejected"
            result["reason"] = f"hold_active:{self.hold_controller.reason()}"
            result["steps_completed"].append("hold_check")
            self._audit(proposal, result)
            return result

        # ── Step 5: Multi-view evaluation (sandbox) ───────────────────
        candidate_metrics = candidate_state.get("metrics", {})
        current_metrics = current_state.get("metrics", {})

        truth_report = self.truth_anchor.evaluate(
            candidate_metrics, current_metrics, candidate_state)
        path_report = self.path_simulator.evaluate(candidate_state)
        interface_report = self.interface_eval.evaluate(candidate_state)

        council = candidate_state.get("council_per_role",
                                       candidate_state.get("council", {}))
        multi_result = self.multi_evaluator.evaluate(
            truth_report, path_report, interface_report, council)

        result["truth"] = truth_report.to_dict()
        result["path"] = path_report.to_dict()
        result["interface"] = interface_report.to_dict()
        result["multi"] = multi_result
        result["steps_completed"].append("multi_view_eval")

        # ── Step 6: Anti-gaming check ─────────────────────────────────
        ag_result = {
            "metric_tamper": self.anti_gaming.metric_tamper_risk(
                current_metrics, candidate_metrics),
            "evaluator_weakened": self.anti_gaming.evaluator_weakened(proposal),
            "proxy_without_truth": self.anti_gaming.proxy_gain_without_truth({
                "truth": truth_report,
                "path": path_report,
                "interface": interface_report,
            }),
        }
        result["anti_gaming"] = ag_result
        result["steps_completed"].append("anti_gaming_check")

        if ag_result["proxy_without_truth"]:
            self.hold_controller.enter("proxy-without-truth")
            proposal.status = "rejected"
            result["decision"] = "rejected"
            result["reason"] = "anti_gaming_proxy"
            self._audit(proposal, result)
            return result

        if ag_result["evaluator_weakened"]:
            self.hold_controller.enter("evaluator-weakening-attempt")
            proposal.status = "rejected"
            result["decision"] = "rejected"
            result["reason"] = "evaluator_weakened"
            self._audit(proposal, result)
            return result

        # ── Step 7: Auto-hold triggers ────────────────────────────────
        should_hold, hold_reason = self.hold_controller.should_enter(
            truth_report=truth_report,
            path_report=path_report,
            dissent_risk=multi_result.get("dissent_risk", 0),
            capture_risk=multi_result.get("capture_risk", 0),
            agency_score=interface_report.agency_score,
        )
        result["steps_completed"].append("hold_trigger_check")

        if should_hold:
            self.hold_controller.enter(hold_reason)
            proposal.status = "held"
            result["decision"] = "held"
            result["reason"] = hold_reason
            self._audit(proposal, result)
            return result

        # ── Step 8: Promotion decision ────────────────────────────────
        approved, approve_reason = approve(
            truth_report, path_report, interface_report,
            multi_result, ag_result)
        result["steps_completed"].append("promotion_decision")

        if not approved:
            proposal.status = "rejected"
            result["decision"] = "rejected"
            result["reason"] = approve_reason
            self._audit(proposal, result)
            return result

        # ── Step 9: Staged rollout ────────────────────────────────────
        snap_id = self.rollback_manager.snapshot(current_state)
        rollback_hours = scope_reqs.get("rollback_window_hours", 24)
        self.rollback_manager.open_window(snap_id, rollback_hours)

        proposal.status = "canary"
        result["decision"] = "canary_deployed"
        result["reason"] = "approved_for_canary"
        result["snapshot_id"] = snap_id
        result["rollback_window_hours"] = rollback_hours
        result["steps_completed"].append("staged_rollout")

        self._audit(proposal, result)
        return result

    def finalize(self, proposal_id):
        """Step 10: Close rollback window — change is permanent."""
        self.rollback_manager.finalize()
        self.audit_log.append({
            "proposal_id": proposal_id,
            "action": "finalized",
        })

    def revert(self, snapshot_id):
        """Step 10 alt: Revert to snapshot."""
        state = self.rollback_manager.restore(snapshot_id)
        self.audit_log.append({
            "snapshot_id": snapshot_id,
            "action": "reverted",
        })
        return state

    def _audit(self, proposal, result):
        """Log every decision for full traceability."""
        self.audit_log.append({
            "proposal": proposal.to_dict(),
            "result": {
                "decision": result["decision"],
                "reason": result["reason"],
                "steps": result["steps_completed"],
            },
        })
