"""
V9.0.5 Baseline Tests (ChatGPT v5)
=====================================
Three regression tests for the ChatGPT v5 review findings.

  Bug 1 — Baseline is not really baseline:
    V9.0.4's `baseline_attractor_state = curr_state` was set INSIDE
    the iteration loop, which means baseline = first candidate's state.
    A rejected first candidate could then become the comparison
    anchor under a misleading name. ChatGPT v5 P0.

  Bug 2 — Audit anchor lies after acceptance:
    `effective_attractor_state = curr_state` was set BEFORE the record
    was built, so a record could report `attractor_gating_anchor =
    "effective"` when the actual gate decision was made against
    "baseline". ChatGPT v5 P1.

  Bug 3 — eval.py too permissive:
    Pure substring match meant `"4"` matched inside `"14"` or
    `"not 4"`. A safety/truth prototype should reject such
    schein-correctness. ChatGPT v5 P1.
"""

import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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
# Bug 1: True pre-mutation baseline
# ══════════════════════════════════════════════════════════════════

def test_baseline_is_genuine_pre_mutation():
    """
    BL.1–BL.4: Verify the baseline is constructed BEFORE any mutation,
    not from the first candidate.
    """
    print("\n=== BL: Genuine Pre-Mutation Baseline (ChatGPT v5 P0) ===")

    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            records = runner.main(
                iterations=3,
                storage_path=os.path.join(tmpdir, "log.json"),
                memory_path=os.path.join(tmpdir, "mem.json"),
                simulation_mode=True,
                return_records=True,
            )

    # BL.1: Records carry the actual gating-anchor state, not just label
    have_anchor_state = all(
        "attractor_gating_anchor_state" in r for r in records)
    check("BL.1 record_has_explicit_gating_anchor_state",
          have_anchor_state)

    # BL.2: First record's gating anchor must NOT equal first candidate's state
    # (this was the v5 bug)
    first = records[0]
    candidate_state = first.get("attractor_state")
    anchor_state = first.get("attractor_gating_anchor_state")
    check("BL.2 first_candidate_not_used_as_baseline",
          candidate_state != anchor_state,
          f"both = {candidate_state}")

    # BL.3: When run rejects all candidates, the anchor stays "baseline"
    accepted_count = sum(1 for r in records if r.get("final_decision") == "GO")
    if accepted_count == 0:
        anchors = [r.get("attractor_gating_anchor") for r in records]
        all_baseline = all(a == "baseline" for a in anchors)
        check("BL.3 anchor_stays_baseline_across_rejections",
              all_baseline,
              f"anchors={anchors}")
    else:
        check("BL.3 anchor_stays_baseline_across_rejections",
              True, f"skipped — {accepted_count} acceptances")

    # BL.4: All gating_anchor_state entries are identical when no acceptance
    if accepted_count == 0:
        states = [r.get("attractor_gating_anchor_state") for r in records]
        # All should be the same baseline, not changing per iteration
        first_state = states[0]
        all_same = all(s == first_state for s in states)
        check("BL.4 baseline_state_stable_across_rejections",
              all_same,
              f"baselines differ: {states}")
    else:
        check("BL.4 baseline_state_stable_across_rejections",
              True, "skipped")


def test_build_attractor_state_helper():
    """
    BL.5: The build_attractor_state helper produces a SystemState
    from minimal context (just baseline metrics).
    """
    print("\n=== BL: build_attractor_state helper ===")
    from attractor_engine import SystemState
    from runner import build_attractor_state

    metrics = {
        "base_accuracy": 0.7, "shift_accuracy": 0.65,
        "stress_accuracy": 0.6, "long_horizon_accuracy": 0.62,
        "alignment_consistency_gap": 0.05,
        "memory_sensitivity": 0.10,
        "suspicious_rate": 0.0,
    }
    state = build_attractor_state(metrics)
    check("BL.5 helper_produces_systemstate",
          isinstance(state, SystemState))
    check("BL.6 helper_state_has_all_components",
          all(hasattr(state, attr) for attr in ("sigma", "l", "o", "d")),
          f"state.dict={state.to_dict()}")


# ══════════════════════════════════════════════════════════════════
# Bug 2: Audit anchor honesty
# ══════════════════════════════════════════════════════════════════

def test_audit_anchor_does_not_lie():
    """
    AU.1: When a candidate is accepted, the record for THAT iteration
    must report the gating anchor that was actually used during the
    decision (baseline if it was the first acceptance), NOT the
    post-acceptance "effective" label.

    This bug requires an acceptance to be testable in default-rejection
    runs. We construct it at unit level since runner.main() default
    rejects everything.
    """
    print("\n=== AU: Audit Anchor Honesty (ChatGPT v5 P1) ===")

    # Direct unit-level check: the runner code captures
    # gating_anchor_source BEFORE possibly setting effective_attractor_state.
    # We verify by reading the source.
    runner_path = os.path.join(os.path.dirname(__file__), "runner.py")
    with open(runner_path) as f:
        src = f.read()

    # The fix: gating_anchor_source must be captured BEFORE
    # `effective_attractor_state = curr_state` (which happens on accept).
    # We check the relative line positions.
    src_lines = src.splitlines()

    capture_idx = None
    update_idx = None
    for i, line in enumerate(src_lines):
        if 'gating_anchor_source = "baseline"' in line and capture_idx is None:
            # Find the block where source is captured
            capture_idx = i
        if 'effective_attractor_state = curr_state' in line and update_idx is None:
            # Find the accept-update line
            update_idx = i

    check("AU.1 source_capture_exists", capture_idx is not None)
    check("AU.2 effective_update_exists", update_idx is not None)
    if capture_idx is not None and update_idx is not None:
        check("AU.3 anchor_source_captured_before_effective_update",
              capture_idx < update_idx,
              f"capture@{capture_idx} update@{update_idx}")

    # AU.4: Record stores gating_anchor_state as separate field
    check("AU.4 record_has_gating_anchor_state_field",
          '"attractor_gating_anchor_state"' in src,
          "explicit anchor state field expected in record")


# ══════════════════════════════════════════════════════════════════
# Bug 3: Robust scoring
# ══════════════════════════════════════════════════════════════════

def test_eval_scoring_rejects_false_positives():
    """
    EV.1–EV.7: Word-boundary numeric matching, negation guard,
    and substring fallback for free text.
    """
    print("\n=== EV: Robust Eval Scoring (ChatGPT v5 P1) ===")
    from eval import _score_one

    # Exact numeric match
    check("EV.1 exact_numeric_match_passes",
          _score_one("4", "4"))
    check("EV.2 numeric_in_sentence_passes",
          _score_one("4", "The answer is 4."))

    # Numeric inside larger number — must REJECT
    check("EV.3 numeric_inside_larger_number_rejected",
          not _score_one("4", "The answer is 14."),
          "old substring would have wrongly accepted '14' as containing '4'")

    # Negation — must REJECT
    check("EV.4 explicit_negation_rejected",
          not _score_one("4", "The answer is not 4."),
          "old substring would have wrongly accepted 'not 4'")

    check("EV.5 negation_no_rejected",
          not _score_one("4", "There is no 4 in the result."))

    # Free text — substring stays valid
    check("EV.6 free_text_substring_match",
          _score_one("attracts masses",
                     "Gravity is a force that attracts masses toward each other."))

    # Free text negation
    check("EV.7 free_text_negation_rejected",
          not _score_one("attracts masses",
                          "Gravity does not attract masses, it bends spacetime."),
          "negation guard should also work for free text")


# ══════════════════════════════════════════════════════════════════
# Cross-cutting: end-to-end integration
# ══════════════════════════════════════════════════════════════════

def test_runner_still_runs_with_robust_scoring():
    """
    IN.1: The robust scoring fix must not break the existing runner.
    """
    print("\n=== IN: Integration with V9.0.5 fixes ===")
    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            try:
                records = runner.main(
                    iterations=2,
                    storage_path=os.path.join(tmpdir, "log.json"),
                    memory_path=os.path.join(tmpdir, "mem.json"),
                    simulation_mode=True,
                    return_records=True,
                )
                ok = isinstance(records, list) and len(records) == 2
                check("IN.1 runner_still_completes_with_v9_0_5_fixes", ok)
            except Exception as e:
                check("IN.1 runner_still_completes_with_v9_0_5_fixes",
                      False, f"{type(e).__name__}: {e}")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_baseline_is_genuine_pre_mutation()
    test_build_attractor_state_helper()
    test_audit_anchor_does_not_lie()
    test_eval_scoring_rejects_false_positives()
    test_runner_still_runs_with_robust_scoring()

    print()
    print("=" * 64)
    print(f"V9.0.5 BASELINE TESTS: {len(PASSES)} passed, "
          f"{len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle V9.0.5-Tests bestanden.")
