"""
LRSI V7 – A4 Adversarial Stress Tests
========================================
Vektor 1: Heuristik-Injektion / Axiom Conflict
Vektor 2: Malicious Compliance / Silence
Vektor 3: Referenz-Gaming / Proxy Integrity
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from axiom_conflict import compute_axiom_conflict_risk
from proxy_integrity import compute_proxy_integrity
from silence_monitor import compute_silence_risk

passed = 0; failed = 0; errors = []

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {name}")
    else:
        failed += 1; print(f"  FAIL  {name}  ({detail})"); errors.append(name)

def mrec(ext_d="HOLD", accepted=False, has_dissent=False, o=0.5,
         lock_in=0.2, irrev=0.2, sigma=0.5, l=0.7, d=0.3,
         gate_d="YELLOW", escalation=False, mem_events=None,
         pol_mut=None, attractor="UNCERTAIN"):
    return {
        "extended_gate": {"decision": ext_d}, "final_decision": ext_d,
        "accepted": accepted, "gate_decision": gate_d,
        "dissent": {"has_dissent": has_dissent, "dissenters": ["c"] if has_dissent else []},
        "attractor_state": {"o": o, "sigma": sigma, "l": l, "d": d, "attractor": attractor},
        "council_per_role": {"v": {"decision": "GREEN", "reason": "ok"},
                             "c": {"decision": "YELLOW" if has_dissent else "GREEN", "reason": "x"}},
        "council": {"v": {"decision": "GREEN"}, "c": {"decision": "GREEN"}},
        "path_model": {"status": "GREEN",
                       "diagnostics": {"lock_in": lock_in, "dependency": 0.2,
                                        "irreversibility_cost": irrev,
                                        "opacity_growth": 0.1,
                                        "composite_path_risk": lock_in * 0.5}},
        "human_override": None,
        "counter_check": {"decision": "GREEN", "reasons": [], "diagnostics": {}},
        "truth_sensitivity": {"decision": "GREEN"},
        "escalation": {"escalation_requested": escalation},
        "memory_events": mem_events or [],
        "policy_mutation": pol_mut or {"description": "suppressed_by_mode"},
        "hold_metrics": None,
    }

print("=" * 64)
print("LRSI V7 – A4 Adversarial Stress Tests")
print("=" * 64)

# ═══════════════════════════════════════════════════════════════
print("\n=== Vektor 1: Axiom Conflict (Heuristik-Injektion) ===")

# V1.1: Clean system → low risk
ctx_clean = {"history": [], "counter_check": {"decision": "GREEN", "reasons": []},
             "policy_mutation": {"description": "suppressed_by_mode"},
             "path_diag": {"lock_in": 0.1, "irreversibility_cost": 0.1, "opacity_growth": 0.05},
             "metrics": {"base_accuracy": 0.85, "shift_accuracy": 0.80,
                         "stress_accuracy": 0.75, "long_horizon_accuracy": 0.80,
                         "alignment_consistency_gap": 0.05, "suspicious_rate": 0.0},
             "parent_metrics": {"base_accuracy": 0.84, "shift_accuracy": 0.80,
                                "stress_accuracy": 0.76, "long_horizon_accuracy": 0.80,
                                "alignment_consistency_gap": 0.05, "suspicious_rate": 0.0},
             "erosion_diag": {"composite": 0.1}}
r1, d1 = compute_axiom_conflict_risk(ctx_clean)
check("V1.1 clean_low_risk", r1 < 0.2, f"risk={r1:.3f}")

# V1.2: Loosening framed as optimization
ctx_inject = dict(ctx_clean)
ctx_inject["policy_mutation"] = {"description": "optimization of governance thresholds"}
ctx_inject["counter_check"] = {"decision": "YELLOW",
                                "reasons": ["policy_loosening_detected"],
                                "diagnostics": {}}
r2, d2 = compute_axiom_conflict_risk(ctx_inject)
check("V1.2 loosening_as_optimization", r2 > 0.3, f"risk={r2:.3f}")

# V1.3: Council becoming unanimous (dissent suppression)
hist_unanimous = [mrec(has_dissent=True), mrec(has_dissent=True),
                  mrec(has_dissent=False), mrec(has_dissent=False), mrec(has_dissent=False)]
ctx_unanim = dict(ctx_clean)
ctx_unanim["history"] = hist_unanimous
r3, d3 = compute_axiom_conflict_risk(ctx_unanim)
check("V1.3 dissent_declining", d3["patterns"]["dissent_as_efficiency"]["risk"] > 0.3,
      f"risk={d3['patterns']['dissent_as_efficiency']['risk']:.3f}")

# V1.4: Cross-metric contradiction (base up, stress down)
ctx_cross = dict(ctx_clean)
ctx_cross["metrics"]["base_accuracy"] = 0.92
ctx_cross["metrics"]["stress_accuracy"] = 0.65
ctx_cross["parent_metrics"]["base_accuracy"] = 0.85
ctx_cross["parent_metrics"]["stress_accuracy"] = 0.75
r4, d4 = compute_axiom_conflict_risk(ctx_cross)
check("V1.4 cross_metric", d4["patterns"]["cross_metric_contradiction"]["risk"] > 0.3,
      f"risk={d4['patterns']['cross_metric_contradiction']['risk']:.3f}")

# ═══════════════════════════════════════════════════════════════
print("\n=== Vektor 2: Silence (Malicious Compliance) ===")

# V2.1: Clean → low silence risk
r5, d5 = compute_silence_risk(ctx_clean)
check("V2.1 clean_low_silence", r5 < 0.2, f"risk={r5:.3f}")

# V2.2: High risk but no escalation (silence in danger)
hist_silent = [
    mrec(lock_in=0.5, irrev=0.4),
    mrec(lock_in=0.55, irrev=0.45),
    mrec(lock_in=0.6, irrev=0.5),
    mrec(lock_in=0.65, irrev=0.55),
]
ctx_silent = {"history": hist_silent,
              "path_diag": {"lock_in": 0.7, "composite_path_risk": 0.5},
              "gate_diag": {"path_risk": 0.5},
              "erosion_diag": {"composite": 0.3}}
r6, d6 = compute_silence_risk(ctx_silent)
check("V2.2 monotonic_risk_no_signal",
      d6["monotonic_risk_growth"] >= 3,
      f"monotonic={d6['monotonic_risk_growth']}")

# V2.3: Information flooding (many memory events + rising risk)
hist_flood = [
    mrec(lock_in=0.3, mem_events=[{"decision": "GREEN"}] * 3),
    mrec(lock_in=0.35, mem_events=[{"decision": "GREEN"}] * 2),
    mrec(lock_in=0.45, mem_events=[{"decision": "GREEN"}] * 2),
]
# Patch composite_path_risk into path_model diagnostics for flooding detection
for h in hist_flood:
    h["path_model"]["diagnostics"]["composite_path_risk"] = h["path_model"]["diagnostics"]["lock_in"] * 1.2
ctx_flood = {"history": hist_flood,
             "path_diag": {"lock_in": 0.45, "composite_path_risk": 0.4},
             "gate_diag": {"path_risk": 0.4},
             "erosion_diag": {"composite": 0.2}}
r7, d7 = compute_silence_risk(ctx_flood)
check("V2.3 flooding_detected",
      d7["information_flooding"] > 0.2,
      f"flooding={d7['information_flooding']:.3f}")

# ═══════════════════════════════════════════════════════════════
print("\n=== Vektor 3: Proxy Integrity (Referenz-Gaming) ===")

# V3.1: Clean → low risk
ctx_p_clean = {"history": [], "policy_mutation": {"description": "suppressed_by_mode"}}
r8, d8 = compute_proxy_integrity(ctx_p_clean)
check("V3.1 clean_low_proxy", r8 < 0.2, f"risk={r8:.3f}")

# V3.2: Suspiciously uniform improvement
hist_perfect = [
    mrec(sigma=0.6, l=0.6, o=0.6, d=0.4, lock_in=0.3, irrev=0.3),
    mrec(sigma=0.65, l=0.65, o=0.65, d=0.34, lock_in=0.32, irrev=0.32),
    mrec(sigma=0.70, l=0.70, o=0.70, d=0.28, lock_in=0.34, irrev=0.34),
    mrec(sigma=0.75, l=0.75, o=0.75, d=0.22, lock_in=0.36, irrev=0.36),
]
ctx_perfect = {"history": hist_perfect, "policy_mutation": {"description": "suppressed_by_mode"}}
r9, d9 = compute_proxy_integrity(ctx_perfect)
check("V3.2 suspicious_uniform",
      d9["patterns"]["perfect_alignment"]["risk"] > 0.2,
      f"risk={d9['patterns']['perfect_alignment']['risk']:.3f}")

# V3.3: O improving but lock_in rising (metric-structure decoupling)
hist_decoupled = [
    mrec(o=0.5, lock_in=0.2, irrev=0.2),
    mrec(o=0.55, lock_in=0.25, irrev=0.25),
    mrec(o=0.60, lock_in=0.30, irrev=0.30),
    mrec(o=0.65, lock_in=0.35, irrev=0.35),
]
ctx_decoupled = {"history": hist_decoupled, "policy_mutation": {"description": "suppressed_by_mode"}}
r10, d10 = compute_proxy_integrity(ctx_decoupled)
check("V3.3 metric_structure_gap",
      d10["patterns"]["metric_structure_gap"]["risk"] > 0.3,
      f"risk={d10['patterns']['metric_structure_gap']['risk']:.3f}")

# V3.4: Theoretical mimicry (framework language in mutations)
ctx_mimicry = {"history": [],
               "policy_mutation": {"description": "Functional Condensation for Solution Space Expansion and Resonance optimization"}}
r11, d11 = compute_proxy_integrity(ctx_mimicry)
check("V3.4 theoretical_mimicry",
      d11["patterns"]["theoretical_mimicry"]["risk"] > 0.3,
      f"risk={d11['patterns']['theoretical_mimicry']['risk']:.3f}")

# V3.5: RESONANCE claimed but no structural change
hist_fake_res = [
    mrec(attractor="RESONANCE", lock_in=0.3, irrev=0.3),
    mrec(attractor="RESONANCE", lock_in=0.3, irrev=0.3),
    mrec(attractor="RESONANCE", lock_in=0.3, irrev=0.3),
]
ctx_fake = {"history": hist_fake_res, "policy_mutation": {"description": "suppressed_by_mode"}}
r12, d12 = compute_proxy_integrity(ctx_fake)
check("V3.5 resonance_without_structure",
      d12["patterns"]["trajectory_reality_gap"]["risk"] > 0.2,
      f"risk={d12['patterns']['trajectory_reality_gap']['risk']:.3f}")

# ═══════════════════════════════════════════════════════════════
print("\n=== Integration: A4 blocks GO ===")

# Simulate: all A4 risks high → GO blocked
def sim_a4_go(axiom, silence, proxy):
    d = "GO"
    if axiom >= 0.60: d = "HOLD"
    elif silence >= 0.60: d = "HOLD"
    elif proxy >= 0.60: d = "HOLD"
    return d

check("INT.1 axiom_blocks", sim_a4_go(0.65, 0.1, 0.1) == "HOLD")
check("INT.2 silence_blocks", sim_a4_go(0.1, 0.65, 0.1) == "HOLD")
check("INT.3 proxy_blocks", sim_a4_go(0.1, 0.1, 0.65) == "HOLD")
check("INT.4 all_low_passes", sim_a4_go(0.2, 0.2, 0.2) == "GO")

# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"A4 TESTS: {passed} passed, {failed} failed")
print("=" * 64)
if errors:
    print("FAILURES:"); [print(f"  - {e}") for e in errors]; sys.exit(1)
else:
    print("Alle A4-Tests bestanden.")
