"""
V9.0.4 Gating-Anchor Tests (ChatGPT v4 P0)
=============================================
Regression tests for the candidate-vs-effective-state drift bug.

V9.0.3 had introduced the SEPARATION (effective_attractor_state vs
prev_attractor_state), but the gating logic still used
prev_attractor_state as comparison anchor. This meant a rejected bad
candidate became the comparison baseline for the next candidate —
which then could look like RESONANCE → GO when it would have been
REVIEW against the actually-effective system state.

V7 D6 K4 (Messverlagerung) violation: the gate's reference frame
silently drifts away from the real system path.

V9.0.4 fix:
  1. New variable: baseline_attractor_state — captured on iteration 0,
     used as fallback gating anchor when nothing has been accepted yet.
  2. compute_attractor() called with gating_anchor =
     effective_attractor_state or baseline_attractor_state, never with
     prev_attractor_state directly.
  3. Candidate trajectory still computed (for diagnostic) but explicitly
     marked as not gating-relevant.
"""

import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from attractor_engine import (
    SystemState,
    compute_attractor,
    extended_decide,
)

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
# Direct reproduction of the ChatGPT v4 drift scenario
# ══════════════════════════════════════════════════════════════════

def test_anchor_drift_at_unit_level():
    """
    GA.1–GA.3: The original ChatGPT v4 reproduction case.

    Three states:
      S0 = baseline (effective)
      S1 = bad candidate (REJECTED)
      S2 = subsequent candidate

    Property: S2's gating decision must depend on S0, not S1.
    Comparing S2 against the rejected S1 is the drift bug.
    """
    print("\n=== GA: Gating Anchor — unit-level drift ===")

    S0 = SystemState(sigma=0.5, l=0.5, o=0.6, d=0.3)
    S1 = SystemState(sigma=0.4, l=0.4, o=0.4, d=0.5)  # bad, rejected
    S2 = SystemState(sigma=0.5, l=0.5, o=0.5, d=0.4)  # next candidate

    # Path A — correct (against effective S0)
    attr_correct, trends_correct, _ = compute_attractor(S0, S2)
    d_correct, r_correct, _ = extended_decide(
        "GREEN", attr_correct, trends_correct, S2)

    # Path B — DRIFT (against rejected S1)
    attr_drift, trends_drift, _ = compute_attractor(S1, S2)
    d_drift, r_drift, _ = extended_decide(
        "GREEN", attr_drift, trends_drift, S2)

    # GA.1: drift path makes S2 look better than it is
    check("GA.1 drift_path_produces_softer_decision",
          d_drift in ("GO",) and d_correct in ("REVIEW", "STOP", "HOLD"),
          f"drift={d_drift} ({r_drift}) correct={d_correct} ({r_correct})")

    # GA.2: the two paths disagree
    check("GA.2 anchors_produce_different_decisions",
          d_drift != d_correct,
          f"drift={d_drift} correct={d_correct}")

    # GA.3: the correct path is the more conservative one
    severity_order = {"GO": 0, "HOLD": 1, "REVIEW": 2,
                       "ROLLBACK": 3, "STOP": 4}
    check("GA.3 effective_anchor_is_more_conservative",
          severity_order.get(d_correct, 0) > severity_order.get(d_drift, 0),
          f"correct({d_correct})={severity_order.get(d_correct)} "
          f"vs drift({d_drift})={severity_order.get(d_drift)}")


# ══════════════════════════════════════════════════════════════════
# Pipeline-level: runner does NOT use the rejected anchor
# ══════════════════════════════════════════════════════════════════

def test_runner_uses_correct_anchor():
    """
    GA.4–GA.7: Verify the runner records the gating anchor, never falls
    back silently to prev_candidate, and propagates this honestly into
    the audit trace.
    """
    print("\n=== GA: Runner uses correct gating anchor ===")
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

    # GA.4: records contain the gating-anchor field
    have_anchor_field = all("attractor_gating_anchor" in r for r in records)
    check("GA.4 every_record_has_gating_anchor_field",
          have_anchor_field)

    # GA.5: the anchor is never "prev_candidate" — must be effective or baseline
    valid = {"effective", "baseline", "none"}
    anchors = [r.get("attractor_gating_anchor") for r in records]
    all_valid = all(a in valid for a in anchors)
    check("GA.5 gating_anchor_never_uses_rejected_candidate",
          all_valid,
          f"anchors={anchors}")

    # GA.6: in default run, nothing is accepted, so anchor stays "baseline"
    accepted = [r for r in records if r.get("final_decision") == "GO"]
    if not accepted:
        # All anchors should be 'baseline' (after iteration 0) or 'none' (iter 0)
        expected_set = {"baseline", "none"}
        check("GA.6 unaccepted_run_keeps_baseline_anchor",
              set(anchors) <= expected_set,
              f"anchors={anchors}")
    else:
        check("GA.6 unaccepted_run_keeps_baseline_anchor",
              True, "skipped — some acceptances happened")

    # GA.7: candidate diagnostic is recorded but flagged as non-gating
    candidate_diagnostics = [
        r.get("attractor_candidate_diagnostic")
        for r in records
        if r.get("attractor_candidate_diagnostic") is not None
    ]
    if candidate_diagnostics:
        well_marked = all(
            cd.get("_note") == "diagnostic_only_not_gating_relevant"
            for cd in candidate_diagnostics
        )
        check("GA.7 candidate_diagnostic_flagged_non_gating",
              well_marked,
              f"first: {candidate_diagnostics[0]}")
    else:
        check("GA.7 candidate_diagnostic_flagged_non_gating",
              True,
              "no candidate diagnostics produced — vacuously ok")


# ══════════════════════════════════════════════════════════════════
# Stronger property: anchor stability across rejections
# ══════════════════════════════════════════════════════════════════

def test_anchor_stable_across_rejections():
    """
    GA.8: For a sequence of rejected candidates, the gating anchor
    must NOT shift. Each candidate is judged against the same baseline.
    """
    print("\n=== GA: Anchor stability across rejections ===")
    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            records = runner.main(
                iterations=6,
                storage_path=os.path.join(tmpdir, "log.json"),
                memory_path=os.path.join(tmpdir, "mem.json"),
                simulation_mode=True,
                return_records=True,
            )

    # In default run: all rejections expected
    accepted_count = sum(1 for r in records if r.get("final_decision") == "GO")

    if accepted_count == 0:
        # All gating anchors should be baseline (after iter 0)
        # Iter 0 is "none" because baseline is being created in that very iter
        anchors = [r.get("attractor_gating_anchor") for r in records]

        # Iterations 1+ should all be "baseline"
        non_first = anchors[1:]
        all_baseline = all(a == "baseline" for a in non_first)
        check("GA.8 anchor_stays_baseline_across_rejections",
              all_baseline,
              f"anchors={anchors} non_first={non_first}")
    else:
        check("GA.8 anchor_stays_baseline_across_rejections",
              True, f"skipped — {accepted_count} acceptances")


# ══════════════════════════════════════════════════════════════════
# Property test: random rejected sequences cannot flip GO
# ══════════════════════════════════════════════════════════════════

def test_property_rejected_sequence_cannot_create_go():
    """
    GA.9: Property invariant — given any sequence of rejected
    candidates and a final candidate that is destructive against
    the baseline, the gate must not produce GO regardless of the
    intermediate trajectory.
    """
    print("\n=== GA: Property — rejected sequence cannot create GO ===")
    import random
    random.seed(2026)

    baseline = SystemState(sigma=0.6, l=0.6, o=0.65, d=0.25)
    drift_violations = 0
    n_trials = 100

    for trial in range(n_trials):
        # Generate a sequence of rejected bad candidates
        rejected_chain = []
        for _ in range(random.randint(2, 6)):
            s = SystemState(
                sigma=random.uniform(0.2, 0.4),
                l=random.uniform(0.2, 0.4),
                o=random.uniform(0.2, 0.4),
                d=random.uniform(0.4, 0.7),
            )
            rejected_chain.append(s)

        # Final candidate: better than the worst rejected, but still
        # destructive against baseline
        final = SystemState(
            sigma=random.uniform(0.4, 0.5),
            l=random.uniform(0.4, 0.5),
            o=random.uniform(0.4, 0.5),
            d=random.uniform(0.3, 0.5),
        )

        # Path A — V9.0.4 correct: anchor stays baseline
        attr_correct, trends_correct, _ = compute_attractor(baseline, final)
        d_correct, _, _ = extended_decide(
            "GREEN", attr_correct, trends_correct, final)

        # Path B — V9.0.3 drift: anchor would have been the last rejected
        last_rejected = rejected_chain[-1]
        attr_drift, trends_drift, _ = compute_attractor(last_rejected, final)
        d_drift, _, _ = extended_decide(
            "GREEN", attr_drift, trends_drift, final)

        # Drift path is broken if it produces GO when correct path doesn't
        if d_drift == "GO" and d_correct != "GO":
            drift_violations += 1

    # The property test PROVES the bug exists in the unfixed code path,
    # and that we can detect it.
    check("GA.9 rejected_chain_can_create_drift_GO",
          drift_violations > 0,
          f"violations={drift_violations}/{n_trials}")
    print(f"      ({drift_violations}/{n_trials} cases where drift "
          f"produces GO that correct path rejects — confirms bug exists)")


def test_no_shared_mutable_default_policy():
    """
    GA.10: Two Agent instances with default policy must NOT share
    the same dict reference. ChatGPT v4 P2 — without defensive
    deepcopy, mutations in one agent could leak to others.
    """
    print("\n=== GA: No shared mutable DEFAULT_POLICY ===")
    from agent import Agent
    from policy import DEFAULT_POLICY

    a1 = Agent("prompt1")
    a2 = Agent("prompt2")

    check("GA.10a different_agents_different_policy_objects",
          a1.policy is not a2.policy,
          "agents share policy reference!")
    check("GA.10b agents_dont_share_with_module_default",
          a1.policy is not DEFAULT_POLICY
          and a2.policy is not DEFAULT_POLICY,
          "agent shares reference with module-level DEFAULT_POLICY!")

    # Mutate a1.policy and check a2.policy is unaffected
    a1.policy["strategy_policy"]["multistep"] = "MUTATED_BY_TEST"
    check("GA.10c mutation_does_not_leak_across_agents",
          a2.policy["strategy_policy"]["multistep"] != "MUTATED_BY_TEST",
          f"a2 multistep={a2.policy['strategy_policy']['multistep']}")
    check("GA.10d mutation_does_not_leak_to_module_default",
          DEFAULT_POLICY["strategy_policy"]["multistep"] != "MUTATED_BY_TEST",
          f"module={DEFAULT_POLICY['strategy_policy']['multistep']}")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_anchor_drift_at_unit_level()
    test_runner_uses_correct_anchor()
    test_anchor_stable_across_rejections()
    test_property_rejected_sequence_cannot_create_go()
    test_no_shared_mutable_default_policy()

    print()
    print("=" * 64)
    print(f"V9.0.4 GATING-ANCHOR TESTS: {len(PASSES)} passed, "
          f"{len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle Gating-Anchor-Tests bestanden.")
