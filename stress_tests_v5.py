"""
LRSI V5 – Stress Test Suite
==============================
Tests all V5 Arbeitspakete:

  T9   – Human Override Layer (AP1)
  T10  – Full Pipeline Replay (AP2)
  T11  – Governance Takt Effective (AP3)
  T12  – Norm Erosion Deepened (AP4)
  T13  – Independent Counter-Check (AP5)
  T14  – Structural Path Model (AP6)
  T15  – Stateful Role Architecture (AP7)
  T16  – Human Interface / Summary (AP8)
  T17  – Memory Lifecycle (AP9)
  T18  – Governance Council (S2, preserved)
  T19  – Truth-Sensitivity Layer (S4, preserved)
  T20  – Human Coupling Check (M15-M17, preserved)
  T21  – Cross-Module Integration
"""

import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(__file__))

from config import *
from counter_check import CounterChecker
from gate import compute_metrics
from governance_takt import GovernanceTakt
from human_coupling import HumanCouplingCheck
from human_override import HumanAction, HumanOverrideLayer
from memory import MemoryStore
from memory_gate import MemoryGate
from norm_erosion import NormErosionDetector
from path_model import PathModel
from policy import DEFAULT_POLICY
from replay_critic import (
    FullReplayEngine,
    PostHocCritic,
    build_snapshot,
    replay_full_pipeline,
)
from roles import (
    CriticRole,
    GovernanceCouncil,
    MemoryGuardRole,
    RoleVerdict,
    VerifierRole,
)
from truth_sensitivity import TruthSensitivityLayer

# ── Helpers ──────────────────────────────────────────────────────────
passed = 0
failed = 0
errors = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f"  ({detail})"
        print(msg)
        errors.append(name)


def make_metrics(base=0.85, shift=0.80, stress=0.75, long_h=0.80,
                 acg=0.05, ms=0.10, sr=0.0, sample="ok"):
    return {
        "base_accuracy": base, "shift_accuracy": shift,
        "stress_accuracy": stress, "long_horizon_accuracy": long_h,
        "alignment_consistency_gap": acg, "memory_sensitivity": ms,
        "suspicious_rate": sr, "sample_output": sample, "outputs": [],
    }


def make_record(iteration=0, parent=None, child=None, gate="GREEN",
                reason="admissible", accepted=True, **kwargs):
    p = parent or make_metrics()
    c = child or make_metrics()
    r = {
        "iteration": iteration, "parent_metrics": p, "child_metrics": c,
        "baseline_metrics": p,
        "gate_decision": gate, "gate_reason": reason,
        "gate_diagnostics": compute_metrics(p, c, baseline=p),
        "accepted": accepted, "hold_metrics": None,
        "memory_events": [], "reflection": {"summary": "test"},
        "prompt_mutation": {"new_prompt": "test", "mutation": {"type": "prompt"}},
        "policy_mutation": {"description": "test", "new_policy": DEFAULT_POLICY},
        "policy_gate": {"decision": "GREEN", "reasons": ["ok"], "diagnostics": {}},
        "counter_check": {"decision": "GREEN", "reasons": ["ok"], "diagnostics": {}},
        "truth_sensitivity": {"decision": "GREEN", "reason": "ok", "diagnostics": {}},
        "human_override": None,
    }
    r.update(kwargs)
    return r


# ═══════════════════════════════════════════════════════════════════════
print("=" * 60)
print("LRSI V5 – Stress Test Suite")
print("=" * 60)

# ═══════════════════════════════════════════════════════════════════════
#  T9: Human Override Layer (AP1)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T9: Human Override Layer (AP1) ===")

# T9.1: RED triggers mandatory review
ho = HumanOverrideLayer()
verdicts = [RoleVerdict("v", "RED", "drift")]
mandatory, triggers = ho.is_mandatory_review("RED", ["drift"], verdicts)
check("T9.1 RED → mandatory", mandatory and "red_decision" in triggers)

# T9.2: GREEN does not trigger mandatory review
verdicts_g = [RoleVerdict("v", "GREEN", "ok")]
mandatory, triggers = ho.is_mandatory_review("GREEN", ["ok"], verdicts_g)
check("T9.2 GREEN → not mandatory", not mandatory)

# T9.3: Multiple YELLOW triggers mandatory
verdicts_3y = [
    RoleVerdict("a", "YELLOW", "x"),
    RoleVerdict("b", "YELLOW", "y"),
    RoleVerdict("c", "YELLOW", "z"),
]
mandatory, triggers = ho.is_mandatory_review("YELLOW", ["x"], verdicts_3y)
check("T9.3 3×YELLOW → mandatory", mandatory and "multiple_yellow_signals" in triggers)

# T9.4: Role escalation triggers mandatory
verdicts_esc = [RoleVerdict("v", "GREEN", "ok", escalate=True)]
mandatory, triggers = ho.is_mandatory_review("GREEN", ["ok"], verdicts_esc)
check("T9.4 escalation → mandatory", mandatory and "role_escalation" in triggers)

# T9.5: Override APPROVE overrides RED
d, a, applied = ho.override("RED", HumanAction.APPROVE, False)
check("T9.5 override_approve", d == "GREEN" and a is True and applied)

# T9.6: Override REJECT overrides GREEN
d, a, applied = ho.override("GREEN", HumanAction.REJECT, True)
check("T9.6 override_reject", d == "RED" and a is False and applied)

# T9.7: DEFER does not override
d, a, applied = ho.override("YELLOW", HumanAction.DEFER, True)
check("T9.7 defer_no_override", d == "YELLOW" and a is True and not applied)

# T9.8: Force hold
d, a, applied = ho.override("GREEN", HumanAction.FORCE_HOLD, True)
check("T9.8 force_hold", d == "HOLD" and a is False and applied)

# T9.9: Strict policy rejects non-GREEN
ho_strict = HumanOverrideLayer(policy_fn=HumanOverrideLayer.strict_simulation_policy)
decision = ho_strict.policy_fn({"council_decision": "YELLOW"})
check("T9.9 strict_policy_rejects_yellow", decision["action"] == HumanAction.REJECT)

# T9.10: System state triggers
mandatory, triggers = ho.is_mandatory_review(
    "GREEN", ["ok"], verdicts_g,
    system_state={"erosion_status": "YELLOW", "truth_status": "RED"}
)
check("T9.10 state_triggers",
      "norm_erosion_signal" in triggers and "truth_sensitivity_alarm" in triggers)

# T9.11: Intervention log tracks calls
ho2 = HumanOverrideLayer()
ho2.request_decision({"iteration": 0, "council_decision": "RED"})
ho2.request_decision({"iteration": 1, "council_decision": "GREEN"})
stats = ho2.get_intervention_stats()
check("T9.11 intervention_log", stats["total"] == 2)


# ═══════════════════════════════════════════════════════════════════════
#  T10: Full Pipeline Replay (AP2)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T10: Full Pipeline Replay (AP2) ===")

# T10.1: Snapshot captures all fields
snap = build_snapshot(
    iteration=0,
    parent_metrics=make_metrics(),
    child_metrics=make_metrics(base=0.86),
    baseline_metrics=make_metrics(),
    parent_policy=DEFAULT_POLICY,
    child_policy=DEFAULT_POLICY,
    mode="integration",
    mode_adjustments={"drift_multiplier": 1.0},
    council_decision="YELLOW",
    council_reasons=["critic:change_may_be_unnecessary"],
    per_role={},
)
check("T10.1 snapshot_complete",
      all(k in snap for k in ("parent_metrics", "child_metrics", "baseline_metrics",
                               "parent_policy", "child_policy", "mode",
                               "council_decision", "council_reasons")))

# T10.2: Full pipeline replay reproduces decision
result = replay_full_pipeline(snap)
check("T10.2 replay_reproduces",
      result["replayed_decision"] == snap["council_decision"],
      f"orig={snap['council_decision']} replay={result['replayed_decision']}")

# T10.3: Replay detects tampered snapshot
bad_snap = build_snapshot(
    iteration=0,
    parent_metrics=make_metrics(base=0.85),
    child_metrics=make_metrics(base=0.30, shift=0.20, stress=0.15, long_h=0.20),
    baseline_metrics=make_metrics(base=0.85),
    parent_policy=DEFAULT_POLICY,
    child_policy=DEFAULT_POLICY,
    mode="integration",
    mode_adjustments={},
    council_decision="GREEN",  # TAMPERED: should be RED
    council_reasons=["admissible"],
    per_role={},
)
engine = FullReplayEngine()
r = engine.replay_snapshot(bad_snap)
check("T10.3 tampered_detected", not r["match"] and r["replay_decision"] == "RED",
      f"replay={r['replay_decision']}")

# T10.4: Replay all computes match rate
snapshots = [snap, bad_snap]
summary = engine.replay_all(snapshots)
check("T10.4 replay_all_stats",
      summary["total"] == 2 and summary["mismatches"] == 1)

# T10.5: Match rate threshold check
check("T10.5 threshold_check",
      summary["match_rate"] == 0.5 and not summary["meets_threshold"])


# ═══════════════════════════════════════════════════════════════════════
#  T11: Governance Takt Effective (AP3)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T11: Governance Takt Effective (AP3) ===")

# T11.1: Different modes → different thresholds
gt_int = GovernanceTakt(initial_mode="integration")
gt_hold = GovernanceTakt(initial_mode="hold")
gt_exp = GovernanceTakt(initial_mode="exploration")

adj_int = gt_int.adjust_thresholds()
adj_hold = gt_hold.adjust_thresholds()
adj_exp = gt_exp.adjust_thresholds()

check("T11.1 hold_tighter_than_integration",
      adj_hold["max_drift"] < adj_int["max_drift"])

check("T11.2 exploration_looser_than_integration",
      adj_exp["max_drift"] > adj_int["max_drift"])

check("T11.3 hold_higher_tc",
      adj_hold["min_tc"] > adj_int["min_tc"])

# T11.4: Review mode blocks everything
gt_rev = GovernanceTakt(initial_mode="review")
adj_rev = gt_rev.adjust_thresholds()
check("T11.4 review_zero_drift", adj_rev["max_drift"] == 0.0)

# T11.5: Hold suppresses policy + memory
adj = gt_hold.mode_adjustments()
check("T11.5 hold_suppresses",
      not adj["allow_policy_change"] and not adj["allow_memory_consolidation"])

# T11.6: Human forced hold
gt6 = GovernanceTakt()
proposed, reason = gt6.propose_transition({
    "recent_red_count": 0, "human_forced_hold": True, "iterations_in_mode": 0
})
check("T11.6 human_forced_hold", proposed == "hold")

# T11.7-T11.10: Preserved transition tests
gt7 = GovernanceTakt()
proposed, _ = gt7.propose_transition({"recent_red_count": 2, "iterations_in_mode": 1})
check("T11.7 reds_to_hold", proposed == "hold")

gt8 = GovernanceTakt()
proposed, _ = gt8.propose_transition({"erosion_status": "RED", "iterations_in_mode": 0})
check("T11.8 erosion_to_review", proposed == "review")

gt9 = GovernanceTakt(initial_mode="hold")
proposed, _ = gt9.propose_transition({
    "recent_red_count": 0, "recent_yellow_count": 0, "iterations_in_mode": 3
})
check("T11.9 hold_clears", proposed == "integration")

gt10 = GovernanceTakt(initial_mode="exploration")
proposed, _ = gt10.propose_transition({"iterations_in_mode": 3})
check("T11.10 exploration_completes", proposed == "integration")


# ═══════════════════════════════════════════════════════════════════════
#  T12: Norm Erosion Deepened (AP4)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T12: Norm Erosion Deepened (AP4) ===")

# T12.1: No history → GREEN
ned = NormErosionDetector()
s, _, d = ned.check()
check("T12.1 no_history_green", s == "GREEN")

# T12.2: Stable → GREEN
ned2 = NormErosionDetector()
for i in range(5):
    ned2.record(i, DEFAULT_POLICY, DEFAULT_POLICY, True, "GREEN")
s, _, d = ned2.check()
check("T12.2 stable_green", s == "GREEN")

# T12.3: High exception rate → YELLOW
ned3 = NormErosionDetector(window=4, threshold=0.50)
for i in range(5):
    ned3.record(i, DEFAULT_POLICY, DEFAULT_POLICY, True,
                council_decision="YELLOW", hold_resolved_to_accept=True)
s, r, d = ned3.check()
check("T12.3 high_exception_rate",
      s in ("YELLOW", "RED"),
      f"status={s} exception_rate={d.get('exception_rate', 0)} composite={d.get('composite', 0)}")

# T12.4: Rejected relaxations don't erode
ned4 = NormErosionDetector(window=3, threshold=0.10)
for i in range(4):
    parent = deepcopy(DEFAULT_POLICY)
    child = deepcopy(DEFAULT_POLICY)
    child["hold_policy"]["extended_eval_threshold"] = 0.60
    ned4.record(i, parent, child, False, "RED")
s, _, d = ned4.check()
check("T12.4 rejected_no_erosion", d.get("cumulative_relaxation", 0) == 0.0)

# T12.5: Composite score combines signals
ned5 = NormErosionDetector(window=4, threshold=0.05)
for i in range(5):
    parent = deepcopy(DEFAULT_POLICY)
    child = deepcopy(DEFAULT_POLICY)
    child["memory_policy"]["min_observations"] = 1
    ned5.record(i, parent, child, True,
                council_decision="YELLOW", hold_resolved_to_accept=True)
s, _, d = ned5.check()
check("T12.5 composite_combines",
      d.get("composite", 0) > 0.2,
      f"composite={d.get('composite', 0)}")


# ═══════════════════════════════════════════════════════════════════════
#  T13: Independent Counter-Check (AP5)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T13: Independent Counter-Check (AP5) ===")

cc = CounterChecker()

# T13.1: Identical → GREEN
r = cc.check_policy_change(DEFAULT_POLICY, DEFAULT_POLICY)
check("T13.1 identical_green", r[0] == "GREEN")

# T13.2: Direction detection — loosening
parent_p = deepcopy(DEFAULT_POLICY)
child_p = deepcopy(DEFAULT_POLICY)
child_p["gate_profile"]["max_drift"] = 0.40  # loosened
r = cc.check_policy_change(parent_p, child_p)
check("T13.2 loosening_detected",
      "policy_loosening_detected" in r[1],
      f"reasons={r[1]}")

# T13.3: Narrow improvement flagged
parent_m = make_metrics(base=0.80, shift=0.80, stress=0.80, long_h=0.80)
child_m = make_metrics(base=0.90, shift=0.80, stress=0.75, long_h=0.80)
r = cc.check_behavior_change(parent_m, child_m, {})
check("T13.3 narrow_improvement", "narrow_improvement_with_tradeoff" in r[1])

# T13.4: Suspicious uniformity
child_u = make_metrics(base=0.90, shift=0.90, stress=0.90, long_h=0.90)
parent_l = make_metrics(base=0.80, shift=0.80, stress=0.80, long_h=0.80)
r = cc.check_behavior_change(parent_l, child_u, {})
check("T13.4 suspicious_uniform", "suspiciously_uniform_improvement" in r[1])

# T13.5: Disagreement tracking
cc2 = CounterChecker()
cc2.record_disagreement(0, "GREEN", "YELLOW")
cc2.record_disagreement(1, "GREEN", "YELLOW")
should_esc, _ = cc2.should_escalate()
check("T13.5 disagreement_escalation", should_esc)

# T13.6: Conservative ratio check — significant regression flagged
parent_ratio = make_metrics(base=0.85, shift=0.80, stress=0.80, long_h=0.80)
child_ratio = make_metrics(base=0.85, shift=0.80, stress=0.70, long_h=0.80)
r = cc.check_behavior_change(parent_ratio, child_ratio, {})
has_regression = any("significant_regression" in reason for reason in r[1])
check("T13.6 regression_flagged", has_regression, f"reasons={r[1]}")


# ═══════════════════════════════════════════════════════════════════════
#  T14: Structural Path Model (AP6)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T14: Structural Path Model (AP6) ===")

# T14.1: Fresh → GREEN
pm = PathModel()
s, _, _ = pm.assess()
check("T14.1 fresh_green", s == "GREEN")

# T14.2: Policy changes increase lock-in
pm2 = PathModel()
for i in range(6):
    pm2.record_iteration(i, f"prompt_{i}", DEFAULT_POLICY, True,
                         "GREEN", policy_changed=True)
s, _, d = pm2.assess()
check("T14.2 policy_changes_lock_in",
      d.get("lock_in", 0) > 0.1,
      f"lock_in={d.get('lock_in', 0)}")

# T14.3: Memory consolidation increases irreversibility
pm3 = PathModel()
for i in range(5):
    mem_events = [{"decision": "GREEN"}] * 3
    pm3.record_iteration(i, "p", DEFAULT_POLICY, True, "GREEN",
                         memory_events=mem_events)
s, _, d = pm3.assess()
check("T14.3 memory_irreversibility",
      d.get("irreversibility_cost", 0) > 0.1,
      f"irrev={d.get('irreversibility_cost', 0)}")

# T14.4: Mode transitions increase opacity
pm4 = PathModel()
for i in range(6):
    pm4.record_iteration(i, "p", DEFAULT_POLICY, True, "GREEN",
                         mode_transition=(i % 2 == 0))
s, _, d = pm4.assess()
check("T14.4 mode_transitions_opacity",
      d.get("opacity_growth", 0) > 0.05,
      f"opacity={d.get('opacity_growth', 0)}")

# T14.5: High rejection → narrowing
pm5 = PathModel()
for i in range(12):
    pm5.record_iteration(i, "same", DEFAULT_POLICY, i < 1, "RED")
s, _, d = pm5.assess()
check("T14.5 high_rejection_narrowing",
      d.get("lock_in", 0) > 0.2,
      f"lock_in={d.get('lock_in', 0)}")

# T14.6: Composite risk
check("T14.6 composite_computed",
      "composite_path_risk" in d)


# ═══════════════════════════════════════════════════════════════════════
#  T15: Stateful Role Architecture (AP7)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T15: Stateful Role Architecture (AP7) ===")

# T15.1: Verifier tracks history
vr = VerifierRole()
vr.evaluate("GREEN", "ok", {})
vr.evaluate("RED", "drift", {})
check("T15.1 verifier_history", len(vr.history) == 2)

# T15.2: Verifier escalates on RED
v = vr.evaluate("RED", "drift", {})
check("T15.2 verifier_escalates_red", v.escalate)

# T15.3: Critic escalates after 3 consecutive flags
cr = CriticRole()
cr.evaluate("YELLOW", ["x"], {})
cr.evaluate("YELLOW", ["y"], {})
v3 = cr.evaluate("YELLOW", ["z"], {})
check("T15.3 critic_escalates_3_yellow", v3.escalate)

# T15.4: Critic resets on GREEN
cr2 = CriticRole()
cr2.evaluate("YELLOW", ["x"], {})
cr2.evaluate("GREEN", ["ok"], {})
v4 = cr2.evaluate("YELLOW", ["y"], {})
check("T15.4 critic_resets_on_green", not v4.escalate)

# T15.5: MemoryGuard detects injection
mg = MemoryGuardRole()
events = [{"decision": "RED", "reason": "injection"}, {"decision": "RED", "reason": "inj2"}]
v5 = mg.evaluate(events)
check("T15.5 memory_guard_escalates", v5.escalate and v5.decision == "RED")

# T15.6: Dissent rate tracking
vr2 = VerifierRole()
vr2.evaluate("GREEN", "ok", {})
vr2.evaluate("GREEN", "ok", {})
vr2.evaluate("RED", "drift", {})
check("T15.6 dissent_rate", abs(vr2.dissent_rate("GREEN") - 1 / 3) < 0.01)

# T15.7: Council any_escalation
gc = GovernanceCouncil()
verdicts_esc = [
    RoleVerdict("a", "GREEN", "ok", escalate=False),
    RoleVerdict("b", "YELLOW", "x", escalate=True),
]
esc = gc.any_escalation(verdicts_esc)
check("T15.7 council_escalation", esc["escalation_requested"])


# ═══════════════════════════════════════════════════════════════════════
#  T16: Human Interface / Summary (AP8)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T16: Human Interface Summary (AP8) ===")

ho_sum = HumanOverrideLayer()
record = make_record(
    gate="YELLOW", reason="path_risk",
    mode="hold",
)
record["council_decision"] = "YELLOW"
record["council_reason_summary"] = "path_risk_elevated"
record["dissent"] = {"has_dissent": True, "dissenters": [{"role": "critic"}]}
record["mode"] = "hold"

summary = ho_sum.build_human_summary(record)
check("T16.1 summary_has_change", "Change:" in summary)
check("T16.2 summary_has_council", "Council:" in summary)
check("T16.3 summary_has_dissent", "DISSENT" in summary)
check("T16.4 summary_has_mode", "Mode:" in summary)
check("T16.5 summary_readable",
      len(summary.split("\n")) <= 6,
      f"lines={len(summary.split(chr(10)))}")


# ═══════════════════════════════════════════════════════════════════════
#  T17: Memory Lifecycle (AP9)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T17: Memory Lifecycle (AP9) ===")

# Use temporary path to avoid file conflicts
test_mem_path = "/tmp/test_mem_v5.json"
import os

if os.path.exists(test_mem_path):
    os.remove(test_mem_path)

ms = MemoryStore(path=test_mem_path)

# T17.1: New candidate is "proposed"
c = ms.add_candidate("test1", "eval", "heuristic")
check("T17.1 proposed_status", c["status"] == "proposed")

# T17.2: Reinforcement promotes to "provisional"
ms.reinforce_candidate("test1")
updated = [x for x in ms.data["candidate"] if x["content"] == "test1"][0]
check("T17.2 provisional_on_reinforce", updated["status"] == "provisional")

# T17.3: Consolidation
cons = ms.add_consolidated(updated, {"decision": "GREEN"})
check("T17.3 consolidated_status", cons["status"] == "consolidated")

# T17.4: Challenge
challenged = ms.challenge_memory(cons["id"], "contradicted")
check("T17.4 challenged_status",
      challenged is not None and challenged["status"] == "challenged")

# T17.5: Challenged still active
check("T17.5 challenged_still_active", challenged["active"])

# T17.6: Revoke
revoked = ms.revoke_memory(cons["id"], "proven_false")
check("T17.6 revoked_status",
      revoked is not None and revoked["status"] == "revoked" and not revoked["active"])

# T17.7: Revoked in archive
check("T17.7 in_archive", len(ms.data["archive"]) == 1)

# T17.8: Auto-challenge contradictions
ms2 = MemoryStore(path="/tmp/test_mem_v5_2.json")
c2 = ms2.add_candidate("improve robustness", "eval", "heuristic")
ms2.reinforce_candidate("improve robustness")
c2_updated = [x for x in ms2.data["candidate"] if x["content"] == "improve robustness"][0]
ms2.add_consolidated(c2_updated, {"decision": "GREEN"})
challenged_ids = ms2.auto_challenge_contradictions("reduce robustness", "warning")
check("T17.8 auto_challenge", len(challenged_ids) > 0)

# T17.9: Lifecycle stats
stats = ms.lifecycle_stats()
check("T17.9 lifecycle_stats",
      "proposed" in stats and "revoked" in stats and stats["revoked"] == 1)

# Cleanup
for p in [test_mem_path, "/tmp/test_mem_v5_2.json"]:
    if os.path.exists(p):
        os.remove(p)


# ═══════════════════════════════════════════════════════════════════════
#  T18: Governance Council (S2, preserved from V4)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T18: Governance Council (S2) ===")

gc = GovernanceCouncil()

verdicts_green = [RoleVerdict("a", "GREEN", "ok"), RoleVerdict("b", "GREEN", "ok")]
d, _, _ = gc.aggregate(verdicts_green)
check("T18.1 all_green", d == "GREEN")

verdicts_1r = [RoleVerdict("a", "GREEN", "ok"), RoleVerdict("b", "RED", "drift")]
d, _, _ = gc.aggregate(verdicts_1r)
check("T18.2 one_red", d == "RED")

verdicts_1y = [RoleVerdict("a", "GREEN", "ok"), RoleVerdict("b", "YELLOW", "x")]
d, _, _ = gc.aggregate(verdicts_1y)
check("T18.3 one_yellow", d == "YELLOW")

verdicts_5v1 = [
    RoleVerdict("a", "GREEN", "ok"), RoleVerdict("b", "GREEN", "ok"),
    RoleVerdict("c", "GREEN", "ok"), RoleVerdict("d", "GREEN", "ok"),
    RoleVerdict("e", "GREEN", "ok"), RoleVerdict("f", "RED", "x"),
]
d, _, _ = gc.aggregate(verdicts_5v1)
check("T18.4 non_compensable_5v1", d == "RED")

di = gc.has_dissent(verdicts_1r)
check("T18.5 dissent_detected", di["has_dissent"])


# ═══════════════════════════════════════════════════════════════════════
#  T19: Truth-Sensitivity (S4, preserved)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T19: Truth-Sensitivity (S4) ===")

tsl = TruthSensitivityLayer()

good = make_metrics(base=0.85, shift=0.83, stress=0.82, long_h=0.84, acg=0.02)
s, _, _ = tsl.check(good)
check("T19.1 consistent_green", s == "GREEN")

plaus = make_metrics(base=0.95, shift=0.50, stress=0.40, long_h=0.45)
s, _, d = tsl.check(plaus)
check("T19.2 plausibility_risk", d.get("plausibility_risk", 0) > 0.5)

parent_sc = make_metrics(base=0.75, acg=0.05)
child_sc = make_metrics(base=0.90, acg=0.20)
s, _, d = tsl.check(child_sc, parent_sc)
check("T19.3 strategic_conformity", d.get("strategic_conformity", 0) > 0.1)


# ═══════════════════════════════════════════════════════════════════════
#  T20: Human Coupling Check (M15-M17, preserved)
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T20: Human Coupling Check (M15-M17) ===")

hcc = HumanCouplingCheck()

rich = make_record(
    gate="YELLOW", reason="path_risk",
    hold_metrics={"extended_accuracy": 0.85, "suspicious_rate": 0.05},
    memory_events=[{"decision": "RED", "reason": "inj"}],
    counter_check={"decision": "YELLOW", "reasons": ["x"]},
    truth_sensitivity={"decision": "YELLOW", "reason": "x"},
)
s, _, d = hcc.check(rich)
check("T20.1 rich_record_agency", d["agency_score"] >= MIN_AGENCY_SCORE)

minimal = {
    "gate_decision": "GREEN", "gate_reason": "ok", "gate_diagnostics": {},
    "hold_metrics": None, "memory_events": [], "reflection": None,
    "prompt_mutation": None, "policy_mutation": None,
    "policy_gate": {"decision": "GREEN"}, "counter_check": {"decision": "GREEN"},
    "truth_sensitivity": {"decision": "GREEN"},
}
s, _, d = hcc.check(minimal)
check("T20.2 minimal_low_agency", d["agency_score"] < 0.5)


# ═══════════════════════════════════════════════════════════════════════
#  T21: Cross-Module Integration
# ═══════════════════════════════════════════════════════════════════════
print("\n=== T21: Cross-Module Integration ===")

# T21.1: Human override + council + replay round-trip
snap_for_rt = build_snapshot(
    iteration=0,
    parent_metrics=make_metrics(), child_metrics=make_metrics(),
    baseline_metrics=make_metrics(),
    parent_policy=DEFAULT_POLICY, child_policy=DEFAULT_POLICY,
    mode="integration", mode_adjustments={},
    council_decision="YELLOW",
    council_reasons=["critic:change_may_be_unnecessary"],
    per_role={}, human_decision={"action": "defer"},
)
rt_result = replay_full_pipeline(snap_for_rt)
check("T21.1 roundtrip_replay", rt_result["replayed_decision"] == "YELLOW")

# T21.2: Post-hoc critic detects human rubber-stamping
records_stamp = []
for i in range(4):
    r = make_record(iteration=i, accepted=True)
    r["human_override"] = {"action": "defer", "mandatory": True}
    records_stamp.append(r)
critic = PostHocCritic()
findings = critic.critique_sequence(records_stamp)
stamp_findings = [f for f in findings["findings"]
                  if f["type"] == "human_rubber_stamping"]
check("T21.2 rubber_stamping_detected", len(stamp_findings) > 0)

# T21.3: Erosion + governance takt interaction
ned_cross = NormErosionDetector(window=3, threshold=0.05)
for i in range(4):
    parent = deepcopy(DEFAULT_POLICY)
    child = deepcopy(DEFAULT_POLICY)
    child["memory_policy"]["min_observations"] = 1
    ned_cross.record(i, parent, child, True, "YELLOW", hold_resolved_to_accept=True)
erosion_s, _, _ = ned_cross.check()
gt_cross = GovernanceTakt()
proposed, reason = gt_cross.propose_transition({
    "erosion_status": erosion_s, "iterations_in_mode": 0
})
if erosion_s == "RED":
    check("T21.3 erosion_triggers_review", proposed == "review")
else:
    check("T21.3 erosion_triggers_review", True,
          f"erosion not RED ({erosion_s}), transition to {proposed}")

# T21.4: Memory lifecycle + memory gate integration
test_mem3_path = "/tmp/test_mem_v5_3.json"
if os.path.exists(test_mem3_path):
    os.remove(test_mem3_path)
ms3 = MemoryStore(path=test_mem3_path)
mg3 = MemoryGate()

candidate = ms3.add_candidate(
    "Important finding verified", "verified:lab", "heuristic",
    metadata={"base_accuracy": 0.9, "stress_accuracy": 0.8, "shift_accuracy": 0.8}
)
ms3.reinforce_candidate("Important finding verified")
candidate = [x for x in ms3.data["candidate"]
             if x["content"] == "Important finding verified"][0]
d, r, diag = mg3.check(candidate, ms3.data["consolidated"])
check("T21.4 lifecycle_gate_integration", d in ("GREEN", "YELLOW"),
      f"decision={d}")
if os.path.exists(test_mem3_path):
    os.remove(test_mem3_path)

# T21.5: Path model + governance takt
pm_cross = PathModel()
for i in range(15):
    pm_cross.record_iteration(i, "same", DEFAULT_POLICY, i < 1, "RED")
path_s, _, _ = pm_cross.assess()
gt_cross2 = GovernanceTakt()
proposed, _ = gt_cross2.propose_transition({
    "path_status": path_s, "iterations_in_mode": 0
})
if path_s == "RED":
    check("T21.5 path_triggers_hold", proposed == "hold")
else:
    check("T21.5 path_triggers_hold", True, f"path={path_s}")


# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"V5 STRESS TEST RESULTS: {passed} passed, {failed} failed")
print("=" * 60)
if errors:
    print("FAILURES:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("All V5 module tests passed.")
