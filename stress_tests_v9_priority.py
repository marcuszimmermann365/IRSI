"""
V9.0.2 Extended-Gate Priority Tests
======================================
Regression tests for the extended_decide priority bug found in
ChatGPT review v2: Council RED was being silently demoted to HOLD
or REVIEW when the attractor was UNCERTAIN or DESTRUCTIVE.

V7 D2 §6 (Nicht-Kompensation): a hard council veto must NOT be
softened by other signals. RED is structural, not a metric.

Without the fix:
  extended_decide("RED", "UNCERTAIN", ...) → HOLD  ✗
  extended_decide("RED", "DESTRUCTIVE", ...) → REVIEW  ✗

After the fix:
  extended_decide("RED", *, *, *) → STOP  ✓
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from attractor_engine import SystemState, Trends, extended_decide

PASSES = []
FAILS = []


def check(name, condition, details=""):
    if condition:
        PASSES.append(name)
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, details))
        print(f"  FAIL  {name}  {details}")


def make_state(sigma=0.5, l=0.5, o=0.5, d=0.3):
    return SystemState(sigma=sigma, l=l, o=o, d=d)


def test_council_red_priority():
    """ChatGPT v2 review fix: Council RED must always escalate to STOP."""
    print("\n=== EP: Extended-Gate Priority (ChatGPT v2) ===")

    state = make_state()
    trends_falling = Trends(d_sigma=-0.1, d_l=-0.1, d_o=-0.1, d_d=0.1)
    trends_rising = Trends(d_sigma=0.1, d_l=0.1, d_o=0.1, d_d=-0.1)

    # EP.1: Original ChatGPT failing case
    d, reason, _ = extended_decide("RED", "UNCERTAIN", None, state)
    check("EP.1 council_red_over_uncertain",
          d == "STOP" and reason == "council_red",
          f"got d={d!r} reason={reason!r}")

    # EP.2: Original ChatGPT failing case
    d, reason, _ = extended_decide("RED", "DESTRUCTIVE", trends_falling, state)
    check("EP.2 council_red_over_destructive",
          d == "STOP" and reason == "council_red",
          f"got d={d!r} reason={reason!r}")

    # EP.3: RED must override RESONANCE — the most dangerous case
    # (a system claiming RESONANCE while council says RED is the
    # exact pattern we want to block)
    d, reason, _ = extended_decide("RED", "RESONANCE", trends_rising, state)
    check("EP.3 council_red_over_resonance",
          d == "STOP" and reason == "council_red",
          f"got d={d!r} reason={reason!r}")

    # EP.4: RED + LOCK_IN
    d, reason, _ = extended_decide("RED", "LOCK_IN", None, state)
    check("EP.4 council_red_over_lock_in",
          d == "STOP" and reason == "council_red",
          f"got d={d!r} reason={reason!r}")

    # EP.5: RED with no trends — must still STOP
    d, reason, _ = extended_decide("RED", "UNCERTAIN", None, state)
    check("EP.5 council_red_no_trends_still_stops",
          d == "STOP",
          f"got d={d!r}")

    # EP.6: All trend directions × all attractors with RED
    all_red_stop = True
    failed_combos = []
    for attractor in ["UNCERTAIN", "DESTRUCTIVE", "RESONANCE", "LOCK_IN"]:
        for tr_name, tr in [("falling", trends_falling),
                             ("rising", trends_rising),
                             ("none", None)]:
            d, reason, _ = extended_decide("RED", attractor, tr, state)
            if d != "STOP":
                all_red_stop = False
                failed_combos.append((attractor, tr_name, d, reason))
    check("EP.6 council_red_always_stops_all_combos",
          all_red_stop,
          f"failed: {failed_combos}")


def test_existing_priorities_preserved():
    """Verify that the fix did not break OTHER priority orderings."""
    print("\n=== EP: Existing Priorities Preserved ===")

    state = make_state()
    trends_falling = Trends(d_sigma=-0.1, d_l=-0.1, d_o=-0.1, d_d=0.1)
    trends_rising = Trends(d_sigma=0.1, d_l=0.1, d_o=0.1, d_d=-0.1)

    # EP.7: GREEN + RESONANCE → GO
    d, reason, _ = extended_decide("GREEN", "RESONANCE", trends_rising, state)
    check("EP.7 green_resonance_still_go",
          d == "GO" and reason == "resonance",
          f"got d={d!r} reason={reason!r}")

    # EP.8: GREEN + UNCERTAIN → HOLD
    d, reason, _ = extended_decide("GREEN", "UNCERTAIN", None, state)
    check("EP.8 green_uncertain_still_hold",
          d == "HOLD" and reason == "attractor_uncertain",
          f"got d={d!r} reason={reason!r}")

    # EP.9: YELLOW + UNCERTAIN → HOLD
    d, reason, _ = extended_decide("YELLOW", "UNCERTAIN", None, state)
    check("EP.9 yellow_uncertain_still_hold",
          d == "HOLD",
          f"got d={d!r}")

    # EP.10: GREEN + DESTRUCTIVE + falling → REVIEW
    d, reason, _ = extended_decide("GREEN", "DESTRUCTIVE",
                                    trends_falling, state)
    check("EP.10 green_destructive_falling_still_review",
          d == "REVIEW" and reason == "destructive_trajectory",
          f"got d={d!r} reason={reason!r}")

    # EP.11: critical openness STOP still beats council
    # (critical thresholds remain pre-RED in priority — they are
    # state-based safety floors, not gate decisions)
    state_critical = make_state(o=0.05)  # below O_CRITICAL
    d, reason, _ = extended_decide("GREEN", "RESONANCE",
                                    trends_rising, state_critical)
    check("EP.11 critical_openness_still_stops_even_with_green",
          d == "STOP" and "openness" in reason,
          f"got d={d!r} reason={reason!r}")

    # EP.12: ROLLBACK has highest priority — even over council RED
    state_rollback = make_state(o=0.5)
    state_rollback.o_components["lock_in"] = 0.85
    d, reason, _ = extended_decide("RED", "LOCK_IN",
                                    trends_falling, state_rollback)
    # ROLLBACK requires both lock_in AND falling openness
    # (and trends_falling has d_o=-0.1 which is below -ATTRACTOR_EPSILON)
    check("EP.12 rollback_highest_priority_even_with_red",
          d == "ROLLBACK",
          f"got d={d!r} reason={reason!r}")


def test_priority_ordering_documented():
    """
    Verify the priority order matches the docstring:
      ROLLBACK → STOP (state-critical) → STOP (council_red) →
      REVIEW → HOLD → GO
    """
    print("\n=== EP: Priority Ordering ===")

    state = make_state()
    trends_falling = Trends(d_sigma=-0.1, d_l=-0.1, d_o=-0.1, d_d=0.1)

    # EP.13: Council RED beats REVIEW (DESTRUCTIVE + falling trends)
    # (this was the original bug — falling trends caused REVIEW
    # before RED was even considered)
    d, reason, _ = extended_decide("RED", "DESTRUCTIVE",
                                    trends_falling, state)
    check("EP.13 red_beats_review_for_destructive",
          d == "STOP",
          f"got d={d!r} reason={reason!r}")

    # EP.14: Council RED beats HOLD (UNCERTAIN attractor)
    d, reason, _ = extended_decide("RED", "UNCERTAIN", None, state)
    check("EP.14 red_beats_hold_for_uncertain",
          d == "STOP",
          f"got d={d!r} reason={reason!r}")


def test_external_commit_logging():
    """
    V9.0.2 ChatGPT v2 fix: external_commits must be populated when
    a mutation is accepted, so that "no data = no risk" cannot be
    silently asserted.
    """
    print("\n=== EC: External Commit Logging (ChatGPT v2) ===")
    from external_integrity import ExternalCommitLog, compute_cross_domain_openness

    # EC.1: Empty log → reversibility verified (the unsafe default)
    log = ExternalCommitLog()
    o_ext, o_combined, diag = compute_cross_domain_openness(0.5, log, {})
    check("EC.1 empty_log_default_state",
          isinstance(diag.get("external_reversibility_verified"), bool),
          f"diag={diag}")

    # EC.2: After recording, the log has entries
    log.record(action="policy_mutation_iter_0", iteration=0,
               irreversibility=0.4, rollback_available=True,
               verification_source="runner_self_report",
               domain="agent_policy", resolved=False)
    check("EC.2 record_increases_count",
          len(log.entries) == 1)

    # EC.3: unresolved() returns the new entry
    unresolved = log.unresolved()
    check("EC.3 unresolved_returns_new_entry",
          len(unresolved) == 1
          and unresolved[0]["action"] == "policy_mutation_iter_0")

    # EC.4: Self-reported entries flagged as unverified
    check("EC.4 runner_self_report_is_unverified_kind",
          log.has_unverified(),
          "self-report should count as unverified per A3 REQ")

    # EC.5: Resolved entries no longer count as unresolved
    log.entries[0]["resolved"] = True
    check("EC.5 resolved_entries_excluded_from_unresolved",
          len(log.unresolved()) == 0)

    # EC.6: Runner code path actually calls record() on GO
    # Verify by inspecting source
    with open(os.path.join(os.path.dirname(__file__),
                            "runner.py")) as f:
        runner_src = f.read()
    has_call = "external_commits.record(" in runner_src
    check("EC.6 runner_calls_external_commits_record_on_accept",
          has_call,
          "runner.py must invoke external_commits.record() on accept")


def test_human_override_fail_closed():
    """
    V9.0.2 ChatGPT v2 fix: production mode without policy_fn must
    fail-closed instead of silently using the simulation policy.
    """
    print("\n=== HO: HumanOverride fail-closed (ChatGPT v2) ===")
    from human_override import HumanOverrideLayer

    # FC.1: Default (simulation) construction works
    try:
        HumanOverrideLayer()
        check("HO.1 default_simulation_works", True)
    except Exception as e:
        check("HO.1 default_simulation_works", False, str(e))

    # FC.2: Explicit simulation works
    try:
        HumanOverrideLayer(simulation_mode=True)
        check("HO.2 explicit_simulation_works", True)
    except Exception as e:
        check("HO.2 explicit_simulation_works", False, str(e))

    # FC.3: Production with policy_fn works
    try:
        HumanOverrideLayer(simulation_mode=False,
                            policy_fn=lambda *a, **k: None)
        check("HO.3 production_with_policy_works", True)
    except Exception as e:
        check("HO.3 production_with_policy_works", False, str(e))

    # FC.4: Production WITHOUT policy_fn must fail
    raised = False
    try:
        HumanOverrideLayer(simulation_mode=False)
    except RuntimeError as e:
        raised = True
        # Message must mention the fail-closed reason
        msg = str(e)
        check("HO.4 production_no_policy_raises_runtime_error", True)
        check("HO.5 fail_closed_message_explains",
              "policy_fn" in msg and "human" in msg.lower(),
              f"msg={msg[:100]!r}")
    if not raised:
        check("HO.4 production_no_policy_raises_runtime_error", False,
              "did not raise")
        check("HO.5 fail_closed_message_explains", False, "no error")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_council_red_priority()
    test_existing_priorities_preserved()
    test_priority_ordering_documented()
    test_external_commit_logging()
    test_human_override_fail_closed()

    print()
    print("=" * 64)
    print(f"V9.0.2 PRIORITY TESTS: {len(PASSES)} passed, "
          f"{len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle Priority-Tests bestanden.")
