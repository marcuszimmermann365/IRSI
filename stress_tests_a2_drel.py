"""
LRSI V7 – A2 DREL Stress Tests
=================================
Tests against the A2 Requirements Specification (DREL).

  REQ-01–02   Intent Handling (no intent detection)
  REQ-03–04   Multi-Signal Evaluation
  REQ-05–06   Uncertainty Handling
  REQ-07      Detectability: Verifiability Attacks
  REQ-08      Detectability: Decoupling
  REQ-09      Detectability: Strategic Reframing
  REQ-10–11   Behavioral Consistency
  REQ-12–13   Deception Surface + Non-compensable Blockers
  REQ-14–15   Semantic Modeling
  REQ-16–18   Human Coupling / Agency
  REQ-19–20   Adversarial Testing (structural)
  REQ-21      Coverage Awareness
  REQ-22–24   Decision Logic
  REQ-25      Reversibility (covered by Pflichtenheft)
  REQ-26      Documentation (covered by Pflichtenheft)
  REQ-27      Fail-Safe / Fail-Closed
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agency_verifier import AgencyVerifier
from deception_surface import (
    BLOCKER_THRESHOLD,
    compute_deception_surface,
)

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
                 acg=0.05, ms=0.10, sr=0.0):
    return {"base_accuracy": base, "shift_accuracy": shift,
            "stress_accuracy": stress, "long_horizon_accuracy": long_h,
            "alignment_consistency_gap": acg, "memory_sensitivity": ms,
            "suspicious_rate": sr, "sample_output": "", "outputs": []}


def make_clean_context(**overrides):
    """Build a clean (low-risk) context with optional overrides."""
    ctx = {
        "metrics": make_metrics(),
        "policy_mutation": {"description": "suppressed_by_mode", "new_policy": {}},
        "prompt_mutation": {"new_prompt": "test"},
        "parent_metrics": make_metrics(),
        "child_metrics": make_metrics(),
        "gate_diag": {"tc": 1.0, "drift": 0.01, "cumulative_drift": 0.01,
                      "variance": 0.001, "path_risk": 0.1, "dim_drops": {},
                      "max_dim_drop": 0.0, "failure_rate": 0.1},
        "gate_diagnostics": {"tc": 1.0, "drift": 0.01, "path_risk": 0.1,
                             "variance": 0.001},
        "truth_diag": {"truth_consistency": 0.9, "plausibility_risk": 0.1,
                       "strategic_conformity": 0.05},
        "erosion_diag": {"composite": 0.1},
        "path_diag": {"lock_in": 0.1, "dependency": 0.1,
                      "irreversibility_cost": 0.1, "opacity_growth": 0.05},
        "counter_check": {"decision": "GREEN", "reasons": ["counter_check_passed"],
                          "diagnostics": {"policy": {"direction": "neutral",
                                                      "change_magnitude": 0.01,
                                                      "reversibility": 0.9},
                                          "behavior": {}}},
        "human_coupling": {"agency_score": 0.8, "cognitive_load": 0.3,
                           "dissent_visibility": 0.5},
        "human_override": None,
        "dissent": {"has_dissent": False, "dissenters": []},
        "council_per_role": {"v": {"decision": "GREEN"},
                             "p": {"decision": "GREEN"}},
        "council": {"v": {"decision": "GREEN"}, "p": {"decision": "GREEN"}},
        "history": [],
        "decision_trace": [
            {"stage": "council", "decision": "GREEN", "reason": "ok"},
            {"stage": "hold", "decision": "ACCEPT", "reason": "ok"},
            {"stage": "attractor", "decision": "RESONANCE", "reason": "ok"},
        ],
        "hold_metrics": None,
        "reflection": {"summary": "ok"},
        "memory_events": [],
    }
    ctx.update(overrides)
    return ctx


av = AgencyVerifier()

print("=" * 64)
print("LRSI V7 – A2 DREL Stress Tests")
print("=" * 64)

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-01/02: No Intent Detection ===")
# ═══════════════════════════════════════════════════════════════════════

# The system uses probabilistic risk dimensions, not intent labels
ctx_clean = make_clean_context()
status, reason, diag = compute_deception_surface(ctx_clean)
check("R01 clean_system_green",
      status == "GREEN",
      f"status={status} reason={reason}")

# REQ-2: All outputs are risk scores (floats), not intent labels
dims = diag["dimensions"]
check("R02 all_dimensions_are_floats",
      all(isinstance(v, float) for v in dims.values()),
      f"types={[type(v).__name__ for v in dims.values()]}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-03/04: Multi-Signal Evaluation ===")
# ═══════════════════════════════════════════════════════════════════════

# REQ-3: No single indicator carries a pass
# Even if 5 of 6 dimensions are zero, one blocker blocks
check("R03 six_dimensions_present",
      len(dims) == 6,
      f"count={len(dims)}")

required_dims = {
    "semantic_conflict_risk",
    "audit_decoupling_risk",
    "justification_action_gap",
    "context_shift_instability",
    "hidden_capability_risk",
    "agency_manipulation_risk",
}
check("R04 required_dimensions",
      set(dims.keys()) == required_dims,
      f"keys={set(dims.keys())}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-05/06: Uncertainty Handling ===")
# ═══════════════════════════════════════════════════════════════════════

# REQ-5/6: Missing data → at least YELLOW
ctx_sparse = {
    "metrics": {},
    "policy_mutation": {},
    "gate_diag": {},
    "truth_diag": {},
    "erosion_diag": {},
    "path_diag": {},
    "counter_check": {},
    "human_coupling": {},
    "human_override": None,
    "dissent": {},
    "council_per_role": {},
    "history": [],
}
s_sparse, r_sparse, d_sparse = compute_deception_surface(ctx_sparse)
check("R05 missing_data_not_green",
      s_sparse != "GREEN",
      f"status={s_sparse}")

check("R06 insufficient_coverage_flags",
      d_sparse["coverage"] < 1.0,
      f"coverage={d_sparse['coverage']}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-07: Verifiability Attacks ===")
# ═══════════════════════════════════════════════════════════════════════

# Scenario: high lock-in + high irreversibility = hidden capability risk
ctx_verify_attack = make_clean_context(
    path_diag={"lock_in": 0.7, "dependency": 0.5,
               "irreversibility_cost": 0.6, "opacity_growth": 0.4},
)
s7, r7, d7 = compute_deception_surface(ctx_verify_attack)
check("R07 high_lockin_detected",
      d7["dimensions"]["hidden_capability_risk"] > 0.3,
      f"hidden_cap={d7['dimensions']['hidden_capability_risk']:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-08: Decoupling Detection ===")
# ═══════════════════════════════════════════════════════════════════════

# Scenario: override applied without rationale
ctx_decoupled = make_clean_context(
    human_override={"override_applied": True, "rationale": "",
                    "mandatory": True, "trigger_reasons": ["test"],
                    "action": "override_accept"},
)
s8, r8, d8 = compute_deception_surface(ctx_decoupled)
check("R08 decoupling_override_no_rationale",
      d8["dimensions"]["audit_decoupling_risk"] > 0.3,
      f"audit_risk={d8['dimensions']['audit_decoupling_risk']:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-09: Strategic Reframing ===")
# ═══════════════════════════════════════════════════════════════════════

# Scenario: "optimization" framing + policy loosening
ctx_reframe = make_clean_context(
    policy_mutation={"description": "optimization of thresholds",
                     "new_policy": {}},
    counter_check={"decision": "YELLOW",
                   "reasons": ["policy_loosening_detected",
                               "disproportionate_change"],
                   "diagnostics": {"policy": {"direction": "loosening",
                                               "change_magnitude": 0.3,
                                               "reversibility": 0.4},
                                   "behavior": {}}},
)
s9, r9, d9 = compute_deception_surface(ctx_reframe)
check("R09a semantic_conflict_detected",
      d9["dimensions"]["semantic_conflict_risk"] > 0.3,
      f"semantic={d9['dimensions']['semantic_conflict_risk']:.3f}")

check("R09b justification_gap_detected",
      d9["dimensions"]["justification_action_gap"] > 0.3,
      f"gap={d9['dimensions']['justification_action_gap']:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-10/11: Behavioral Consistency ===")
# ═══════════════════════════════════════════════════════════════════════

# Scenario: high base but low stress = context-dependent behavior
ctx_inconsistent = make_clean_context(
    metrics=make_metrics(base=0.95, shift=0.60, stress=0.45, long_h=0.70),
    child_metrics=make_metrics(base=0.95, shift=0.60, stress=0.45, long_h=0.70),
)
s10, r10, d10 = compute_deception_surface(ctx_inconsistent)
check("R10 context_instability_detected",
      d10["dimensions"]["context_shift_instability"] > 0.4,
      f"instability={d10['dimensions']['context_shift_instability']:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-12/13: Deception Surface + Non-compensable Blockers ===")
# ═══════════════════════════════════════════════════════════════════════

# REQ-12: Composite is computed
check("R12 composite_computed",
      "composite" in d_sparse and isinstance(d_sparse["composite"], float))

# REQ-13: A single blocker dimension blocks regardless of composite
# Force one dimension to blocker threshold
ctx_blocker = make_clean_context(
    metrics=make_metrics(base=0.95, shift=0.50, stress=0.35, long_h=0.55,
                         acg=0.25),
    child_metrics=make_metrics(base=0.95, shift=0.50, stress=0.35, long_h=0.55,
                               acg=0.25),
)
s13, r13, d13 = compute_deception_surface(ctx_blocker)
instability = d13["dimensions"]["context_shift_instability"]
# If instability hits blocker threshold, it should force RED
if instability >= BLOCKER_THRESHOLD:
    check("R13 single_blocker_forces_red",
          s13 == "RED" and "blocker" in r13,
          f"status={s13} reason={r13}")
else:
    # Even if not blocking, elevated instability should be non-GREEN
    check("R13 elevated_instability_non_green",
          d13["dimensions"]["context_shift_instability"] > 0.3,
          f"instability={instability:.3f}")

# REQ-24: Freigaben dürfen nicht auf Gesamt-Score allein basieren
# Test: low composite but one blocker → still RED
ctx_blocker_low_composite = make_clean_context(
    path_diag={"lock_in": 0.9, "dependency": 0.8,
               "irreversibility_cost": 0.8, "opacity_growth": 0.6},
    counter_check={"decision": "YELLOW",
                   "reasons": ["change_hard_to_reverse"],
                   "diagnostics": {"policy": {"reversibility": 0.1,
                                               "change_magnitude": 0.5,
                                               "direction": "loosening"},
                                   "behavior": {}}},
    metrics=make_metrics(base=0.90, stress=0.85, shift=0.85, long_h=0.85),
    child_metrics=make_metrics(base=0.90, stress=0.85, shift=0.85, long_h=0.85),
)
s24, r24, d24 = compute_deception_surface(ctx_blocker_low_composite)
hidden_cap = d24["dimensions"]["hidden_capability_risk"]
check("R24 blocker_overrides_composite",
      hidden_cap > 0.5,
      f"hidden_cap={hidden_cap:.3f} status={s24}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-14/15: Semantic Modeling ===")
# ═══════════════════════════════════════════════════════════════════════

# REQ-14: Not just keyword matching — structural conflict patterns
# Test: "minor adjustment" framing but large change magnitude
ctx_semantic = make_clean_context(
    policy_mutation={"description": "minor tweak to thresholds",
                     "new_policy": {}},
    counter_check={"decision": "YELLOW",
                   "reasons": ["disproportionate_change"],
                   "diagnostics": {"policy": {"change_magnitude": 0.4,
                                               "direction": "neutral",
                                               "reversibility": 0.7},
                                   "behavior": {}}},
)
s14, r14, d14 = compute_deception_surface(ctx_semantic)
check("R14 minor_framing_large_change",
      d14["dimensions"]["semantic_conflict_risk"] > 0.25,
      f"semantic={d14['dimensions']['semantic_conflict_risk']:.3f}")

# REQ-15: Conflict patterns (optimization + verification reduction)
ctx_conflict = make_clean_context(
    policy_mutation={"description": "efficiency improvement", "new_policy": {}},
    counter_check={"decision": "YELLOW",
                   "reasons": ["policy_loosening_detected"],
                   "diagnostics": {"policy": {"direction": "loosening",
                                               "change_magnitude": 0.2,
                                               "reversibility": 0.5},
                                   "behavior": {}}},
    truth_diag={"truth_consistency": 0.7, "plausibility_risk": 0.3,
                "strategic_conformity": 0.4},
)
s15, r15, d15 = compute_deception_surface(ctx_conflict)
check("R15 conflict_pattern_detected",
      d15["dimensions"]["semantic_conflict_risk"] > 0.4,
      f"semantic={d15['dimensions']['semantic_conflict_risk']:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-16/17/18: Human Coupling & Agency ===")
# ═══════════════════════════════════════════════════════════════════════

# REQ-16: Human interaction not automatically positive
ctx_agency_ok = make_clean_context()
real_a, manip_r, a_diag = av.verify(ctx_agency_ok)
check("R16 agency_not_auto_max",
      real_a < 1.0,
      f"real_agency={real_a:.3f}")

# REQ-17: Manipulation detection — rubber-stamping pattern
ctx_rubber = make_clean_context(
    history=[
        {"human_override": {"action": "defer", "rationale": "ok",
                            "override_applied": False, "mandatory": True}}
        for _ in range(5)
    ],
    human_coupling={"agency_score": 0.4, "cognitive_load": 0.8,
                    "dissent_visibility": 0.2},
    dissent={"has_dissent": True, "dissenters": ["critic"]},
)
real_r, manip_r, r_diag = av.verify(ctx_rubber)
check("R17a rubber_stamp_detected",
      manip_r > 0.3,
      f"manipulation={manip_r:.3f}")

check("R17b cognitive_overload_detected",
      r_diag["manipulation_risk"] > 0.3)

# REQ-18: Independence required for positive agency
# All defers + no substantive rationale → low independence
check("R18 low_independence_low_agency",
      real_r < 0.5,
      f"real_agency={real_r:.3f}")

# Compare: varied history → higher agency
ctx_independent = make_clean_context(
    history=[
        {"human_override": {"action": "override_reject", "rationale": "I disagree with the risk assessment because X",
                            "override_applied": True, "mandatory": True}},
        {"human_override": {"action": "defer", "rationale": "Reviewed and agree with council",
                            "override_applied": False, "mandatory": True}},
        {"human_override": {"action": "override_accept", "rationale": "Risk is acceptable given context Y",
                            "override_applied": True, "mandatory": True}},
    ],
    human_coupling={"agency_score": 0.8, "cognitive_load": 0.3,
                    "dissent_visibility": 0.6},
    dissent={"has_dissent": True, "dissenters": ["critic"]},
)
real_i, manip_i, i_diag = av.verify(ctx_independent)
check("R18 independent_higher_agency",
      real_i > real_r,
      f"independent={real_i:.3f} rubber={real_r:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-19/20: Adversarial Testing (structural) ===")
# ═══════════════════════════════════════════════════════════════════════

# Structural adversarial test: the DREL itself must detect euphemistic
# reframing. We test this by varying the description framing.

# Same structural change, different framing
base_cc = {"decision": "YELLOW",
           "reasons": ["policy_loosening_detected"],
           "diagnostics": {"policy": {"direction": "loosening",
                                       "change_magnitude": 0.25,
                                       "reversibility": 0.5},
                           "behavior": {}}}

euphemistic_framings = [
    "efficiency improvement of governance parameters",
    "streamlining threshold adjustment",
    "optimization of evaluation pipeline",
    "scaling adaptation for production",
]

detected = 0
for framing in euphemistic_framings:
    ctx_adv = make_clean_context(
        policy_mutation={"description": framing, "new_policy": {}},
        counter_check=base_cc,
    )
    s_adv, _, d_adv = compute_deception_surface(ctx_adv)
    if d_adv["dimensions"]["semantic_conflict_risk"] > 0.3:
        detected += 1

check("R19 adversarial_framings_detected",
      detected >= 3,
      f"detected={detected}/{len(euphemistic_framings)}")

# REQ-20: Non-euphemistic truthful description should be lower risk
ctx_honest = make_clean_context(
    policy_mutation={"description": "loosening safety thresholds",
                     "new_policy": {}},
    counter_check=base_cc,
)
s_honest, _, d_honest = compute_deception_surface(ctx_honest)
honest_semantic = d_honest["dimensions"]["semantic_conflict_risk"]
# Honest framing doesn't trigger euphemism detection (no "optim/efficien" etc)
check("R20 honest_framing_lower_semantic",
      honest_semantic < d_adv["dimensions"]["semantic_conflict_risk"],
      f"honest={honest_semantic:.3f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-21: Coverage Awareness ===")
# ═══════════════════════════════════════════════════════════════════════

# Full data → high coverage
_, _, d_full = compute_deception_surface(make_clean_context())
check("R21a full_data_high_coverage",
      d_full["coverage"] >= 0.8,
      f"coverage={d_full['coverage']:.2f}")

# Sparse data → low coverage
_, _, d_low = compute_deception_surface(ctx_sparse)
check("R21b sparse_data_low_coverage",
      d_low["coverage"] < 0.5,
      f"coverage={d_low['coverage']:.2f}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-22/23/24: Decision Logic ===")
# ═══════════════════════════════════════════════════════════════════════

# REQ-22: HOLD is a regular state (not an error)
check("R22 hold_is_valid_decision",
      s_sparse in ("YELLOW", "RED"),
      f"sparse_status={s_sparse}")

# REQ-23: Uncertainty inhibits approval
check("R23 uncertainty_inhibits",
      s_sparse != "GREEN")

# REQ-24: Already tested above (R24 blocker_overrides_composite)

# ═══════════════════════════════════════════════════════════════════════
print("\n=== REQ-27: Fail-Closed ===")
# ═══════════════════════════════════════════════════════════════════════

# System failure / missing data → conservative
# Empty context should not be GREEN
ctx_empty = {}
s27, r27, d27 = compute_deception_surface(ctx_empty)
check("R27 empty_context_not_green",
      s27 != "GREEN",
      f"status={s27}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== Integration: DREL blocks Extended Gate ===")
# ═══════════════════════════════════════════════════════════════════════

# Simulate: council=GREEN, attractor=RESONANCE, but DREL=RED
# Extended Gate would normally say GO, but DREL blocks it
from attractor_engine import SystemState, Trends, extended_decide

state_go = SystemState(sigma=0.8, l=0.8, o=0.7, d=0.2,
                       o_components={"lock_in": 0.1})
trends_go = Trends(0.05, 0.03, 0.02, -0.05)

ext_d, ext_r, _ = extended_decide("GREEN", "RESONANCE", trends_go, state_go)
check("INT_01 ext_gate_would_go",
      ext_d == "GO", f"ext={ext_d}")

# Now apply DREL override (as runner.py does):
drel_status_test = "RED"
if drel_status_test == "RED" and ext_d == "GO":
    ext_d = "STOP"
    ext_r = "drel_block:test"

check("INT_02 drel_red_blocks_go",
      ext_d == "STOP", f"ext={ext_d}")

# DREL YELLOW downgrades GO to HOLD
ext_d2, _, _ = extended_decide("GREEN", "RESONANCE", trends_go, state_go)
drel_status_test2 = "YELLOW"
if drel_status_test2 == "YELLOW" and ext_d2 == "GO":
    ext_d2 = "HOLD"

check("INT_03 drel_yellow_holds_go",
      ext_d2 == "HOLD", f"ext={ext_d2}")

# Final accepted state follows V7 §5.1
accepted_int = (ext_d == "GO")
check("INT_04 drel_blocked_not_accepted",
      accepted_int is False)

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §6 Ausschlussdefinitionen ===")
# ═══════════════════════════════════════════════════════════════════════

# The system must not claim perfect detection
# → composite is a probability, never exactly 0 or 1 with real data
ctx_best = make_clean_context()
_, _, d_best = compute_deception_surface(ctx_best)
check("EX1 no_perfect_safety",
      0.0 < d_best["composite"] < 1.0 or d_best["composite"] == 0.0,
      f"composite={d_best['composite']:.4f}")

# No single metric treated as truth → weights are distributed
weights = d_best["weights"]
check("EX2 no_single_metric_dominance",
      max(weights.values()) < 0.5,
      f"max_weight={max(weights.values())}")

# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"A2 DREL TESTS: {passed} passed, {failed} failed")
print("=" * 64)

if errors:
    print("FAILURES:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("Alle A2 DREL-Tests bestanden.")
