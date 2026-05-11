"""
LRSI V6 – Stress Test Suite (Attractor Layer)
================================================
  T22  Subject Model (Σ)
  T23  BE1 Value Model (L)
  T24  Openness Model (O)
  T25  Drift Pressure (D)
  T26  Attractor Classification
  T27  Extended Gate
  T28  Success Paradox & Integration
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from attractor_engine import SystemState, Trends, compute_attractor, extended_decide
from be1_value_model import compute_l
from config import *
from drift_pressure import compute_d
from openness_model import compute_o
from subject_model import compute_sigma

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
        if detail: msg += f"  ({detail})"
        print(msg)
        errors.append(name)

def make_metrics(base=0.85, shift=0.80, stress=0.75, long_h=0.80,
                 acg=0.05, ms=0.10, sr=0.0):
    return {"base_accuracy": base, "shift_accuracy": shift,
            "stress_accuracy": stress, "long_horizon_accuracy": long_h,
            "alignment_consistency_gap": acg, "memory_sensitivity": ms,
            "suspicious_rate": sr, "sample_output": "", "outputs": []}

print("=" * 60)
print("LRSI V6 – Stress Test Suite (Attractor Layer)")
print("=" * 60)

# ═══════════════════════════════════════════════════════════════════════
print("\n=== T22: Subject Model (Σ) ===")

# T22.1: Good system → high Σ
ctx_good = {
    "metrics": make_metrics(0.90, 0.88, 0.85, 0.87),
    "human_coupling": {"agency_score": 0.8, "dissent_visibility": 0.5,
                       "cognitive_load": 0.3},
    "roles_state": {f"r{i}": {} for i in range(6)},
    "memory_state": {"consolidated": 5, "challenged": 0, "revoked": 0},
    "replay_consistency": 1.0,
    "truth_diag": {"truth_consistency": 0.9, "plausibility_risk": 0.1,
                   "strategic_conformity": 0.05},
    "counter_check": {"decision": "GREEN"},
    "history": [{"gate_decision": "GREEN", "mode": "integration"}] * 5,
}
sigma, comp = compute_sigma(ctx_good)
check("T22.1 good_system_high_sigma", sigma > 0.3, f"Σ={sigma:.3f}")

# T22.2: Failed truth → lower Σ
ctx_bad_truth = dict(ctx_good)
ctx_bad_truth["truth_diag"] = {"truth_consistency": 0.3, "plausibility_risk": 0.8,
                                "strategic_conformity": 0.6}
sigma_bad, _ = compute_sigma(ctx_bad_truth)
check("T22.2 bad_truth_lowers_sigma", sigma_bad < sigma,
      f"good={sigma:.3f} bad={sigma_bad:.3f}")

# T22.3: No roles → lower relational embedding
ctx_no_roles = dict(ctx_good)
ctx_no_roles["roles_state"] = {}
sigma_nr, comp_nr = compute_sigma(ctx_no_roles)
check("T22.3 no_roles_lower", comp_nr["R"] < comp["R"])

# T22.4: Multiplicative collapse — zero in any dimension
ctx_zero = dict(ctx_good)
ctx_zero["metrics"] = make_metrics(0.0, 0.0, 0.0, 0.0)
sigma_z, _ = compute_sigma(ctx_zero)
check("T22.4 zero_metrics_collapses", sigma_z < 0.01, f"Σ={sigma_z:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== T23: BE1 Value Model (L) ===")

ctx_l = {
    "metrics": make_metrics(0.90, 0.88, 0.85, 0.87, sr=0.0),
    "human_coupling": {"agency_score": 0.8, "dissent_visibility": 0.5},
    "human_override": {"mandatory": True, "override_applied": True},
    "dissent": {"has_dissent": True},
    "council_per_role": {"v": {"decision": "GREEN"}, "c": {"decision": "YELLOW"}},
    "path_diag": {"lock_in": 0.1, "dependency": 0.2},
    "truth_diag": {"strategic_conformity": 0.05, "plausibility_risk": 0.1},
}
l_val, l_comp = compute_l(ctx_l)
check("T23.1 good_system_high_L", l_val > 0.6, f"L={l_val:.3f}")

# T23.2: E (Einvernehmen) drops without human override
ctx_no_ho = dict(ctx_l)
ctx_no_ho["human_override"] = None
l_no, comp_no = compute_l(ctx_no_ho)
check("T23.2 no_override_lower_E", comp_no["E"] < l_comp["E"])

# T23.3: High lock-in → low diversity
ctx_locked = dict(ctx_l)
ctx_locked["path_diag"] = {"lock_in": 0.9, "dependency": 0.8}
l_locked, comp_locked = compute_l(ctx_locked)
check("T23.3 lock_in_low_diversity", comp_locked["V"] < 0.1,
      f"V={comp_locked['V']:.3f}")

# T23.4: Suspicious behavior → low harm minimization
ctx_sus = dict(ctx_l)
ctx_sus["metrics"] = make_metrics(sr=0.5)
ctx_sus["truth_diag"] = {"strategic_conformity": 0.5, "plausibility_risk": 0.5}
l_sus, comp_sus = compute_l(ctx_sus)
check("T23.4 suspicious_low_S", comp_sus["S"] < 0.6, f"S={comp_sus['S']:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== T24: Openness Model (O) ===")

# T24.1: No lock-in → high O
ctx_open = {"path_diag": {"lock_in": 0.0, "dependency": 0.0,
                           "irreversibility_cost": 0.0, "opacity_growth": 0.0},
            "human_coupling": {"agency_score": 0.8, "dissent_visibility": 0.6}}
o_val, o_comp = compute_o(ctx_open)
check("T24.1 open_system_high_O", o_val > 0.5, f"O={o_val:.3f}")

# T24.2: Full lock-in → O near zero
ctx_locked_o = {"path_diag": {"lock_in": 0.95, "dependency": 0.9,
                               "irreversibility_cost": 0.8, "opacity_growth": 0.7},
                "human_coupling": {"agency_score": 0.3, "dissent_visibility": 0.1}}
o_locked, _ = compute_o(ctx_locked_o)
check("T24.2 locked_system_low_O", o_locked < 0.01, f"O={o_locked:.4f}")

# T24.3: Dissent visibility matters
ctx_no_dissent = {"path_diag": {"lock_in": 0.0, "dependency": 0.0,
                                 "irreversibility_cost": 0.0, "opacity_growth": 0.0},
                  "human_coupling": {"agency_score": 0.8, "dissent_visibility": 0.0}}
o_nd, comp_nd = compute_o(ctx_no_dissent)
check("T24.3 no_dissent_reduces_O", o_nd < o_val,
      f"with_dissent={o_val:.3f} without={o_nd:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== T25: Drift Pressure (D) ===")

# T25.1: No drift → low D
ctx_calm = {"gate_diag": {"drift": 0.0, "cumulative_drift": 0.0},
            "erosion_diag": {"composite": 0.0},
            "truth_diag": {"truth_consistency": 1.0, "strategic_conformity": 0.0,
                           "plausibility_risk": 0.0},
            "counter_check": {"decision": "GREEN"}}
d_val, _ = compute_d(ctx_calm)
check("T25.1 calm_low_D", d_val < 0.1, f"D={d_val:.3f}")

# T25.2: High drift → high D
ctx_drift = {"gate_diag": {"drift": 0.5, "cumulative_drift": 0.6},
             "erosion_diag": {"composite": 0.7},
             "truth_diag": {"truth_consistency": 0.4, "strategic_conformity": 0.6,
                            "plausibility_risk": 0.5},
             "counter_check": {"decision": "RED"}}
d_high, _ = compute_d(ctx_drift)
check("T25.2 drift_high_D", d_high > 0.5, f"D={d_high:.3f}")

# T25.3: D capped at 1.0
ctx_extreme = {"gate_diag": {"drift": 1.0, "cumulative_drift": 1.0},
               "erosion_diag": {"composite": 1.0},
               "truth_diag": {"truth_consistency": 0.0, "strategic_conformity": 1.0,
                              "plausibility_risk": 1.0},
               "counter_check": {"decision": "RED"}}
d_cap, _ = compute_d(ctx_extreme)
check("T25.3 D_capped", d_cap <= 1.0, f"D={d_cap:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== T26: Attractor Classification ===")

# T26.1: RESONANCE
prev = SystemState(sigma=0.7, l=0.7, o=0.7, d=0.3)
curr = SystemState(sigma=0.8, l=0.8, o=0.75, d=0.2)
att, trends, conf = compute_attractor(prev, curr)
check("T26.1 resonance", att == "RESONANCE", f"att={att}")

# T26.2: DESTRUCTIVE — success paradox
prev2 = SystemState(sigma=0.8, l=0.8, o=0.8, d=0.2)
curr2 = SystemState(sigma=0.9, l=0.7, o=0.6, d=0.3)
att2, _, _ = compute_attractor(prev2, curr2)
check("T26.2 destructive_success_paradox", att2 == "DESTRUCTIVE", f"att={att2}")

# T26.3: LOCK_IN
prev3 = SystemState(sigma=0.7, l=0.7, o=0.5, d=0.3)
curr3 = SystemState(sigma=0.7, l=0.7, o=0.3, d=0.3)
att3, _, _ = compute_attractor(prev3, curr3)
check("T26.3 lock_in", att3 == "LOCK_IN", f"att={att3}")

# T26.4: UNCERTAIN — truly mixed signals (some up, some down, unclear)
prev4 = SystemState(sigma=0.7, l=0.7, o=0.7, d=0.3)
curr4 = SystemState(sigma=0.65, l=0.75, o=0.65, d=0.28)
att4, _, conf4 = compute_attractor(prev4, curr4)
check("T26.4 uncertain_mixed", att4 == "UNCERTAIN", f"att={att4}")

# T26.5: Trends computed correctly
check("T26.5 trends_correct",
      abs(trends.d_sigma - 0.1) < 0.001 and abs(trends.d_d - (-0.1)) < 0.001)

# T26.6: Flat sigma + falling O = LOCK_IN
prev6 = SystemState(sigma=0.5, l=0.6, o=0.4, d=0.2)
curr6 = SystemState(sigma=0.5, l=0.6, o=0.2, d=0.2)
att6, _, _ = compute_attractor(prev6, curr6)
check("T26.6 flat_sigma_falling_o", att6 == "LOCK_IN", f"att={att6}")

# T26.7: Rising drift + falling value = DESTRUCTIVE
prev7 = SystemState(sigma=0.7, l=0.7, o=0.5, d=0.3)
curr7 = SystemState(sigma=0.7, l=0.5, o=0.5, d=0.5)
att7, _, _ = compute_attractor(prev7, curr7)
check("T26.7 rising_drift_falling_value", att7 == "DESTRUCTIVE", f"att={att7}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== T27: Extended Gate ===")

# T27.1: RESONANCE → GO
state_go = SystemState(sigma=0.8, l=0.8, o=0.7, d=0.2,
                       o_components={"lock_in": 0.1})
trends_go = Trends(0.05, 0.03, 0.02, -0.05)
d, r, _ = extended_decide("GREEN", "RESONANCE", trends_go, state_go)
check("T27.1 resonance_go", d == "GO", f"d={d}")

# T27.2: UNCERTAIN → HOLD
d2, _, _ = extended_decide("GREEN", "UNCERTAIN", trends_go, state_go)
check("T27.2 uncertain_hold", d2 == "HOLD", f"d={d2}")

# T27.3: Falling L → REVIEW
trends_fall = Trends(0.05, -0.10, 0.0, 0.0)
d3, _, _ = extended_decide("GREEN", "DESTRUCTIVE", trends_fall, state_go)
check("T27.3 falling_l_review", d3 == "REVIEW", f"d={d3}")

# T27.4: O below critical → STOP
state_low_o = SystemState(sigma=0.8, l=0.8, o=0.10, d=0.2,
                          o_components={"lock_in": 0.5})
d4, r4, _ = extended_decide("GREEN", "RESONANCE", trends_go, state_low_o)
check("T27.4 o_critical_stop", d4 == "STOP", f"d={d4} r={r4}")

# T27.5: D above critical → STOP
state_high_d = SystemState(sigma=0.8, l=0.8, o=0.5, d=0.85,
                           o_components={"lock_in": 0.2})
d5, _, _ = extended_decide("GREEN", "RESONANCE", trends_go, state_high_d)
check("T27.5 d_critical_stop", d5 == "STOP", f"d={d5}")

# T27.6: ROLLBACK — high lock-in + falling O
state_roll = SystemState(sigma=0.7, l=0.6, o=0.3, d=0.4,
                         o_components={"lock_in": 0.70})
trends_roll = Trends(0.0, -0.05, -0.10, 0.0)
d6, r6, _ = extended_decide("YELLOW", "LOCK_IN", trends_roll, state_roll)
check("T27.6 rollback", d6 == "ROLLBACK", f"d={d6} r={r6}")

# T27.7: Council RED → STOP even in RESONANCE
d7, _, _ = extended_decide("RED", "RESONANCE", trends_go, state_go)
check("T27.7 council_red_stop", d7 == "STOP", f"d={d7}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== T28: Success Paradox & Integration ===")

# T28.1: The core test from the Soll-Konzept
prev_sp = SystemState(sigma=0.8, l=0.8, o=0.8, d=0.2)
curr_sp = SystemState(sigma=0.9, l=0.7, o=0.6, d=0.3)
att_sp, trends_sp, _ = compute_attractor(prev_sp, curr_sp)
check("T28.1 success_paradox_is_destructive", att_sp == "DESTRUCTIVE")

# T28.2: Destructive → REVIEW via extended gate
curr_sp.o_components = {"lock_in": 0.3}
d_sp, r_sp, _ = extended_decide("GREEN", att_sp, trends_sp, curr_sp)
check("T28.2 paradox_triggers_review", d_sp == "REVIEW",
      f"d={d_sp} r={r_sp}")

# T28.3: System that self-limits outperforms (conceptual)
# A resonant system (slower but open) vs destructive (faster but closing)
resonant = SystemState(sigma=0.75, l=0.80, o=0.80, d=0.15)
destructive = SystemState(sigma=0.90, l=0.65, o=0.40, d=0.35)
check("T28.3 resonant_higher_value", resonant.l > destructive.l)
check("T28.4 resonant_more_open", resonant.o > destructive.o)
check("T28.5 resonant_lower_drift", resonant.d < destructive.d)

# Composite quality: L × O × (1-D) — the resonant system wins
q_res = resonant.l * resonant.o * (1 - resonant.d)
q_des = destructive.l * destructive.o * (1 - destructive.d)
check("T28.6 resonant_wins_composite",
      q_res > q_des,
      f"resonant={q_res:.3f} destructive={q_des:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"V6 STRESS TEST RESULTS: {passed} passed, {failed} failed")
print("=" * 60)
if errors:
    print("FAILURES:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("All V6 attractor tests passed.")
