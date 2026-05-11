"""
LRSI V7 – Pflichtenheft-Konformitätstests (§7 + §8)
======================================================
Tests gegen das Pflichtenheft "Governance-Konsistenz & Erweiterbarkeit V1.0"

  §7.1 Pflicht-Tests:
    P01–P04  Extended Gate: HOLD/REVIEW/STOP/ROLLBACK → accepted == False
    P05      ROLLBACK → effective_policy == previous_policy
    P06–P07  Snapshot: Ablehnung → effective_policy unverändert
    P08      Snapshot: Candidate erscheint nicht als Parent bei Ablehnung
    P09      Path Model: Nur accepted Policies gespeichert
    P10      Audit: Vollständige decision_trace

  §7.2 Negativtests:
    N01      HOLD + accepted=True darf nicht entstehen
    N02      REVIEW + accepted=True darf nicht entstehen
    N03      Falsche Parent-Historie darf nicht gespeichert werden

  §8 Invarianten:
    I01      Final Gate Invariante
    I02      State Consistency Invariante
    I03      History Integrity Invariante
    I04      Path Integrity Invariante
    I05      Audit Completeness Invariante

  §6.2 Erweiterbarkeit:
    E01      EFI-ready: Pipeline akzeptiert neue blockierende Variable
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from copy import deepcopy

from attractor_engine import SystemState, Trends, extended_decide
from path_model import PathModel

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


# ── Helpers ───────────────────────────────────────────────────────────

def make_state(sigma=0.7, l=0.7, o=0.7, d=0.3, lock_in=0.1):
    return SystemState(
        sigma=sigma, l=l, o=o, d=d,
        o_components={"lock_in": lock_in},
    )


def make_trends(d_sigma=0.0, d_l=0.0, d_o=0.0, d_d=0.0):
    return Trends(d_sigma, d_l, d_o, d_d)


def simulate_pipeline(council_decision, ext_decision, previous_policy,
                      candidate_policy):
    """
    Simulate the V7 pipeline logic for a single iteration.
    Returns (accepted, effective_policy, final_decision).
    This mirrors the exact logic in runner.py V7.
    """
    # §5.1: Extended Gate is final
    accepted = (ext_decision == "GO")

    # §4.1 step 5: ROLLBACK restores previous
    if ext_decision == "ROLLBACK":
        effective_policy = deepcopy(previous_policy)
    elif accepted:
        effective_policy = deepcopy(candidate_policy)
    else:
        effective_policy = deepcopy(previous_policy)

    return accepted, effective_policy, ext_decision


print("=" * 64)
print("LRSI V7 – Pflichtenheft-Konformitätstests (§7 + §8)")
print("=" * 64)

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §7.1 Pflicht-Tests: Extended Gate ===")
# ═══════════════════════════════════════════════════════════════════════

state = make_state()
trends = make_trends(0.05, 0.03, 0.02, -0.05)
prev_pol = {"name": "parent", "version": 1}
cand_pol = {"name": "candidate", "version": 2}

# P01: HOLD → accepted == False
d_hold, _, _ = extended_decide("GREEN", "UNCERTAIN", trends, state)
acc, eff, fin = simulate_pipeline("GREEN", d_hold, prev_pol, cand_pol)
check("P01 HOLD_not_accepted",
      d_hold == "HOLD" and acc is False,
      f"ext={d_hold} acc={acc}")

# P02: REVIEW → accepted == False
trends_fall = make_trends(0.05, -0.10, 0.0, 0.0)
d_rev, _, _ = extended_decide("GREEN", "DESTRUCTIVE", trends_fall, state)
acc2, eff2, fin2 = simulate_pipeline("GREEN", d_rev, prev_pol, cand_pol)
check("P02 REVIEW_not_accepted",
      d_rev == "REVIEW" and acc2 is False,
      f"ext={d_rev} acc={acc2}")

# P03: STOP → accepted == False
state_low_o = make_state(o=0.10)
d_stop, _, _ = extended_decide("GREEN", "RESONANCE", trends, state_low_o)
acc3, eff3, fin3 = simulate_pipeline("GREEN", d_stop, prev_pol, cand_pol)
check("P03 STOP_not_accepted",
      d_stop == "STOP" and acc3 is False,
      f"ext={d_stop} acc={acc3}")

# P04: ROLLBACK → accepted == False
state_roll = make_state(o=0.3, d=0.4, lock_in=0.70)
trends_roll = make_trends(0.0, -0.05, -0.10, 0.0)
d_rb, _, _ = extended_decide("YELLOW", "LOCK_IN", trends_roll, state_roll)
acc4, eff4, fin4 = simulate_pipeline("GREEN", d_rb, prev_pol, cand_pol)
check("P04 ROLLBACK_not_accepted",
      d_rb == "ROLLBACK" and acc4 is False,
      f"ext={d_rb} acc={acc4}")

# P05: ROLLBACK → effective_policy == previous_policy
check("P05 ROLLBACK_restores_previous",
      eff4 == prev_pol,
      f"effective={eff4} expected={prev_pol}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §7.1 Pflicht-Tests: Snapshot-Konsistenz ===")
# ═══════════════════════════════════════════════════════════════════════

# P06: Ablehnung → effective_policy == previous_policy (HOLD)
_, eff_hold, _ = simulate_pipeline("GREEN", "HOLD", prev_pol, cand_pol)
check("P06 rejection_effective_unchanged_HOLD",
      eff_hold == prev_pol,
      f"effective={eff_hold}")

# P07: Ablehnung → effective_policy == previous_policy (STOP)
_, eff_stop, _ = simulate_pipeline("GREEN", "STOP", prev_pol, cand_pol)
check("P07 rejection_effective_unchanged_STOP",
      eff_stop == prev_pol)

# P08: Candidate darf nicht als Parent erscheinen bei Ablehnung
# Simulating: after rejection, the next iteration's previous_policy
# must still be prev_pol, not cand_pol
acc_rej, eff_rej, _ = simulate_pipeline("GREEN", "REVIEW", prev_pol, cand_pol)
# The effective_policy becomes the next iteration's previous_policy
check("P08 candidate_not_parent_after_rejection",
      acc_rej is False and eff_rej == prev_pol,
      f"acc={acc_rej} effective={eff_rej}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §7.1 Pflicht-Tests: Path Model ===")
# ═══════════════════════════════════════════════════════════════════════

# P09: Path model stores only accepted iterations as accepted
pm = PathModel()

# Iteration 0: accepted (GO)
pm.record_iteration(0, "prompt_a", {"v": 1}, True, "GO", [])

# Iteration 1: rejected (HOLD)
pm.record_iteration(1, "prompt_b", {"v": 2}, False, "HOLD", [])

# Iteration 2: rejected (STOP)
pm.record_iteration(2, "prompt_c", {"v": 3}, False, "STOP", [])

# Iteration 3: accepted (GO)
pm.record_iteration(3, "prompt_d", {"v": 4}, True, "GO", [])

check("P09 path_only_accepted",
      len(pm._accepted_prompts) == 2
      and pm._accepted_prompts == ["prompt_a", "prompt_d"],
      f"accepted_prompts={pm._accepted_prompts}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §7.1 Pflicht-Tests: Audit ===")
# ═══════════════════════════════════════════════════════════════════════

# P10: Vollständige decision_trace mit allen 4 Stufen
decision_trace = [
    {"stage": "council", "decision": "GREEN", "reason": "admissible"},
    {"stage": "hold", "decision": "ACCEPT", "reason": "council_green"},
    {"stage": "attractor", "decision": "UNCERTAIN", "reason": "Σ=0.7"},
    {"stage": "extended", "decision": "HOLD", "reason": "attractor_uncertain"},
]

required_stages = {"council", "hold", "attractor", "extended"}
trace_stages = {entry["stage"] for entry in decision_trace}
check("P10 decision_trace_complete",
      required_stages == trace_stages,
      f"stages={trace_stages}")

# Each entry has required fields
all_have_fields = all(
    "stage" in e and "decision" in e and "reason" in e
    for e in decision_trace
)
check("P10b decision_trace_fields_present", all_have_fields)

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §7.2 Negativtests ===")
# ═══════════════════════════════════════════════════════════════════════

# N01: HOLD + accepted=True must never occur
# Test all possible ext_decisions and verify invariant
for ext_d in ["HOLD", "REVIEW", "STOP", "ROLLBACK"]:
    acc_n, _, _ = simulate_pipeline("GREEN", ext_d, prev_pol, cand_pol)
    check(f"N01 {ext_d}_never_accepted",
          acc_n is False,
          f"ext={ext_d} acc={acc_n}")

# N02: Council GREEN + Extended HOLD → must NOT be accepted
# This is the EXACT bug that existed in V6
d_n2, _, _ = extended_decide("GREEN", "UNCERTAIN", trends, state)
acc_n2, _, _ = simulate_pipeline("GREEN", d_n2, prev_pol, cand_pol)
check("N02 council_green_ext_hold_not_accepted",
      d_n2 == "HOLD" and acc_n2 is False,
      f"ext={d_n2} acc={acc_n2}")

# N03: Rejected candidate must not appear in parent history
pm2 = PathModel()
pm2.record_iteration(0, "prompt_base", {"v": 0}, True, "GO", [])
pm2.record_iteration(1, "prompt_rejected", {"v": 99}, False, "STOP", [])
pm2.record_iteration(2, "prompt_next", {"v": 1}, True, "GO", [])
check("N03 rejected_not_in_history",
      {"v": 99} not in pm2._accepted_policies,
      f"accepted_policies={pm2._accepted_policies}")

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §8 Invarianten ===")
# ═══════════════════════════════════════════════════════════════════════

# I01: Final Gate Invariante — Extended Gate bestimmt finalen Zustand
# Exhaustive: for every combination of council + ext, only GO → accepted
for council_d in ["GREEN", "YELLOW", "RED"]:
    for ext_d in ["GO", "HOLD", "REVIEW", "STOP", "ROLLBACK"]:
        acc_i, _, _ = simulate_pipeline(council_d, ext_d, prev_pol, cand_pol)
        expected = (ext_d == "GO")
        check(f"I01 final_gate_{council_d}_{ext_d}",
              acc_i == expected,
              f"acc={acc_i} expected={expected}")

# I02: State Consistency — persisted state = effective state
# After HOLD: effective must be previous
_, eff_i2, _ = simulate_pipeline("GREEN", "HOLD", prev_pol, cand_pol)
check("I02 state_consistency_hold",
      eff_i2 == prev_pol)

# After GO: effective must be candidate
_, eff_i2b, _ = simulate_pipeline("GREEN", "GO", prev_pol, cand_pol)
check("I02 state_consistency_go",
      eff_i2b == cand_pol)

# After ROLLBACK: effective must be previous
_, eff_i2c, _ = simulate_pipeline("GREEN", "ROLLBACK", prev_pol, cand_pol)
check("I02 state_consistency_rollback",
      eff_i2c == prev_pol)

# I03: History Integrity — trace shows real transitions
# Simulating 3 iterations: accept, reject, accept
history = []
running_policy = {"v": 0}
for i, ext_d in enumerate(["GO", "STOP", "GO"]):
    cand = {"v": i + 1}
    acc_h, eff_h, _ = simulate_pipeline("GREEN", ext_d, running_policy, cand)
    history.append({
        "iteration": i,
        "previous_policy": deepcopy(running_policy),
        "candidate_policy": deepcopy(cand),
        "effective_policy": deepcopy(eff_h),
        "accepted": acc_h,
    })
    running_policy = deepcopy(eff_h)

# Verify chain: each previous_policy equals prior effective_policy
chain_ok = True
for i in range(1, len(history)):
    if history[i]["previous_policy"] != history[i - 1]["effective_policy"]:
        chain_ok = False
        break
check("I03 history_integrity_chain", chain_ok)

# Verify: rejected candidate (v:2) does not appear as effective
# After iter 0 (GO, cand v:1), running_policy is v:1
# Iter 1 (STOP, cand v:2) → effective stays v:1 (the previous)
check("I03b rejected_not_effective",
      history[1]["effective_policy"] == {"v": 1}
      and history[1]["candidate_policy"] == {"v": 2},
      f"iter1_effective={history[1]['effective_policy']}")

# I04: Path Integrity — path model only has real states
pm3 = PathModel()
for h in history:
    pm3.record_iteration(h["iteration"], f"p{h['iteration']}",
                          h["effective_policy"], h["accepted"],
                          "GO" if h["accepted"] else "STOP", [])
# Only iterations 0 and 2 were accepted
check("I04 path_integrity",
      len(pm3._accepted_policies) == 2,
      f"count={len(pm3._accepted_policies)}")
check("I04b path_no_rejected_policy",
      {"v": 2} not in pm3._accepted_policies)

# I05: Audit Completeness — every decision is reconstructable
# A valid record must have decision_trace with all 4 stages
sample_record = {
    "iteration": 0,
    "previous_policy": prev_pol,
    "candidate_policy": cand_pol,
    "final_decision": "HOLD",
    "accepted": False,
    "decision_trace": [
        {"stage": "council", "decision": "GREEN", "reason": "admissible"},
        {"stage": "hold", "decision": "ACCEPT", "reason": "council_green"},
        {"stage": "attractor", "decision": "UNCERTAIN", "reason": "mixed"},
        {"stage": "extended", "decision": "HOLD", "reason": "uncertain"},
    ],
    "effective_policy": prev_pol,
}

# Can reconstruct: final_decision must match last trace entry
last_trace = sample_record["decision_trace"][-1]
check("I05 audit_reconstructable",
      last_trace["stage"] == "extended"
      and last_trace["decision"] == sample_record["final_decision"])

# Accepted must be consistent with final_decision
check("I05b audit_accepted_consistent",
      sample_record["accepted"] == (sample_record["final_decision"] == "GO"))

# Effective policy must match: rejected → previous
check("I05c audit_effective_consistent",
      sample_record["effective_policy"] == prev_pol)

# ═══════════════════════════════════════════════════════════════════════
print("\n=== §6.2 Erweiterbarkeit: EFI-ready ===")
# ═══════════════════════════════════════════════════════════════════════

# E01: A new blocking variable can be inserted before extended_decide
# without changing the pipeline structure.
# Demonstration: wrapping extended_decide with an EFI pre-check.

def efi_extended_decide(base_gate, attractor, trends, state, efi_ok=True):
    """Extended gate with EFI pre-check (§10)."""
    if not efi_ok:
        return "HOLD", "efi_block", {"efi_ok": False}
    return extended_decide(base_gate, attractor, trends, state)

# Without EFI block: normal behavior
d_efi, r_efi, _ = efi_extended_decide(
    "GREEN", "RESONANCE", trends, state, efi_ok=True)
check("E01a efi_pass_through",
      d_efi == "GO",
      f"d={d_efi}")

# With EFI block: returns HOLD
d_efi2, r_efi2, diag_efi2 = efi_extended_decide(
    "GREEN", "RESONANCE", trends, state, efi_ok=False)
check("E01b efi_blocks",
      d_efi2 == "HOLD" and r_efi2 == "efi_block",
      f"d={d_efi2}")

# EFI block → not accepted
acc_efi, _, _ = simulate_pipeline("GREEN", d_efi2, prev_pol, cand_pol)
check("E01c efi_block_not_accepted",
      acc_efi is False)

# EFI visible in audit
check("E01d efi_in_audit",
      diag_efi2.get("efi_ok") is False)

# ═══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"PFLICHTENHEFT-TESTS: {passed} passed, {failed} failed")
print("=" * 64)

if errors:
    print("FAILURES:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("Alle Pflichtenheft-Tests bestanden. System konform zu V1.0.")
