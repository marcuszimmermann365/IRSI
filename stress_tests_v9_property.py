"""
V9 Property-Based Tests
=========================
Tests structural invariants that should hold under all valid inputs.

These complement the unit tests and smoke tests:
  - Unit tests:   "this specific case behaves like X"
  - Smoke tests:  "the pipeline runs without error"
  - Property tests: "this invariant holds for ALL valid inputs"

The properties below are direct translations of V7 normative claims.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from carrier_erosion import compute_carrier_erosion
from pareto_admissibility import (
    check_complexity_admissibility,
    is_admissible,
)
from sham_resonance import compute_sham_resonance

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
    def __init__(self, sigma, l, o, d):
        self.sigma = sigma
        self.l = l
        self.o = o
        self.d = d


# ══════════════════════════════════════════════════════════════════
# Property 1: Σ↑ + O↓ → never admissible (D2 §2c invariant)
# ══════════════════════════════════════════════════════════════════

def property_sigma_up_o_down_never_admissible():
    """
    For all randomly generated trajectories where Σ rises clearly
    above the threshold AND O falls clearly below, complexity_admissibility
    must reject.

    This is the V7 D2 §2c invariant: Entwicklung ohne Höherentwicklung
    is never admissible — when the pattern is clearly present.

    Note on threshold edge cases: A first version of this property
    test generated trajectories that *nominally* had Σ growth = 0.20-0.40,
    but the windowed Δ-measurement (4-step history + current) yielded
    actual Δ values in the 0.14–0.15 range — exactly at the V7 threshold
    boundary. The algorithm correctly did NOT flag these as violations.
    The property test was at fault, not the code.

    This is a useful finding: it shows that the threshold (0.15) creates
    an unavoidable edge zone. For a production system, this zone would
    need calibration against external scenarios (V7 D3a §7 implies this).
    For V9, we test only the unambiguous violation region.
    """
    print("\n=== PR1: Property — Σ↑ + O↓ → inadmissible (clear cases) ===")
    random.seed(42)

    violations_found = 0
    correctly_rejected = 0
    n_trials = 100
    cases_logged = []

    for trial in range(n_trials):
        # Generate random initial state
        sigma_start = random.uniform(0.20, 0.40)
        o_start = random.uniform(0.55, 0.80)

        # Force the pattern WELL ABOVE threshold:
        # Σ growth ≥ 0.30 (threshold 0.15, window dilution ~0.75)
        # O decline ≥ 0.18 (threshold 0.05, window dilution ~0.75)
        sigma_growth = random.uniform(0.30, 0.50)
        o_decline = random.uniform(0.18, 0.30)

        # Build a 4-step history
        history = []
        for i in range(4):
            t = i / 3.0  # 0 .. 1
            history.append({
                "attractor_state": {
                    "sigma": sigma_start + sigma_growth * t,
                    "o": o_start - o_decline * t,
                    "l": 0.5,
                    "d": 0.3,
                }
            })

        current = State(
            sigma=sigma_start + sigma_growth,
            l=0.5,
            o=o_start - o_decline,
            d=0.3,
        )

        admissible, risk, diag = check_complexity_admissibility(
            history, current)

        # Property: must NOT be admissible
        if admissible:
            violations_found += 1
            cases_logged.append({
                "trial": trial,
                "delta_sigma": diag.get("delta_sigma"),
                "delta_o": diag.get("delta_o"),
                "pattern": diag.get("pattern"),
            })
        else:
            correctly_rejected += 1

    # Report — the invariant must hold for ALL trials in clear region
    check("PR1.1 sigma_up_o_down_always_rejected_in_clear_region",
          violations_found == 0,
          f"violations={violations_found}/{n_trials} "
          f"first_few={cases_logged[:3]}")
    check("PR1.2 all_correctly_rejected",
          correctly_rejected == n_trials,
          f"correct={correctly_rejected}/{n_trials}")


# ══════════════════════════════════════════════════════════════════
# Property 2: Sham resonance is non-decreasing in independence loss
# ══════════════════════════════════════════════════════════════════

def property_sham_monotone_in_independence():
    """
    For RESONANCE classifications, sham_risk should be non-decreasing
    as dissent_independence falls (all else equal).

    This is the V7 D4a §7 invariant: less independence = more sham.
    """
    print("\n=== PR2: Property — sham_risk non-decreasing as "
          "independence falls ===")

    # Fixed context except for dissent_independence
    base_ctx = {
        "attractor_state": "RESONANCE",
        "attractor_confidence": 0.75,
        "council_per_role": {
            "r1": {"decision": "GO", "reason": "x"},
            "r2": {"decision": "GO", "reason": "y"},
        },
        "dissent_visibility": 0.50,
        "human_coupling": {"agency_score": 0.7, "cognitive_load": 0.3,
                            "dissent_visibility": 0.50},
        "truth_diag": {},
        "counter_check": {"decision": "GREEN"},
        "history": [],
    }

    # Sweep independence from 1.0 down to 0.0
    independences = [i / 20.0 for i in range(20, -1, -1)]
    risks = []
    for ind in independences:
        ctx = dict(base_ctx)
        ctx["dissent_independence"] = ind
        risk, _, _ = compute_sham_resonance(ctx)
        risks.append(risk)

    # Check monotone non-decreasing
    monotone = True
    violations = []
    for i in range(1, len(risks)):
        if risks[i] < risks[i-1] - 1e-9:  # tolerance for float
            monotone = False
            violations.append((independences[i-1], risks[i-1],
                                independences[i], risks[i]))

    check("PR2.1 risk_monotone_in_independence_loss",
          monotone,
          f"{len(violations)} violations: {violations[:3]}")

    # Endpoint check: risk at independence=0 should be > risk at 1.0
    check("PR2.2 endpoints_correct_direction",
          risks[-1] > risks[0],
          f"ind=1.0 risk={risks[0]:.3f}; ind=0.0 risk={risks[-1]:.3f}")


# ══════════════════════════════════════════════════════════════════
# Property 3: Carrier erosion non-decreasing in agency decline
# ══════════════════════════════════════════════════════════════════

def property_carrier_erosion_responds_to_decline():
    """
    Steeper agency declines should produce non-decreasing erosion risk.
    """
    print("\n=== PR3: Property — erosion responds to agency slope ===")

    # Generate two histories: one with mild decline, one with steep
    def make_history(start, slope, n=8):
        return [
            {
                "human_coupling": {
                    "agency_score": max(0.0, min(1.0, start + slope * i)),
                    "cognitive_load": 0.3,
                    "dissent_visibility": 0.5,
                },
                "human_override": {
                    "override_applied": True,
                    "action": ["approve", "review", "request"][i % 3],
                    "rationale": f"detailed reasoning for step {i}",
                },
                "attractor_state": {"sigma": 0.5},
            }
            for i in range(n)
        ]

    risks = []
    slopes = [0.0, -0.01, -0.02, -0.03, -0.04, -0.05]
    for slope in slopes:
        hist = make_history(0.80, slope)
        risk, _, _ = compute_carrier_erosion({
            "history": hist,
            "human_coupling": {"agency_score": 0.80 + slope * 7,
                                "cognitive_load": 0.3},
            "sigma": 0.5,
        })
        risks.append(risk)

    # Risk should be non-decreasing as slope becomes more negative
    monotone = all(risks[i] >= risks[i-1] - 0.01
                    for i in range(1, len(risks)))
    check("PR3.1 erosion_non_decreasing_with_steeper_decline",
          monotone,
          f"slopes={slopes} risks={[round(r,3) for r in risks]}")

    # Steepest slope should produce higher risk than no decline
    check("PR3.2 steep_decline_higher_risk_than_flat",
          risks[-1] > risks[0],
          f"flat={risks[0]:.3f} steep={risks[-1]:.3f}")


# ══════════════════════════════════════════════════════════════════
# Property 4: Admissibility region symmetric in violations
# ══════════════════════════════════════════════════════════════════

def property_admissibility_floors_independent():
    """
    For any single floor violation, is_admissible must return False.
    Compensability between dimensions is forbidden (D2 non-compensable).
    """
    print("\n=== PR4: Property — admissibility floors independent ===")
    random.seed(7)

    # Each dimension has a floor
    # O ≥ 0.20, D ≤ 0.75, L ≥ 0.30, Σ ≥ 0.10
    fail_cases = []

    for trial in range(50):
        # Generate a state where exactly ONE dimension is below floor,
        # all others are excellent
        which = random.choice(["o", "d", "l", "sigma"])
        s = {"sigma": 0.8, "l": 0.8, "o": 0.8, "d": 0.2}

        if which == "o":
            s["o"] = random.uniform(0.0, 0.19)
        elif which == "d":
            s["d"] = random.uniform(0.76, 1.0)
        elif which == "l":
            s["l"] = random.uniform(0.0, 0.29)
        elif which == "sigma":
            s["sigma"] = random.uniform(0.0, 0.09)

        admissible, violations = is_admissible(s)
        if admissible:
            fail_cases.append((which, s))

    check("PR4.1 single_floor_violation_blocks_admissibility",
          len(fail_cases) == 0,
          f"{len(fail_cases)} compensation violations")


# ══════════════════════════════════════════════════════════════════
# Property 5: Empty inputs produce conservative (safe) defaults
# ══════════════════════════════════════════════════════════════════

def property_empty_inputs_safe():
    """
    All V9 modules should handle empty/missing inputs gracefully
    without crashing and without false-positive GO.
    """
    print("\n=== PR5: Property — empty inputs are safe ===")

    # sham_resonance with completely empty context
    try:
        risk, block, diag = compute_sham_resonance({})
        check("PR5.1 sham_handles_empty_context",
              isinstance(risk, float) and not block,
              f"risk={risk} block={block}")
    except Exception as e:
        check("PR5.1 sham_handles_empty_context", False, str(e))

    # carrier_erosion with empty history
    try:
        risk, block, diag = compute_carrier_erosion({})
        check("PR5.2 carrier_handles_empty_context",
              isinstance(risk, float) and not block)
    except Exception as e:
        check("PR5.2 carrier_handles_empty_context", False, str(e))

    # complexity_admissibility with empty history
    try:
        adm, risk, diag = check_complexity_admissibility(
            [], State(0.5, 0.5, 0.5, 0.3))
        check("PR5.3 complexity_handles_empty_history",
              isinstance(adm, bool))
    except Exception as e:
        check("PR5.3 complexity_handles_empty_history", False, str(e))


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    property_sigma_up_o_down_never_admissible()
    property_sham_monotone_in_independence()
    property_carrier_erosion_responds_to_decline()
    property_admissibility_floors_independent()
    property_empty_inputs_safe()

    print()
    print("=" * 64)
    print(f"V9 PROPERTY TESTS: {len(PASSES)} passed, {len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle V9-Property-Tests bestanden.")
