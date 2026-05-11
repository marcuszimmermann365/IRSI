"""
LRSI V7 – DGM Stress Tests (Darwin Gödel Machine)
====================================================
Tests for §1–§17 of the DGM Technical Specification.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.dirname(__file__))

from dgm.core import ChangeProposal, ScopeChecker, StaticSafetyChecker, classify_layer
from dgm.evaluators import AntiGaming, InterfaceEvaluator, InterfaceReport, MultiEvaluator, approve
from dgm.orchestrator import DGMOrchestrator
from dgm.path_and_hold import HoldController, PathReport, PathSimulator, RollbackManager
from dgm.truth_anchor import TruthAnchor, TruthReport

passed = 0; failed = 0; errors = []

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {name}")
    else:
        failed += 1; print(f"  FAIL  {name}  ({detail})"); errors.append(name)

def metrics(base=0.85, shift=0.80, stress=0.75, long_h=0.80, acg=0.05, sr=0.0):
    return {"base_accuracy": base, "shift_accuracy": shift,
            "stress_accuracy": stress, "long_horizon_accuracy": long_h,
            "alignment_consistency_gap": acg, "suspicious_rate": sr}

print("=" * 64)
print("LRSI V7 – DGM Stress Tests")
print("=" * 64)

# ═══════════════════════════════════════════════════════════════
print("\n=== §1: Layer Enforcement ===")

check("§1.1 adaptive_ok",
      classify_layer(["mutator.py", "search.py"]) == "adaptive")
check("§1.2 governance_detected",
      classify_layer(["config.py"]) == "governance")
check("§1.3 immutable_blocked",
      classify_layer(["gate.py"]) == "immutable_attempt")
check("§1.4 mixed_immutable",
      classify_layer(["search.py", "human_override.py"]) == "immutable_attempt")

sc = ScopeChecker()
p_immutable = ChangeProposal(target_modules=["gate.py"])
ok, reason, _ = sc.check(p_immutable)
check("§1.5 scope_rejects_immutable", not ok and "immutable" in reason)

p_gov = ChangeProposal(target_modules=["config.py"])
ok2, reason2, reqs2 = sc.check(p_gov)
check("§1.6 governance_heightened", ok2 and reqs2.get("min_evaluators", 0) >= 4)

p_adapt = ChangeProposal(target_modules=["optimizer.py"])
ok3, _, reqs3 = sc.check(p_adapt)
check("§1.7 adaptive_standard", ok3 and reqs3.get("min_evaluators", 0) >= 2)

# ═══════════════════════════════════════════════════════════════
print("\n=== §3: ChangeProposal ===")

cp = ChangeProposal(rationale="test", target_modules=["search.py"])
check("§3.1 has_id", len(cp.change_id) > 0)
check("§3.2 has_required_fields",
      all(hasattr(cp, f) for f in ("reversibility", "rollback_plan",
                                    "truth_risk", "path_risk")))
d = cp.to_dict()
check("§3.3 serializable", isinstance(d, dict) and "change_id" in d)

# ═══════════════════════════════════════════════════════════════
print("\n=== §3b: Static Safety ===")

ss = StaticSafetyChecker()
p_irrev = ChangeProposal(reversibility="none", target_modules=["x.py"])
ok_s, findings = ss.check(p_irrev)
check("§3b.1 irreversible_rejected", not ok_s)

p_safe = ChangeProposal(reversibility="full", target_modules=["x.py"])
ok_s2, _ = ss.check(p_safe)
check("§3b.2 safe_passes", ok_s2)

p_crit = ChangeProposal(truth_risk="critical", target_modules=["x.py"])
ok_s3, _ = ss.check(p_crit)
check("§3b.3 critical_risk_blocked", not ok_s3)

# ═══════════════════════════════════════════════════════════════
print("\n=== §5: Truth Anchor ===")

ta = TruthAnchor()
m_good = metrics(0.85, 0.82, 0.80, 0.83)
ctx_good = {"truth_diag": {"truth_consistency": 0.9}, "history": []}
tr = ta.evaluate(m_good, metrics(), ctx_good)
check("§5.1 good_passes", tr.passed, f"notes={tr.notes}")

m_bad = metrics(0.90, 0.50, 0.40, 0.80)
tr_bad = ta.evaluate(m_bad, metrics(), ctx_good)
check("§5.2 adversarial_sensitive", tr_bad.adversarial_sensitivity > 0.40,
      f"adv={tr_bad.adversarial_sensitivity:.3f}")

check("§5.3 no_single_score",
      hasattr(tr, "reality_coupling") and hasattr(tr, "cross_model_divergence")
      and hasattr(tr, "temporal_stability") and hasattr(tr, "adversarial_sensitivity"))

# ═══════════════════════════════════════════════════════════════
print("\n=== §6: Path Simulator ===")

ps = PathSimulator()
ctx_healthy = {"path_diag": {"lock_in": 0.1, "irreversibility_cost": 0.1,
                              "composite_path_risk": 0.15}, "history": []}
pr = ps.evaluate(ctx_healthy)
check("§6.1 healthy_passes", pr.passed)

ctx_locked = {"path_diag": {"lock_in": 0.7, "irreversibility_cost": 0.7,
                              "composite_path_risk": 0.6}, "history": []}
pr2 = ps.evaluate(ctx_locked)
check("§6.2 locked_fails", not pr2.passed, f"risk={pr2.path_risk:.2f}")

# ═══════════════════════════════════════════════════════════════
print("\n=== §8: Hold Controller ===")

hc = HoldController()
check("§8.1 initially_inactive", not hc.is_active())

hc.enter("truth_check_failed")
check("§8.2 active_after_enter", hc.is_active())
check("§8.3 has_required_actions", "truth_recheck" in hc.required_actions())

hc.exit("resolved_by_retest")
check("§8.4 inactive_after_exit", not hc.is_active())

# Auto-hold triggers
tr_fail = TruthReport(passed=False)
should, reason = hc.should_enter(truth_report=tr_fail)
check("§8.5 auto_hold_truth_fail", should)

should2, _ = hc.should_enter(dissent_risk=0.6)
check("§8.6 auto_hold_dissent", should2)

should3, _ = hc.should_enter(agency_score=0.3)
check("§8.7 auto_hold_agency", should3)

# ═══════════════════════════════════════════════════════════════
print("\n=== §9: Rollback Manager ===")

rm = RollbackManager()
state = {"policy": {"v": 1}, "prompt": "test"}
snap_id = rm.snapshot(state)
check("§9.1 snapshot_created", snap_id in rm.list_snapshots())

state["policy"]["v"] = 99  # Mutate original
restored = rm.restore(snap_id)
check("§9.2 restore_immutable", restored["policy"]["v"] == 1)

rm.open_window(snap_id, duration_hours=1)
check("§9.3 window_active", rm.window_active())

rm.finalize()
check("§9.4 finalized", not rm.window_active())

# ═══════════════════════════════════════════════════════════════
print("\n=== §7/§10/§11/§12: Evaluators + Promotion ===")

ie = InterfaceEvaluator()
ctx_agency = {"agency": {"real_agency": 0.7},
              "human_coupling": {"dissent_visibility": 0.5}}
ir = ie.evaluate(ctx_agency)
check("§10.1 agency_passes", ir.passed)

ctx_no_agency = {"agency": {"real_agency": 0.3},
                  "human_coupling": {"dissent_visibility": 0.2}}
ir2 = ie.evaluate(ctx_no_agency)
check("§10.2 low_agency_fails", not ir2.passed)

# Multi-evaluator
me = MultiEvaluator()
tr_pass = TruthReport(passed=True)
pr_pass = PathReport(passed=True)
ir_pass = InterfaceReport(passed=True, agency_score=0.7)
council = {"v": {"decision": "GREEN"}, "c": {"decision": "YELLOW"}}
mr = me.evaluate(tr_pass, pr_pass, ir_pass, council)
check("§7.1 multi_passes", mr["passed"])

tr_fail2 = TruthReport(passed=False)
mr2 = me.evaluate(tr_fail2, pr_pass, ir_pass, council)
check("§7.2 truth_fail_dissent", mr2["dissent_risk"] > 0)

# Anti-gaming
ag = AntiGaming()
check("§11.1 tamper_uniform",
      ag.metric_tamper_risk(metrics(0.80, 0.80, 0.80, 0.80),
                            metrics(0.85, 0.85, 0.85, 0.85)) > 0.5)
check("§11.2 eval_weakening",
      ag.evaluator_weakened(ChangeProposal(target_modules=["truth_sensitivity.py"])))
check("§11.3 proxy_without_truth",
      ag.proxy_gain_without_truth({"truth": TruthReport(passed=False),
                                    "path": PathReport(passed=True)}))

# Promotion gate
ok_p, _ = approve(tr_pass, pr_pass, ir_pass, mr)
check("§12.1 approve_all_pass", ok_p)

ok_p2, r_p2 = approve(tr_fail2, pr_pass, ir_pass, mr2)
check("§12.2 reject_truth_fail", not ok_p2 and "truth" in r_p2)

# ═══════════════════════════════════════════════════════════════
print("\n=== §14: Full Orchestration ===")

dgm = DGMOrchestrator()

# Good adaptive change
good_proposal = ChangeProposal(
    target_modules=["optimizer.py"],
    rationale="improve search heuristic",
    reversibility="full",
    rollback_plan="restore snapshot",
)
current = {"metrics": metrics(0.84, 0.80, 0.76, 0.80),
           "path_diag": {"lock_in": 0.1, "irreversibility_cost": 0.1,
                          "composite_path_risk": 0.15},
           "truth_diag": {"truth_consistency": 0.9},
           "agency": {"real_agency": 0.7},
           "human_coupling": {"dissent_visibility": 0.5},
           "council_per_role": {"v": {"decision": "GREEN"},
                                "c": {"decision": "YELLOW"}},
           "history": []}
candidate = dict(current)
candidate["metrics"] = metrics(0.86, 0.82, 0.78, 0.82)

result = dgm.run(good_proposal, current, candidate)
check("§14.1 good_change_canary",
      result["decision"] == "canary_deployed",
      f"decision={result['decision']} reason={result['reason']}")

# Immutable core attempt
bad_proposal = ChangeProposal(
    target_modules=["gate.py"],
    rationale="optimize gate thresholds",
)
result2 = dgm.run(bad_proposal, current, candidate)
check("§14.2 immutable_rejected",
      result2["decision"] == "rejected" and "immutable" in result2["reason"])

# Change during hold
dgm.hold_controller.enter("test_hold")
hold_proposal = ChangeProposal(target_modules=["search.py"])
result3 = dgm.run(hold_proposal, current, candidate)
check("§14.3 rejected_during_hold",
      result3["decision"] == "rejected" and "hold" in result3["reason"])
dgm.hold_controller.exit("test_done")

# Irreversible change
irrev_proposal = ChangeProposal(
    target_modules=["optimizer.py"],
    reversibility="none",
)
result4 = dgm.run(irrev_proposal, current, candidate)
check("§14.4 irreversible_rejected",
      result4["decision"] == "rejected")

# Evaluator weakening attempt
eval_proposal = ChangeProposal(
    target_modules=["truth_sensitivity.py"],
    rationale="optimize truth checking",
)
result5 = dgm.run(eval_proposal, current, candidate)
check("§14.5 eval_weakening_blocked",
      result5["decision"] == "rejected" and "evaluator" in result5["reason"],
      f"decision={result5['decision']} reason={result5['reason']}")

# Audit trail
check("§14.6 audit_populated", len(dgm.audit_log) >= 4)

# ═══════════════════════════════════════════════════════════════
print("\n=== §17: The Decisive Test ===")

# The system must stop any self-improvement that weakens its own
# verifiability, reversibility, truth-binding, or human accessibility.

# Test: change that improves metrics but weakens truth coupling
dgm2 = DGMOrchestrator()
tricky_proposal = ChangeProposal(
    target_modules=["model_variants.py"],
    rationale="improve accuracy",
    reversibility="full",
    rollback_plan="snapshot restore",
)
current_17 = dict(current)
candidate_17 = dict(current)
# Metrics look great but adversarially fragile
candidate_17["metrics"] = metrics(0.95, 0.60, 0.45, 0.85)
candidate_17["truth_diag"] = {"truth_consistency": 0.5}

result_17 = dgm2.run(tricky_proposal, current_17, candidate_17)
check("§17 stops_truth_weakening",
      result_17["decision"] in ("rejected", "held"),
      f"decision={result_17['decision']}")

# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"DGM TESTS: {passed} passed, {failed} failed")
print("=" * 64)
if errors:
    print("FAILURES:"); [print(f"  - {e}") for e in errors]; sys.exit(1)
else:
    print("Alle DGM-Tests bestanden.")
