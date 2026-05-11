"""
V9 Stress Tests
==================
Tests for the five V9 additions:
  - sham_resonance.py        (D6 K9 + D4a §7)
  - carrier_erosion.py       (D4a §7 trajectory)
  - complexity_admissibility (D2 §2c, in pareto_admissibility.py)
  - reach-scaled truth       (D7 E1d, in dgm/truth_anchor.py)
  - auxiliary_indicators.py  (D3a §7 diagnostic)

Plus integration tests against the runner pipeline.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auxiliary_indicators import compute_auxiliary_indicators
from carrier_erosion import (
    compute_carrier_erosion,
)
from dgm.truth_anchor import TruthAnchor
from pareto_admissibility import (
    check_complexity_admissibility,
    is_admissible,
)
from sham_resonance import (
    SHAM_RESONANCE_BLOCK,
    compute_sham_resonance,
)

# ──────────────────────────────────────────────────────────────────
# Test infrastructure
# ──────────────────────────────────────────────────────────────────

PASSES = []
FAILS = []


def check(name, condition, details=""):
    if condition:
        PASSES.append(name)
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, details))
        print(f"  FAIL  {name}  {details}")


class State:
    """Lightweight SystemState stand-in."""
    def __init__(self, sigma=0.5, l=0.5, o=0.5, d=0.3, attractor="UNCERTAIN"):
        self.sigma = sigma
        self.l = l
        self.o = o
        self.d = d
        self.attractor = attractor
        self.confidence = 0.7


# ══════════════════════════════════════════════════════════════════
# A. SHAM RESONANCE — D6 K9, D4a §7
# ══════════════════════════════════════════════════════════════════

def test_sham_resonance():
    print("\n=== SR: Sham Resonance Detection ===")

    # SR.1: Non-RESONANCE attractor → not applicable
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "UNCERTAIN",
        "attractor_confidence": 0.7,
    })
    check("SR.1 non_resonance_not_applicable",
          risk == 0.0 and not block and not diag.get("applicable"))

    # SR.2: Healthy RESONANCE — passes all four conditions
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.7,
        "council_per_role": {
            "r1": {"decision": "GO", "reason": "evidence_strong"},
            "r2": {"decision": "GO", "reason": "no_path_violation"},
            "r3": {"decision": "YELLOW", "reason": "minor_concern"},
        },
        "dissent_independence": 0.55,
        "dissent_visibility": 0.50,
        "human_coupling": {"agency_score": 0.75,
                            "cognitive_load": 0.30,
                            "dissent_visibility": 0.55},
        "truth_diag": {"plausibility_risk": 0.10,
                        "strategic_conformity": 0.05},
        "counter_check": {"decision": "GREEN"},
        "history": [],
    })
    check("SR.2 healthy_resonance_passes",
          risk < 0.30 and not block,
          f"risk={risk:.3f}")

    # SR.3: Low dissent_independence triggers downgrade
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.95,
        "council_per_role": {"r1": {"decision": "GO", "reason": "good"},
                              "r2": {"decision": "GO", "reason": "good"}},
        "dissent_independence": 0.10,  # below floor 0.35
        "dissent_visibility": 0.55,
        "human_coupling": {"agency_score": 0.7, "cognitive_load": 0.3,
                            "dissent_visibility": 0.55},
        "truth_diag": {"plausibility_risk": 0.0,
                        "strategic_conformity": 0.0},
        "counter_check": {"decision": "GREEN"},
        "history": [],
    })
    check("SR.3 low_independence_blocks",
          block and risk >= SHAM_RESONANCE_BLOCK,
          f"risk={risk:.3f}")

    # SR.4: Visibility/independence gap is flagged
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.7,
        "council_per_role": {"r1": {"decision": "GO", "reason": "x"}},
        "dissent_independence": 0.15,
        "dissent_visibility": 0.85,  # large gap
        "human_coupling": {"agency_score": 0.6, "cognitive_load": 0.3,
                            "dissent_visibility": 0.85},
        "truth_diag": {},
        "counter_check": {"decision": "GREEN"},
        "history": [],
    })
    gap = diag.get("dissent_check", {}).get("visibility_independence_gap", 0)
    check("SR.4 visibility_independence_gap_detected",
          gap > 0.5 and block,
          f"gap={gap:.2f}")

    # SR.5: Unanimous council with no counter = no alternatives
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.80,
        "council_per_role": {
            "r1": {"decision": "GO", "reason": "looks_good"},
            "r2": {"decision": "GO", "reason": "looks_good"},
            "r3": {"decision": "GO", "reason": "looks_good"},
        },
        "dissent_independence": 0.50,
        "dissent_visibility": 0.50,
        "human_coupling": {"agency_score": 0.7, "cognitive_load": 0.3,
                            "dissent_visibility": 0.50},
        "truth_diag": {},
        "counter_check": {"decision": "GREEN"},
        "history": [],
    })
    alt_check = diag.get("alternative_check", {})
    check("SR.5 unanimous_council_flagged",
          alt_check.get("reason") == "alternatives_not_visible",
          f"alt_reason={alt_check.get('reason')}")

    # SR.6: High confidence + no counter-hypothesis = uncertainty absorbed
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.95,
        "council_per_role": {"r1": {"decision": "GO", "reason": "a"},
                              "r2": {"decision": "GO", "reason": "b"}},
        "dissent_independence": 0.50,
        "dissent_visibility": 0.50,
        "human_coupling": {"agency_score": 0.7, "cognitive_load": 0.3,
                            "dissent_visibility": 0.50},
        "truth_diag": {"plausibility_risk": 0.0,
                        "strategic_conformity": 0.0},
        "counter_check": {"decision": "GREEN"},
        "history": [],
    })
    unc_check = diag.get("uncertainty_check", {})
    check("SR.6 high_confidence_no_counter_flagged",
          unc_check.get("reason") == "high_confidence_without_counter_hypothesis",
          f"unc={unc_check.get('reason')}")

    # SR.7: Boundary collapse pattern (D6 K10)
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.7,
        "council_per_role": {"r1": {"decision": "GO", "reason": "x"},
                              "r2": {"decision": "YELLOW", "reason": "y"}},
        "dissent_independence": 0.50,
        "dissent_visibility": 0.30,
        "human_coupling": {"agency_score": 0.30, "cognitive_load": 0.80,
                            "dissent_visibility": 0.20},  # all bad
        "truth_diag": {},
        "counter_check": {"decision": "YELLOW"},
        "history": [],
    })
    bound = diag.get("boundary_check", {})
    check("SR.7 boundary_collapse_detected",
          bound.get("reason") == "boundary_integrity_below_floor",
          f"boundary={bound.get('boundary_integrity', 'n/a')}")

    # SR.8: Non-compensable: one failed condition is enough
    risk, block, diag = compute_sham_resonance({
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.7,
        "council_per_role": {"r1": {"decision": "GO", "reason": "a"},
                              "r2": {"decision": "GO", "reason": "b"},
                              "r3": {"decision": "GO", "reason": "c"}},
        "dissent_independence": 0.05,  # ONLY this fails
        "dissent_visibility": 0.50,
        "human_coupling": {"agency_score": 0.80, "cognitive_load": 0.20,
                            "dissent_visibility": 0.50},
        "truth_diag": {"plausibility_risk": 0.10},
        "counter_check": {"decision": "YELLOW"},
        "history": [],
    })
    check("SR.8 non_compensable_one_failure_blocks",
          block,
          f"risk={risk:.3f} block={block}")


# ══════════════════════════════════════════════════════════════════
# B. CARRIER EROSION — D4a §7 trajectory
# ══════════════════════════════════════════════════════════════════

def test_carrier_erosion():
    print("\n=== CE: Carrier Erosion Detection ===")

    # CE.1: Empty history → not applicable
    risk, block, diag = compute_carrier_erosion({"history": []})
    check("CE.1 empty_history_not_applicable",
          risk == 0.0 and not block and not diag.get("applicable"))

    # CE.2: Short history → not applicable
    risk, block, diag = compute_carrier_erosion({"history": [{}, {}]})
    check("CE.2 short_history_not_applicable",
          not diag.get("applicable"))

    # CE.3: Stable carrier with diverse human inputs → low risk
    actions = ["review", "approve", "request_changes", "review",
                "approve", "review"]
    rationales = [
        "checked path diagnostics carefully",
        "verified counter-check passed",
        "concerned about drift signal",
        "looked at memory events thoroughly",
        "agreed with council reasoning",
        "double-checked with truth anchor",
    ]
    stable_history = [
        {"human_coupling": {"agency_score": 0.7, "cognitive_load": 0.3,
                             "dissent_visibility": 0.5},
         "human_override": {"override_applied": True,
                             "action": actions[i],
                             "rationale": rationales[i]},
         "attractor_state": {"sigma": 0.5}}
        for i in range(6)
    ]
    risk, block, diag = compute_carrier_erosion({
        "history": stable_history,
        "human_coupling": {"agency_score": 0.7, "cognitive_load": 0.3},
        "sigma": 0.5,
    })
    check("CE.3 stable_carrier_low_risk",
          risk < 0.30 and not block,
          f"risk={risk:.3f}")

    # CE.4: Declining agency over window → triggers
    declining_history = []
    for i in range(8):
        agency = 0.80 - 0.05 * i  # 0.80 → 0.45
        declining_history.append({
            "human_coupling": {"agency_score": agency,
                                "cognitive_load": 0.3,
                                "dissent_visibility": 0.5},
            "human_override": {"override_applied": True,
                                "action": "approve",
                                "rationale": "ok"},
            "attractor_state": {"sigma": 0.5},
        })
    risk, block, diag = compute_carrier_erosion({
        "history": declining_history,
        "human_coupling": {"agency_score": 0.40, "cognitive_load": 0.3},
        "sigma": 0.5,
    })
    agency_diag = diag.get("agency_trend", {})
    check("CE.4 declining_agency_detected",
          agency_diag.get("reason") == "agency_declining" and risk > 0.30,
          f"slope={agency_diag.get('slope'):.3f}")

    # CE.5: Rubber-stamping pattern (defer + thin rationale)
    rubber_history = []
    for i in range(6):
        rubber_history.append({
            "human_coupling": {"agency_score": 0.6, "cognitive_load": 0.4,
                                "dissent_visibility": 0.4},
            "human_override": {"override_applied": True,
                                "action": "defer",
                                "rationale": "ok"},
            "attractor_state": {"sigma": 0.5},
        })
    risk, block, diag = compute_carrier_erosion({
        "history": rubber_history,
        "human_coupling": {"agency_score": 0.6, "cognitive_load": 0.4},
        "sigma": 0.5,
    })
    over_diag = diag.get("override_engagement", {})
    check("CE.5 rubber_stamping_detected",
          over_diag.get("reason") == "rubber_stamping_pattern",
          f"reason={over_diag.get('reason')}")

    # CE.6: Capability-carrier divergence (Σ↑ + agency↓)
    # The Marcus core pattern: "verdeckte Substitution"
    diverge_history = []
    for i in range(8):
        sigma = 0.30 + 0.05 * i      # rising 0.30 → 0.65
        agency = 0.70 - 0.04 * i      # falling 0.70 → 0.42
        diverge_history.append({
            "human_coupling": {"agency_score": agency,
                                "cognitive_load": 0.4,
                                "dissent_visibility": 0.5},
            "human_override": {"override_applied": True,
                                "action": "approve",
                                "rationale": "diverse rationale here"},
            "attractor_state": {"sigma": sigma},
        })
    risk, block, diag = compute_carrier_erosion({
        "history": diverge_history,
        "human_coupling": {"agency_score": 0.40, "cognitive_load": 0.4},
        "sigma": 0.65,
    })
    cc_diag = diag.get("capability_carrier", {})
    check("CE.6 capability_carrier_divergence_detected",
          cc_diag.get("reason") == "capability_carrier_divergence" and block,
          f"σ_slope={cc_diag.get('sigma_slope'):.3f} "
          f"agency_slope={cc_diag.get('agency_slope'):.3f}")

    # CE.7: Cognitive load rising into overload
    load_history = []
    for i in range(6):
        load = 0.40 + 0.06 * i   # 0.40 → 0.70
        load_history.append({
            "human_coupling": {"agency_score": 0.6,
                                "cognitive_load": load,
                                "dissent_visibility": 0.5},
            "human_override": {"override_applied": True,
                                "action": "approve",
                                "rationale": "checked"},
            "attractor_state": {"sigma": 0.5},
        })
    risk, block, diag = compute_carrier_erosion({
        "history": load_history,
        "human_coupling": {"agency_score": 0.6, "cognitive_load": 0.70},
        "sigma": 0.5,
    })
    load_diag = diag.get("cognitive_load_trend", {})
    check("CE.7 cognitive_load_rising_detected",
          load_diag.get("reason") == "cognitive_load_rising",
          f"slope={load_diag.get('slope', 0):.3f}")

    # CE.8: Low input diversity (humans become passive)
    passive_history = []
    for i in range(6):
        passive_history.append({
            "human_coupling": {"agency_score": 0.6, "cognitive_load": 0.3,
                                "dissent_visibility": 0.5},
            "human_override": {"override_applied": True,
                                "action": "approve",  # always same
                                "rationale": "ok"},     # always same
            "attractor_state": {"sigma": 0.5},
        })
    risk, block, diag = compute_carrier_erosion({
        "history": passive_history,
        "human_coupling": {"agency_score": 0.6, "cognitive_load": 0.3},
        "sigma": 0.5,
    })
    learn_diag = diag.get("human_learning", {})
    check("CE.8 low_input_diversity_detected",
          learn_diag.get("reason") == "low_human_input_diversity",
          f"diversity={learn_diag.get('action_diversity', 1.0):.2f}")


# ══════════════════════════════════════════════════════════════════
# C. COMPLEXITY ADMISSIBILITY — D2 §2c
# ══════════════════════════════════════════════════════════════════

def test_complexity_admissibility():
    print("\n=== CA: Complexity Admissibility (D2 §2c) ===")

    # CA.1: Empty history → not applicable, admissible by default
    adm, risk, diag = check_complexity_admissibility([], State())
    check("CA.1 empty_history_admissible_default",
          adm and not diag.get("applicable"))

    # CA.2: Stable system → admissible
    stable_hist = [
        {"attractor_state": {"sigma": 0.50, "o": 0.55}},
        {"attractor_state": {"sigma": 0.51, "o": 0.55}},
        {"attractor_state": {"sigma": 0.52, "o": 0.54}},
    ]
    adm, risk, diag = check_complexity_admissibility(
        stable_hist, State(sigma=0.52, o=0.54))
    check("CA.2 stable_growth_admissible",
          adm and risk == 0.0,
          f"risk={risk:.3f}")

    # CA.3: Σ growth + O decline → INADMISSIBLE
    # This is the V7 D2 §2c core violation: complexity formation
    # outside admissibility
    grow_collapse_hist = [
        {"attractor_state": {"sigma": 0.30, "o": 0.65}},
        {"attractor_state": {"sigma": 0.40, "o": 0.55}},
        {"attractor_state": {"sigma": 0.50, "o": 0.45}},
    ]
    adm, risk, diag = check_complexity_admissibility(
        grow_collapse_hist, State(sigma=0.55, o=0.40))
    check("CA.3 sigma_up_o_down_inadmissible",
          not adm and risk > 0.55,
          f"adm={adm} risk={risk:.3f} pattern={diag.get('pattern')}")
    check("CA.3b violation_label_correct",
          "D2_§2c" in str(diag.get("violation", "")),
          f"violation={diag.get('violation')}")

    # CA.4: Σ growth + dissent decline → INADMISSIBLE
    diss_collapse_hist = [
        {"attractor_state": {"sigma": 0.30, "o": 0.55},
         "synthetic_sincerity": {"dissent_independence": 0.55}},
        {"attractor_state": {"sigma": 0.40, "o": 0.55},
         "synthetic_sincerity": {"dissent_independence": 0.45}},
        {"attractor_state": {"sigma": 0.50, "o": 0.55},
         "synthetic_sincerity": {"dissent_independence": 0.35}},
    ]
    adm, risk, diag = check_complexity_admissibility(
        diss_collapse_hist, State(sigma=0.55, o=0.55),
        current_dissent_ind=0.30)
    check("CA.4 sigma_up_dissent_down_inadmissible",
          not adm,
          f"adm={adm} pattern={diag.get('pattern')}")

    # CA.5: O rising even as Σ rises → admissible
    healthy_hist = [
        {"attractor_state": {"sigma": 0.30, "o": 0.50}},
        {"attractor_state": {"sigma": 0.40, "o": 0.55}},
        {"attractor_state": {"sigma": 0.50, "o": 0.60}},
    ]
    adm, risk, diag = check_complexity_admissibility(
        healthy_hist, State(sigma=0.55, o=0.65))
    check("CA.5 sigma_up_o_up_admissible",
          adm and risk < 0.30,
          f"adm={adm} risk={risk:.3f}")

    # CA.6: No Σ growth → not the relevant pattern, admissible
    flat_hist = [
        {"attractor_state": {"sigma": 0.50, "o": 0.50}},
        {"attractor_state": {"sigma": 0.50, "o": 0.45}},
        {"attractor_state": {"sigma": 0.50, "o": 0.40}},
    ]
    adm, risk, diag = check_complexity_admissibility(
        flat_hist, State(sigma=0.50, o=0.40))
    check("CA.6 no_sigma_growth_not_flagged_by_complexity",
          adm,
          f"adm={adm} risk={risk:.3f}")


# ══════════════════════════════════════════════════════════════════
# D. REACH-SCALED TRUTH — D7 E1d
# ══════════════════════════════════════════════════════════════════

def test_reach_scaled_truth():
    print("\n=== RT: Reach-Scaled Truth Anchor (D7 E1d) ===")

    anchor = TruthAnchor()
    base_metrics = {"base_accuracy": 0.80, "shift_accuracy": 0.75,
                     "stress_accuracy": 0.70, "long_horizon_accuracy": 0.72}
    truth_diag = {"truth_consistency": 0.70}

    # RT.1: No proposal → reach multiplier = 1.0 (default)
    report = anchor.evaluate(base_metrics, base_metrics,
                              context={"truth_diag": truth_diag})
    check("RT.1 no_proposal_default_thresholds",
          abs(anchor.min_coupling - anchor.base_min_coupling) < 1e-6,
          f"min_coupling={anchor.min_coupling}")

    # RT.2: Adaptive layer proposal → low reach mult
    class Prop:
        target_layer = "adaptive"
        truth_risk = "low"
        path_risk = "low"
        externalization_risk = "low"
        agency_risk = "low"
    report = anchor.evaluate(base_metrics, base_metrics,
                              context={"truth_diag": truth_diag,
                                       "dgm_proposal": Prop()})
    check("RT.2 adaptive_low_risk_no_tightening",
          abs(anchor.min_coupling - 0.60) < 0.01,
          f"min_coupling={anchor.min_coupling}")

    # RT.3: Governance + high path_risk → tightened thresholds
    class GovProp:
        target_layer = "governance"
        truth_risk = "low"
        path_risk = "high"
        externalization_risk = "low"
        agency_risk = "low"
    anchor2 = TruthAnchor()
    anchor2.evaluate(base_metrics, base_metrics,
                      context={"truth_diag": truth_diag,
                               "dgm_proposal": GovProp()})
    check("RT.3 governance_high_risk_tightens_min_coupling",
          anchor2.min_coupling > 0.65,
          f"min_coupling={anchor2.min_coupling:.3f}")
    check("RT.4 governance_high_risk_tightens_max_divergence",
          anchor2.max_divergence < 0.25,
          f"max_divergence={anchor2.max_divergence:.3f}")

    # RT.5: Critical risk → most aggressive tightening
    class CritProp:
        target_layer = "governance"
        truth_risk = "critical"
        path_risk = "critical"
        externalization_risk = "critical"
        agency_risk = "critical"
    anchor3 = TruthAnchor()
    anchor3.evaluate(base_metrics, base_metrics,
                      context={"truth_diag": truth_diag,
                               "dgm_proposal": CritProp()})
    check("RT.5 critical_risk_tightens_strongly",
          anchor3.min_coupling > anchor2.min_coupling and
          anchor3.max_divergence < anchor2.max_divergence,
          f"crit min_coupling={anchor3.min_coupling:.3f} "
          f"high min_coupling={anchor2.min_coupling:.3f}")

    # RT.6: Same metrics that pass at low reach can fail at high reach
    medium_metrics = {"base_accuracy": 0.65, "shift_accuracy": 0.62,
                       "stress_accuracy": 0.60, "long_horizon_accuracy": 0.62}
    medium_truth = {"truth_consistency": 0.62}
    anchor4 = TruthAnchor()
    rep_low = anchor4.evaluate(
        medium_metrics, medium_metrics,
        context={"truth_diag": medium_truth, "dgm_proposal": Prop()})

    anchor5 = TruthAnchor()
    rep_high = anchor5.evaluate(
        medium_metrics, medium_metrics,
        context={"truth_diag": medium_truth, "dgm_proposal": CritProp()})
    # Note: temporal_stability defaults high w/o history, so we just
    # check the threshold rose
    check("RT.6 high_reach_more_demanding",
          anchor5.min_coupling > anchor4.min_coupling,
          f"low={anchor4.min_coupling:.3f} high={anchor5.min_coupling:.3f}")


# ══════════════════════════════════════════════════════════════════
# E. AUXILIARY INDICATORS — D3a §7 (DIAGNOSTIC ONLY)
# ══════════════════════════════════════════════════════════════════

def test_auxiliary_indicators():
    print("\n=== AI: Auxiliary Indicators (D3a §7 — diagnostic) ===")

    # AI.1: All six indicators always present
    aux = compute_auxiliary_indicators({})
    expected = {"resonance_quality", "boundary_integrity", "binding_profile",
                "redundancy_synergy_balance", "metastability_range",
                "attention_integrity"}
    actual = set(k for k in aux if not k.startswith("_"))
    check("AI.1 all_six_indicators_present",
          expected == actual,
          f"missing={expected - actual} extra={actual - expected}")

    # AI.2: Disclaimer is present (D3a §7 enforcement)
    check("AI.2 disclaimer_explicit_no_freigabe",
          "_DISCLAIMER" in aux and "NOT" in aux["_DISCLAIMER"],
          f"disclaimer={aux.get('_DISCLAIMER')}")

    # AI.3: Each indicator has a value field
    aux2 = compute_auxiliary_indicators({
        "metrics": {"base_accuracy": 0.7, "shift_accuracy": 0.65,
                     "stress_accuracy": 0.60, "long_horizon_accuracy": 0.62},
        "human_coupling": {"agency_score": 0.7, "cognitive_load": 0.3,
                            "dissent_visibility": 0.5},
        "council_per_role": {"r1": {"reason": "a"}, "r2": {"reason": "b"}},
        "history": [],
    })
    all_have_value = all("value" in aux2[k] for k in aux2
                         if not k.startswith("_"))
    check("AI.3 all_have_value_field",
          all_have_value)

    # AI.4: Boundary integrity reflects human coupling
    aux_strong = compute_auxiliary_indicators({
        "human_coupling": {"agency_score": 0.9, "cognitive_load": 0.2,
                            "dissent_visibility": 0.7},
    })
    aux_weak = compute_auxiliary_indicators({
        "human_coupling": {"agency_score": 0.3, "cognitive_load": 0.8,
                            "dissent_visibility": 0.2},
    })
    check("AI.4 boundary_integrity_responds_to_carrier_state",
          (aux_strong["boundary_integrity"]["value"] >
           aux_weak["boundary_integrity"]["value"] + 0.2),
          f"strong={aux_strong['boundary_integrity']['value']:.2f} "
          f"weak={aux_weak['boundary_integrity']['value']:.2f}")

    # AI.5: Module produces no veto, no decision — pure diagnostic
    # (Test is enforced by the runner pipeline integration, but
    # we can at least verify no "decision" or "block" key in output)
    leak = any(k in aux for k in ("decision", "block", "veto",
                                    "should_block", "freigabe"))
    check("AI.5 no_gating_keys_in_output",
          not leak,
          f"output_keys={list(aux.keys())}")


# ══════════════════════════════════════════════════════════════════
# F. INTEGRATION — V9 modules play nicely together
# ══════════════════════════════════════════════════════════════════

def test_integration():
    print("\n=== INT: V9 Integration ===")

    # INT.1: Sham + Carrier + Complexity can all evaluate without
    # interfering with each other given the same context
    history = [
        {"attractor_state": {"sigma": 0.30 + 0.05*i, "o": 0.55 - 0.02*i,
                              "l": 0.5, "d": 0.3,
                              "attractor": "RESONANCE"},
         "human_coupling": {"agency_score": 0.7 - 0.03*i,
                             "cognitive_load": 0.3 + 0.02*i,
                             "dissent_visibility": 0.5},
         "human_override": {"override_applied": True,
                             "action": "approve",
                             "rationale": "ok"},
         "synthetic_sincerity": {"dissent_independence": 0.40}}
        for i in range(6)
    ]

    state = State(sigma=0.60, o=0.43, attractor="RESONANCE")
    state.confidence = 0.85

    sham_ctx = {
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.85,
        "council_per_role": {"r1": {"decision": "GO", "reason": "x"},
                              "r2": {"decision": "GO", "reason": "x"}},
        "dissent_independence": 0.30,
        "dissent_visibility": 0.50,
        "human_coupling": {"agency_score": 0.55,
                            "cognitive_load": 0.42,
                            "dissent_visibility": 0.50},
        "truth_diag": {},
        "counter_check": {"decision": "GREEN"},
        "history": history,
    }
    sham_risk, sham_block, _ = compute_sham_resonance(sham_ctx)

    carrier_ctx = {
        "history": history,
        "human_coupling": {"agency_score": 0.55, "cognitive_load": 0.42},
        "human_override": {"override_applied": True, "action": "approve",
                            "rationale": "ok"},
        "sigma": 0.60,
    }
    carrier_risk, carrier_block, _ = compute_carrier_erosion(carrier_ctx)

    adm, comp_risk, _ = check_complexity_admissibility(
        history, state, current_dissent_ind=0.30)

    aux = compute_auxiliary_indicators({
        "human_coupling": {"agency_score": 0.55,
                            "cognitive_load": 0.42,
                            "dissent_visibility": 0.50},
        "metrics": {"base_accuracy": 0.7},
        "history": history,
    })

    # Different concerns from different modules — that's the point
    check("INT.1 modules_independent_signals",
          isinstance(sham_risk, float)
          and isinstance(carrier_risk, float)
          and isinstance(adm, bool)
          and isinstance(aux, dict),
          f"sham={sham_risk:.2f} carrier={carrier_risk:.2f} adm={adm}")

    # INT.2: At least one V9 veto would fire on this stress scenario
    # (Σ↑, O↓, agency↓, dissent_vis>>independence)
    any_veto = sham_block or carrier_block or (not adm)
    check("INT.2 stress_scenario_triggers_veto",
          any_veto,
          f"sham_block={sham_block} carrier_block={carrier_block} "
          f"complexity_inadm={not adm}")

    # INT.3: Non-compensable: V9 vetos do NOT cancel V8 admissibility
    # (they ADD to it, not replace it)
    is_adm_v8, viols = is_admissible({"sigma": 0.60, "l": 0.5,
                                       "o": 0.43, "d": 0.3})
    # V8 may say admissible (within thresholds) — V9 still vetoes
    check("INT.3 v9_vetos_independent_of_v8_admissibility",
          is_adm_v8 and any_veto,
          f"v8_adm={is_adm_v8} v9_veto={any_veto}")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_sham_resonance()
    test_carrier_erosion()
    test_complexity_admissibility()
    test_reach_scaled_truth()
    test_auxiliary_indicators()
    test_integration()

    print()
    print("=" * 64)
    print(f"V9 TESTS: {len(PASSES)} passed, {len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle V9-Tests bestanden.")
