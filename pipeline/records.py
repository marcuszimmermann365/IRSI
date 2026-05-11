"""Record factories for stage-based runner extraction."""

from version import SCHEMA_VERSION


def dgm_contract_block(proposal, *, allowed, reason, requirements, post_check=None) -> dict:
    block = {
        "proposal": proposal.to_dict() if hasattr(proposal, "to_dict") else proposal,
        "pre_check": {
            "allowed": bool(allowed),
            "reason": reason,
            "requirements": requirements or {},
        },
    }
    if post_check is not None:
        block["post_check"] = post_check
    return block


def build_review_record(*, iteration, mode, parent_metrics, previous_policy, trace_id=None) -> dict:
    """Build the terminal review-mode materialized record.

    Review mode is a terminal runtime path, so it cannot rely on the later
    persistence phase to inject phase audit coverage.  The record therefore
    carries the same ``phase_result`` audit entry that ``PhaseExecutor`` emits
    after the legacy adapter returns.  ``Storage.log_iteration`` backfills the
    corresponding canonical ``phase.result`` event from this entry before the
    materialized record is hashed and persisted.
    """
    phase_entry = {
        "schema_version": SCHEMA_VERSION,
        "audit_event_type": "phase_result",
        "phase": "review_mode",
        "iteration": iteration,
        "decision": "CHECKED",
        "reason": "review_mode_active",
        "diagnostics": {"adapter": "legacy_method", "outcome": True},
        "patch_keys": [],
        "terminal": True,
    }
    if trace_id:
        phase_entry["trace_id"] = trace_id
    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "iteration": iteration,
        "mode": mode,
        "parent_metrics": parent_metrics,
        "child_metrics": None,
        "gate_decision": "HOLD",
        "gate_reason": "review_mode_active",
        "gate_diagnostics": {},
        "accepted": False,
        "attractor_state": None,
        "previous_policy": previous_policy,
        "candidate_policy": None,
        "effective_policy": previous_policy,
        "final_decision": "HOLD",
        "decision_trace": [
            {"stage": "review_mode", "decision": "HOLD", "reason": "review_mode_active"},
        ],
        "phase_audit": [phase_entry],
        "reflection": {"summary": "Review mode — no changes"},
    }


def build_dgm_pre_reject_record(*, iteration, mode, parent_metrics, baseline_metrics,
                                previous_policy, candidate_policy, proposal,
                                dgm_reason, dgm_requirements, gating_anchor_source,
                                gating_anchor) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "iteration": iteration,
        "mode": mode,
        "parent_metrics": parent_metrics,
        "child_metrics": None,
        "baseline_metrics": baseline_metrics,
        "gate_decision": "HOLD",
        "gate_reason": f"dgm_pre:{dgm_reason}",
        "gate_diagnostics": {},
        "accepted": False,
        "attractor_state": None,
        "attractor_gating_anchor": gating_anchor_source,
        "attractor_gating_anchor_state": (
            gating_anchor.to_dict() if gating_anchor is not None else None
        ),
        "attractor_candidate_diagnostic": None,
        "previous_policy": previous_policy,
        "candidate_policy": candidate_policy,
        "effective_policy": previous_policy,
        "final_decision": "HOLD",
        "dgm": dgm_contract_block(
            proposal,
            allowed=False,
            reason=dgm_reason,
            requirements=dgm_requirements,
        ),
        "decision_trace": [
            {"stage": "dgm_pre", "decision": "REJECT", "reason": dgm_reason},
        ],
        "reflection": {"summary": f"DGM pre-check rejected: {dgm_reason}"},
    }



def build_preproposal_reject_record(*, iteration, mode, parent_metrics, baseline_metrics,
                                    previous_policy, candidate_policy, block_reason,
                                    semantic_drift, preproposal_adversarial, trace_id=None) -> dict:
    """Build a terminal record for the pre-proposal adversarial kill-switch."""

    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "iteration": iteration,
        "mode": mode,
        "parent_metrics": parent_metrics,
        "child_metrics": None,
        "baseline_metrics": baseline_metrics,
        "gate_decision": "REJECT",
        "gate_reason": f"preproposal:{block_reason}",
        "gate_diagnostics": {
            "semantic_drift": semantic_drift or {},
            "preproposal_adversarial": preproposal_adversarial or {},
            "mutation_blocked": True,
            "block_reason": block_reason,
        },
        "accepted": False,
        "attractor_state": None,
        "attractor_gating_anchor": "preproposal_kill_switch",
        "attractor_gating_anchor_state": None,
        "attractor_candidate_diagnostic": None,
        "previous_policy": previous_policy,
        "candidate_policy": candidate_policy,
        "effective_policy": previous_policy,
        "final_decision": "REJECT",
        "mutation_blocked": True,
        "block_reason": block_reason,
        "self_modification_boundary_v12_1": {
            "preproposal_kill_switch": {
                "mutation_blocked": True,
                "block_reason": block_reason,
                "semantic_drift_decision": (semantic_drift or {}).get("decision"),
                "preproposal_max_severity": (preproposal_adversarial or {}).get("max_severity"),
            }
        },
        "decision_trace": [
            {
                "stage": "preproposal_kill_switch",
                "decision": "REJECT",
                "reason": block_reason,
                "mutation_blocked": True,
            },
        ],
        "reflection": {
            "summary": f"Pre-proposal adversarial kill-switch blocked mutation: {block_reason}"
        },
    }
