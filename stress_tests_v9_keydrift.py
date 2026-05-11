"""
V9.0.6 Key-Drift and Negation Tests (ChatGPT v6)
====================================================
Two regression bugs found in ChatGPT review v6:

  Bug 1 (P0) — Key drift between runner and pareto_admissibility:
    runner.py writes records under "a3_sincerity" but
    check_complexity_admissibility() looked up "synthetic_sincerity".
    The two carry the same semantic content. Reading only one
    silently disabled the Σ↑+dissent↓ detection in production runs.
    V7 D6 K4 (Messverlagerung): the prüfungsrelevant key drifts
    away from where the runtime data actually lives.

  Bug 2 (P1) — Eval scoring negation patterns too narrow:
    "not 4" → correctly rejected
    "the answer is not equal to 4" → silently accepted
    "4 is incorrect" → silently accepted
    "should not be 4" → silently accepted
    Five common LLM-output negation phrasings slipped through.

Both bugs slipped past 521 unit tests because:
  - Bug 1: the existing test suite used the OLD key
    ("synthetic_sincerity"), so the Pareto check looked correct
    in tests and the runner's actual records never went near it.
  - Bug 2: the test cases used `"not X"` only, missing the more
    verbose phrasings real LLMs produce.
"""

import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from attractor_engine import SystemState
from eval import _score_one
from pareto_admissibility import check_complexity_admissibility

PASSES = []
FAILS = []


def check(name, condition, details=""):
    if condition:
        PASSES.append(name)
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, details))
        print(f"  FAIL  {name}  {details}")


# ══════════════════════════════════════════════════════════════════
# Bug 1: Key drift a3_sincerity vs synthetic_sincerity
# ══════════════════════════════════════════════════════════════════

def _make_decline_history(key):
    """Build a 3-iter history with declining dissent_independence
    under the given record key."""
    hist = []
    for i in range(3):
        hist.append({
            "attractor_state": {
                "sigma": 0.30 + 0.05 * i,
                "o": 0.55,
                "l": 0.5,
                "d": 0.3,
            },
            key: {"dissent_independence": 0.55 - 0.10 * i},
        })
    return hist


def test_key_drift_fix():
    print("\n=== KD: Key Drift a3_sincerity vs synthetic_sincerity ===")

    # Scenario: Σ↑ + dissent↓ — must be inadmissible regardless of key
    state = SystemState(sigma=0.50, l=0.5, o=0.55, d=0.3)

    # KD.1: Runner-format key (a3_sincerity) — must now be detected
    hist_runner = _make_decline_history("a3_sincerity")
    adm_r, risk_r, diag_r = check_complexity_admissibility(
        hist_runner, state, current_dissent_ind=0.20)
    check("KD.1 runner_format_a3_sincerity_detects_dissent_decline",
          not adm_r and risk_r > 0.5,
          f"adm={adm_r} risk={risk_r:.3f} delta_dissent={diag_r.get('delta_dissent')}")

    # KD.2: Old test-format key (synthetic_sincerity) — backward compat
    hist_old = _make_decline_history("synthetic_sincerity")
    adm_o, risk_o, diag_o = check_complexity_admissibility(
        hist_old, state, current_dissent_ind=0.20)
    check("KD.2 old_format_synthetic_sincerity_backward_compatible",
          not adm_o and risk_o > 0.5,
          f"adm={adm_o} risk={risk_o:.3f}")

    # KD.3: Both formats produce identical risk
    check("KD.3 both_formats_produce_identical_risk",
          abs(risk_r - risk_o) < 0.001,
          f"runner={risk_r:.4f} old={risk_o:.4f}")

    # KD.4: a3_sincerity takes precedence when BOTH are present
    # (runner is the source of truth in production)
    hist_both = []
    for i in range(3):
        hist_both.append({
            "attractor_state": {
                "sigma": 0.30 + 0.05 * i, "o": 0.55, "l": 0.5, "d": 0.3,
            },
            "a3_sincerity": {"dissent_independence": 0.55 - 0.10 * i},
            "synthetic_sincerity": {"dissent_independence": 0.99},  # would mask
        })
    adm_b, risk_b, diag_b = check_complexity_admissibility(
        hist_both, state, current_dissent_ind=0.20)
    check("KD.4 a3_sincerity_takes_precedence",
          not adm_b and risk_b > 0.5,
          f"adm={adm_b} risk={risk_b:.3f}")

    # KD.5: Diagnostic dictionary has consistent delta_dissent
    check("KD.5 delta_dissent_in_diagnostic",
          diag_r.get("delta_dissent") is not None
          and diag_r["delta_dissent"] < -0.10,
          f"delta_dissent={diag_r.get('delta_dissent')}")


def test_runner_records_actually_trigger_complexity_check():
    """KD.6: Verify the integration end-to-end through runner.main()."""
    print("\n=== KD: Runner records actually flow into complexity check ===")
    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            records = runner.main(
                iterations=5,
                storage_path=os.path.join(tmpdir, "log.json"),
                memory_path=os.path.join(tmpdir, "mem.json"),
                simulation_mode=True,
                return_records=True,
            )

    # The runner should be writing under a3_sincerity
    has_a3 = any("a3_sincerity" in r for r in records)
    check("KD.6 runner_writes_a3_sincerity_in_records",
          has_a3,
          f"records keys (first): {list(records[0].keys())[:10]}")

    # And those records should be readable by check_complexity_admissibility
    # We verify by extracting the dissent trajectory the way Pareto would
    if has_a3:
        readable_dissent_count = sum(
            1 for r in records
            if isinstance(r.get("a3_sincerity"), dict)
            and "dissent_independence" in r["a3_sincerity"]
        )
        check("KD.7 dissent_trajectory_readable_from_runner_records",
              readable_dissent_count >= 3,
              f"only {readable_dissent_count}/{len(records)} records "
              f"have readable dissent_independence")


# ══════════════════════════════════════════════════════════════════
# Bug 2: Negation pattern coverage
# ══════════════════════════════════════════════════════════════════

def test_extended_negation_patterns():
    """ChatGPT v6 P1: real-LLM-style negations must be rejected."""
    print("\n=== NP: Extended negation patterns ===")

    # Cases that USED to slip through V9.0.5 — must now be rejected
    chatgpt_v6_negations = [
        ("the answer is not equal to 4", "4"),
        ("it is not exactly 4", "4"),
        ("it should not be 4", "4"),
        ("4 is incorrect", "4"),
        ("4 is wrong", "4"),
    ]
    for output, expected in chatgpt_v6_negations:
        result = _score_one(expected, output)
        check(f"NP {expected!r}_in_{output!r}",
              not result,
              f"falsely accepted: {output!r}")

    # Additional negation patterns that should also be caught
    additional_negations = [
        ("cannot be 4", "4"),
        ("won't be 4", "4"),
        ("4 is false", "4"),
        ("4 is invalid", "4"),
        ("4 would be wrong", "4"),
        ("never 4", "4"),
    ]
    for output, expected in additional_negations:
        result = _score_one(expected, output)
        check(f"NP_additional {output!r}",
              not result,
              f"falsely accepted: {output!r}")

    # Positive cases must STILL pass — fix must not over-reject
    positive_cases = [
        ("the answer is 4", "4"),
        ("2 + 2 equals 4", "4"),
        ("It is 4", "4"),
        ("4", "4"),
        ("so the result is 4 indeed", "4"),
        ("Gravity is a force that attracts masses", "attracts masses"),
    ]
    for output, expected in positive_cases:
        result = _score_one(expected, output)
        check(f"NP_positive {output!r}",
              result,
              f"falsely rejected: {output!r}")


def test_word_boundary_still_holds():
    """V9.0.5 word-boundary behavior must not regress."""
    print("\n=== NP: Word boundary preserved ===")

    # Numeric must NOT match within larger numbers
    boundary_cases = [
        ("14", "4", False),
        ("40", "4", False),
        ("24", "4", False),
        ("4", "4", True),
        ("the answer is 4 itself", "4", True),
    ]
    for output, expected, should_match in boundary_cases:
        result = _score_one(expected, output)
        ok = result == should_match
        check(f"NP_boundary {output!r}_match={should_match}",
              ok,
              f"got {result}")


# ══════════════════════════════════════════════════════════════════
# Cross-cutting K4 invariant
# ══════════════════════════════════════════════════════════════════

def test_k4_runtime_to_check_continuity():
    """
    Property test: for any structurally equivalent record schema —
    runner format or test format — the same logical content must
    produce the same admissibility decision.

    V7 D6 K4 invariant: the gate must measure what it says it measures.
    """
    print("\n=== K4: Runtime-to-check continuity (property) ===")

    state = SystemState(sigma=0.50, l=0.5, o=0.55, d=0.3)

    # Generate 10 different decline patterns and verify both keys
    # produce identical decisions
    import random
    random.seed(606)
    discrepancies = []

    for trial in range(20):
        start = random.uniform(0.45, 0.65)
        slope = random.uniform(-0.15, -0.05)
        n_steps = 3

        hist_runner = []
        hist_old = []
        for i in range(n_steps):
            d = max(0.0, start + slope * i)
            attr = {
                "sigma": 0.30 + 0.05 * i,
                "o": 0.55, "l": 0.5, "d": 0.3,
            }
            hist_runner.append({
                "attractor_state": attr,
                "a3_sincerity": {"dissent_independence": d},
            })
            hist_old.append({
                "attractor_state": attr,
                "synthetic_sincerity": {"dissent_independence": d},
            })

        cur = max(0.0, start + slope * n_steps)
        adm_r, risk_r, _ = check_complexity_admissibility(
            hist_runner, state, current_dissent_ind=cur)
        adm_o, risk_o, _ = check_complexity_admissibility(
            hist_old, state, current_dissent_ind=cur)

        if adm_r != adm_o or abs(risk_r - risk_o) > 0.01:
            discrepancies.append({
                "trial": trial,
                "runner": (adm_r, risk_r),
                "old": (adm_o, risk_o),
            })

    check("K4.1 runner_and_test_keys_produce_identical_decisions",
          len(discrepancies) == 0,
          f"{len(discrepancies)}/20 discrepancies: {discrepancies[:2]}")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_key_drift_fix()
    test_runner_records_actually_trigger_complexity_check()
    test_extended_negation_patterns()
    test_word_boundary_still_holds()
    test_k4_runtime_to_check_continuity()

    print()
    print("=" * 64)
    print(f"V9.0.6 KEY-DRIFT + NEGATION TESTS: "
          f"{len(PASSES)} passed, {len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle V9.0.6-Tests bestanden.")
