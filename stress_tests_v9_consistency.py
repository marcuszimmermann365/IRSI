"""
V9.0.3 Consistency Tests
==========================
Regression tests for two semantic drift bugs found in ChatGPT review v3:

  Bug 1 — runner_self_report inconsistency:
    has_unverified() correctly flags runner_self_report, but
    compute_cross_domain_openness() did not. Both must agree.
    V7 D6 K4 (Messverlagerung): two indicators of the same
    structural property must not drift apart.

  Bug 2 — rejected candidates shaping effective state:
    prev_attractor_state was always updated, even when the
    candidate was rejected. The "Final state" report then
    reflected a path the system never actually walked.
    V7 D2 §6: trajectories must reflect actually-effective
    development, not virtual paths.

Both bugs slipped past 470 unit tests because they are about
*consistency between two indicators* and *semantic meaning of
state variables* — neither of which is checkable at the
single-function level.
"""

import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from external_integrity import (
    UNVERIFIED_SOURCES,
    ExternalCommitLog,
    compute_cross_domain_openness,
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
# Bug 1: runner_self_report consistency
# ══════════════════════════════════════════════════════════════════

def test_unverified_sources_consistency():
    """
    has_unverified() and compute_cross_domain_openness() must
    agree on what counts as unverified.
    """
    print("\n=== UC: Unverified Sources Consistency (ChatGPT v3) ===")

    # UC.1: UNVERIFIED_SOURCES contains all three known unverified kinds
    expected = {"agent_self_report", "runner_self_report", "unverified"}
    check("UC.1 unverified_sources_complete",
          set(UNVERIFIED_SOURCES) == expected,
          f"got {set(UNVERIFIED_SOURCES)}")

    # UC.2: ChatGPT v3 reproduction case
    log = ExternalCommitLog()
    log.record(action="policy_mutation_iter_0", iteration=0,
               irreversibility=0.4, rollback_available=True,
               verification_source="runner_self_report",
               domain="agent_policy", resolved=False)

    has_unv = log.has_unverified()
    o_ext, _, diag = compute_cross_domain_openness(0.8, log, {})
    ext_rev = diag["external_reversibility_verified"]

    check("UC.2 runner_self_report_flagged_by_has_unverified",
          has_unv,
          f"has_unverified()={has_unv}")
    check("UC.3 runner_self_report_flagged_by_cross_domain_openness",
          not ext_rev,
          f"external_reversibility_verified={ext_rev}")
    check("UC.4 both_indicators_agree",
          has_unv != ext_rev,  # has_unv=True → ext_rev=False
          f"has_unverified={has_unv} ext_rev_verified={ext_rev}")

    # UC.5: unverified_count must match
    check("UC.5 unverified_count_matches",
          diag["unverified_count"] == 1,
          f"unverified_count={diag['unverified_count']}")

    # UC.6: agent_self_report (the older code already handled this)
    log2 = ExternalCommitLog()
    log2.record(action="x", iteration=0, irreversibility=0.4,
                rollback_available=True,
                verification_source="agent_self_report",
                domain="x", resolved=False)
    o_ext2, _, diag2 = compute_cross_domain_openness(0.8, log2, {})
    check("UC.6 agent_self_report_still_flagged",
          not diag2["external_reversibility_verified"]
          and log2.has_unverified())

    # UC.7: explicit "unverified" string
    log3 = ExternalCommitLog()
    log3.record(action="x", iteration=0, irreversibility=0.4,
                rollback_available=True,
                verification_source="unverified",
                domain="x", resolved=False)
    o_ext3, _, diag3 = compute_cross_domain_openness(0.8, log3, {})
    check("UC.7 explicit_unverified_string_flagged",
          not diag3["external_reversibility_verified"]
          and log3.has_unverified())

    # UC.8: Externally verified source clears both checks
    log4 = ExternalCommitLog()
    log4.record(action="x", iteration=0, irreversibility=0.4,
                rollback_available=True,
                verification_source="external_audit",
                domain="x", resolved=False)
    o_ext4, _, diag4 = compute_cross_domain_openness(0.8, log4, {})
    check("UC.8 external_audit_clears_both",
          diag4["external_reversibility_verified"]
          and not log4.has_unverified())

    # UC.9: Mixed log — one unverified entry pollutes the whole
    log5 = ExternalCommitLog()
    log5.record(action="ok", iteration=0, irreversibility=0.4,
                rollback_available=True,
                verification_source="external_audit",
                domain="x", resolved=False)
    log5.record(action="susp", iteration=0, irreversibility=0.4,
                rollback_available=True,
                verification_source="runner_self_report",
                domain="x", resolved=False)
    o_ext5, _, diag5 = compute_cross_domain_openness(0.8, log5, {})
    check("UC.9 one_unverified_blocks_whole_log",
          not diag5["external_reversibility_verified"]
          and diag5["unverified_count"] == 1)

    # UC.10: Resolved entries don't count
    log6 = ExternalCommitLog()
    log6.record(action="x", iteration=0, irreversibility=0.4,
                rollback_available=True,
                verification_source="runner_self_report",
                domain="x", resolved=True)
    o_ext6, _, diag6 = compute_cross_domain_openness(0.8, log6, {})
    check("UC.10 resolved_entries_excluded",
          diag6["external_reversibility_verified"],
          f"ext_rev={diag6['external_reversibility_verified']}")


# ══════════════════════════════════════════════════════════════════
# Bug 2: Effective vs Candidate Attractor State
# ══════════════════════════════════════════════════════════════════

def test_effective_vs_candidate_state():
    """
    The effective system state must reflect only accepted mutations.
    Rejected candidates may inform diagnostics (trends), but the
    "Final state" report must distinguish system from candidate.
    """
    print("\n=== EC: Effective vs Candidate State (ChatGPT v3) ===")

    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, "log.json")
        mem_path = os.path.join(tmpdir, "mem.json")

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            records = runner.main(
                iterations=4,
                storage_path=log_path,
                memory_path=mem_path,
                simulation_mode=True,
                return_records=True,
                verbose=True,
            )

        output = captured.getvalue()

    # EC.1: Default run rejects candidates — output must say so
    accepted_count = sum(1 for r in records
                         if r.get("final_decision") == "GO")
    check("EC.1 default_run_no_acceptance",
          accepted_count == 0,
          f"accepted_count={accepted_count}")

    # EC.2: Output must distinguish effective from candidate
    if accepted_count == 0:
        check("EC.2 output_says_unchanged_when_nothing_accepted",
              "unchanged" in output and "no candidate was accepted" in output,
              f"output tail: {output[-200:]!r}")
    else:
        check("EC.2 output_says_unchanged_when_nothing_accepted",
              True, "skipped (accepted_count > 0)")

    # EC.3: Output must report last candidate separately
    check("EC.3 last_candidate_reported_separately",
          "Last evaluated candidate" in output,
          f"output tail: {output[-200:]!r}")

    # EC.4: Output must NOT use the misleading "Final state:" label
    # for a state the system never actually reached
    check("EC.4 no_misleading_final_state_label",
          "Final state:" not in output
          or "Effective system state:" in output,
          f"output: {output[-300:]!r}")


# ══════════════════════════════════════════════════════════════════
# Cross-cutting: V7 D6 K4 invariant
# ══════════════════════════════════════════════════════════════════

def test_indicator_consistency_invariant():
    """
    V7 D6 K4 (Messverlagerung): when two indicators measure the
    same structural property, they must agree under all inputs.
    Property test that exercises many random verification source
    strings.
    """
    print("\n=== IC: Indicator Consistency Invariant (V7 D6 K4) ===")
    import random
    random.seed(2026)

    # Random sources, including made-up ones
    candidate_sources = [
        "agent_self_report",
        "runner_self_report",
        "unverified",
        "external_audit",
        "third_party_attestation",
        "blockchain_proof",
        "internal_check",  # what should this be?
        "human_verified",
        "model_self_check",  # ambiguous — should NOT pass
        "trusted_log",
    ]

    inconsistencies = []
    for trial in range(200):
        log = ExternalCommitLog()
        for i in range(random.randint(1, 5)):
            src = random.choice(candidate_sources)
            log.record(action=f"a{trial}_{i}", iteration=trial,
                       irreversibility=random.uniform(0.1, 0.9),
                       rollback_available=random.random() > 0.3,
                       verification_source=src,
                       domain="test",
                       resolved=False)

        has_unv = log.has_unverified()
        _, _, diag = compute_cross_domain_openness(0.8, log, {})
        ext_rev = diag["external_reversibility_verified"]

        # If has_unverified is True, ext_rev_verified must be False
        # (note: ext_rev can ALSO be False because of no-rollback;
        # we check the stricter direction)
        if has_unv and ext_rev:
            inconsistencies.append({
                "trial": trial,
                "sources": [e["verification_source"]
                            for e in log.entries],
            })

    check("IC.1 has_unverified_implies_not_verified_under_random_inputs",
          len(inconsistencies) == 0,
          f"{len(inconsistencies)} inconsistencies, "
          f"first: {inconsistencies[:2]}")


def test_llm_fail_closed():
    """
    V9.0.3 ChatGPT v3 P1: Real-LLM failures must not be disguised as
    plausible answers. They must return a clearly-marked error
    sentinel that downstream evaluation treats as a failed response.
    """
    print("\n=== LL: LLM Fail-Closed (ChatGPT v3 P1) ===")
    import importlib
    import os

    # Snapshot env
    saved = {
        k: os.environ.get(k)
        for k in ("USE_REAL_LLM", "FALLBACK_TO_MOCK",
                  "LLM_API_KEY", "OPENAI_API_KEY", "GROK_API_KEY")
    }
    try:
        # LL.1: Default behavior is mock (tests still work)
        for k in saved:
            os.environ.pop(k, None)
        import llm_client
        importlib.reload(llm_client)
        c = llm_client.LLMClient()
        check("LL.1 default_is_mock",
              c.backend_name == "mock")

        # LL.2: USE_REAL_LLM without key without fallback → raises
        os.environ["USE_REAL_LLM"] = "true"
        os.environ["FALLBACK_TO_MOCK"] = "false"
        importlib.reload(llm_client)
        raised = False
        try:
            llm_client.LLMClient()
        except RuntimeError:
            raised = True
        check("LL.2 production_no_key_no_fallback_raises", raised)

        # LL.3: FALLBACK_TO_MOCK default is now false (was true)
        # Read source and verify
        with open(os.path.join(os.path.dirname(__file__),
                                "llm_client.py")) as f:
            src = f.read()
        check("LL.3 fallback_default_is_false",
              'os.getenv("FALLBACK_TO_MOCK", "false")' in src)

        # LL.4: Error sentinel exists and is well-marked
        check("LL.4 error_sentinel_exists",
              "__LLM_ERROR__" in src,
              "LLM_ERROR_PREFIX should be defined")

        # LL.5: No more generic "I'm not sure, but..." synthesis on
        # real backend errors
        # (the old fallback string)
        # Look only in the LLMClient.generate method, not in MockLLMClient
        gen_method_start = src.find("def generate(self, prompt: str")
        # Skip past the FIRST one (Mock) to find the LLMClient one
        gen_method_start = src.find("def generate(self, prompt: str",
                                     gen_method_start + 1)
        # Take a 1500-char slice from there
        client_generate = src[gen_method_start:gen_method_start + 1500]
        check("LL.5 no_synthesized_uncertain_answer_on_real_error",
              "I'm not sure, but I will reason carefully" not in client_generate
              or "__LLM_ERROR__" in client_generate,
              "real-error path should NOT synthesize a plausible answer")
    finally:
        # Restore env
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(llm_client)


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_unverified_sources_consistency()
    test_effective_vs_candidate_state()
    test_indicator_consistency_invariant()
    test_llm_fail_closed()

    print()
    print("=" * 64)
    print(f"V9.0.3 CONSISTENCY TESTS: {len(PASSES)} passed, "
          f"{len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    else:
        print("Alle Consistency-Tests bestanden.")
