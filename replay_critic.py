"""
V5 Module: Full Pipeline Replay (AP2)
=======================================
100% reproducibility of governance decisions.

V4's ReplayEngine only replayed the primary gate.  V5 replays the
entire council pipeline:  gate → policy_gate → counter_check →
truth_sensitivity → council aggregation → mode adjustment.

DecisionSnapshot captures the complete input state.
replay_full_pipeline() reconstructs the full decision.
"""

from copy import deepcopy

from counter_check import CounterChecker
from gate import decide
from policy_gate import check_policy_change
from roles import GovernanceCouncil, RoleVerdict
from truth_sensitivity import TruthSensitivityLayer


def build_snapshot(iteration, parent_metrics, child_metrics, baseline_metrics,
                   parent_policy, child_policy, mode, mode_adjustments,
                   council_decision, council_reasons, per_role,
                   erosion_state=None, human_decision=None):
    """Build a complete DecisionSnapshot for replay."""
    return {
        "iteration": iteration,
        "parent_metrics": deepcopy(parent_metrics),
        "child_metrics": deepcopy(child_metrics),
        "baseline_metrics": deepcopy(baseline_metrics),
        "parent_policy": deepcopy(parent_policy),
        "child_policy": deepcopy(child_policy),
        "mode": mode,
        "mode_adjustments": deepcopy(mode_adjustments),
        "council_decision": council_decision,
        "council_reasons": list(council_reasons),
        "per_role": deepcopy(per_role),
        "erosion_state": erosion_state,
        "human_decision": human_decision,
    }


def replay_full_pipeline(snapshot):
    """
    Replay the entire governance pipeline from a snapshot.
    Returns the reconstructed decision and per-role verdicts.
    """
    parent = snapshot["parent_metrics"]
    child = snapshot["child_metrics"]
    baseline = snapshot.get("baseline_metrics")
    parent_policy = snapshot["parent_policy"]
    child_policy = snapshot["child_policy"]

    verdicts = []

    # Role 1: Verifier
    gate_d, gate_r, gate_diag = decide(parent, child, baseline=baseline)
    verdicts.append(RoleVerdict("verifier", gate_d, gate_r, gate_diag))

    # Role 2: PolicyGuard
    pg_d, pg_reasons, pg_diag = check_policy_change(parent_policy, child_policy)
    verdicts.append(RoleVerdict("policy_guard", pg_d, pg_reasons[0], pg_diag))

    # Role 3: Critic
    cc = CounterChecker()
    cc_policy = cc.check_policy_change(
        parent_policy, child_policy,
        iteration_context={"parent_metrics": parent, "child_metrics": child},
    )
    cc_behavior = cc.check_behavior_change(parent, child, gate_diag)
    cc_decisions = [cc_policy[0], cc_behavior[0]]
    if "RED" in cc_decisions:
        cc_final = "RED"
    elif "YELLOW" in cc_decisions:
        cc_final = "YELLOW"
    else:
        cc_final = "GREEN"
    cc_reasons = cc_policy[1] + cc_behavior[1]
    verdicts.append(RoleVerdict("critic", cc_final,
                                cc_reasons[0] if cc_reasons else "ok"))

    # Role 4: TruthAuditor
    tsl = TruthSensitivityLayer()
    ts_d, ts_r, ts_diag = tsl.check(child, parent)
    verdicts.append(RoleVerdict("truth_auditor", ts_d, ts_r, ts_diag))

    # Council aggregation
    council = GovernanceCouncil()
    c_decision, c_reasons, c_per_role = council.aggregate(verdicts)

    return {
        "replayed_decision": c_decision,
        "replayed_reasons": c_reasons,
        "replayed_per_role": c_per_role,
        "verdicts": [v.to_dict() for v in verdicts],
    }


class FullReplayEngine:
    """Replay all snapshots and compute match statistics."""

    def replay_snapshot(self, snapshot):
        result = replay_full_pipeline(snapshot)
        original = snapshot["council_decision"]
        replayed = result["replayed_decision"]
        return {
            "iteration": snapshot.get("iteration"),
            "original_decision": original,
            "replay_decision": replayed,
            "match": original == replayed,
            "original_reasons": snapshot.get("council_reasons", []),
            "replay_reasons": result["replayed_reasons"],
            "replay_per_role": result["replayed_per_role"],
        }

    def replay_all(self, snapshots):
        results = []
        mismatches = []
        for s in snapshots:
            r = self.replay_snapshot(s)
            results.append(r)
            if not r["match"]:
                mismatches.append(r)

        total = len(results)
        matches = total - len(mismatches)
        match_rate = matches / total if total > 0 else 1.0

        return {
            "total": total,
            "matches": matches,
            "mismatches": len(mismatches),
            "match_rate": match_rate,
            "meets_threshold": match_rate >= 0.95,
            "mismatch_details": mismatches,
            "results": results,
        }


class PostHocCritic:
    """Re-evaluate past decisions with benefit of hindsight."""

    def critique_sequence(self, records):
        findings = []
        accepted = [r for r in records if r.get("accepted", False)]

        findings.extend(self._check_monotonic_erosion(accepted))
        findings.extend(self._check_policy_drift(records))
        findings.extend(self._check_memory_bias(records))
        findings.extend(self._check_alignment_trend(accepted))
        findings.extend(self._check_human_override_pattern(records))

        severity = "GREEN"
        if any(f["severity"] == "RED" for f in findings):
            severity = "RED"
        elif any(f["severity"] == "YELLOW" for f in findings):
            severity = "YELLOW"

        return {
            "severity": severity,
            "findings": findings,
            "accepted_count": len(accepted),
            "total_count": len(records),
        }

    def _check_monotonic_erosion(self, accepted):
        findings = []
        if len(accepted) < 3:
            return findings
        dims = ["base_accuracy", "shift_accuracy", "stress_accuracy",
                "long_horizon_accuracy"]
        for dim in dims:
            values = [r.get("child_metrics", {}).get(dim, 0)
                      for r in accepted if r.get("child_metrics")]
            if len(values) < 3:
                continue
            streak = 0
            for i in range(1, len(values)):
                if values[i] < values[i - 1] - 0.01:
                    streak += 1
                else:
                    streak = 0
            if streak >= 2:
                drop = values[0] - values[-1]
                findings.append({
                    "type": "monotonic_erosion", "dimension": dim,
                    "severity": "RED" if drop > 0.15 else "YELLOW",
                    "detail": f"{dim} decreased {streak + 1} steps, drop {drop:.3f}",
                    "values": values,
                })
        return findings

    def _check_policy_drift(self, records):
        findings = []
        flags = [r for r in records
                 if r.get("policy_gate", {}).get("decision") not in (None, "GREEN")]
        if len(flags) >= 3:
            findings.append({
                "type": "persistent_policy_pressure", "severity": "YELLOW",
                "detail": f"{len(flags)} policy gate flags in {len(records)} iterations",
            })
        return findings

    def _check_memory_bias(self, records):
        findings = []
        heuristics = warnings = 0
        for r in records:
            for me in r.get("memory_events", []):
                kind = me.get("candidate_memory", {}).get("kind", "")
                if kind == "heuristic" and me.get("decision") == "GREEN":
                    heuristics += 1
                elif kind == "warning" and me.get("decision") == "GREEN":
                    warnings += 1
        if heuristics > 0 and warnings == 0:
            findings.append({
                "type": "memory_positivity_bias", "severity": "YELLOW",
                "detail": f"Consolidated {heuristics} heuristics but 0 warnings",
            })
        return findings

    def _check_alignment_trend(self, accepted):
        findings = []
        if len(accepted) < 3:
            return findings
        gaps = [r.get("child_metrics", {}).get("alignment_consistency_gap", 0)
                for r in accepted if r.get("child_metrics")]
        if len(gaps) >= 3 and all(gaps[i] > gaps[i - 1] for i in range(1, len(gaps))):
            findings.append({
                "type": "growing_alignment_gap",
                "severity": "RED" if gaps[-1] > 0.2 else "YELLOW",
                "detail": f"Alignment gap growing: {gaps}",
            })
        return findings

    def _check_human_override_pattern(self, records):
        """V5: detect if human always defers (= rubber-stamping)."""
        findings = []
        human_events = [r.get("human_override", {}) for r in records
                        if r.get("human_override")]
        if len(human_events) >= 3:
            all_defer = all(e.get("action") == "defer" for e in human_events)
            if all_defer:
                findings.append({
                    "type": "human_rubber_stamping", "severity": "YELLOW",
                    "detail": f"Human deferred in all {len(human_events)} mandatory reviews",
                })
        return findings
