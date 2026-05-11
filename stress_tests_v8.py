"""
LRSI V8 – Stress Tests (Pareto Admissibility + DGM Bridge)
=============================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dgm_bridge import DGMRunnerBridge
from pareto_admissibility import (
    is_admissible,
    pareto_dominates,
    pareto_front,
    pareto_quality,
    select_within_admissible,
)

passed = 0; failed = 0; errors = []

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {name}")
    else:
        failed += 1; print(f"  FAIL  {name}  ({detail})"); errors.append(name)

print("=" * 64)
print("LRSI V8 – Pareto Admissibility + DGM Bridge Tests")
print("=" * 64)

# ═══════════════════════════════════════════════════════════════
print("\n=== Pareto Admissibility ===")

# Admissible state
s_good = {"sigma": 0.7, "l": 0.8, "o": 0.6, "d": 0.2}
ok, v = is_admissible(s_good)
check("PA.1 good_admissible", ok and len(v) == 0)

# O below floor
s_low_o = {"sigma": 0.7, "l": 0.8, "o": 0.1, "d": 0.2}
ok2, v2 = is_admissible(s_low_o)
check("PA.2 low_o_inadmissible", not ok2 and any("o_below" in x for x in v2))

# D above ceiling
s_high_d = {"sigma": 0.7, "l": 0.8, "o": 0.6, "d": 0.8}
ok3, v3 = is_admissible(s_high_d)
check("PA.3 high_d_inadmissible", not ok3)

# Blocker active
ok4, v4 = is_admissible(s_good, blocker_active=True)
check("PA.4 blocker_inadmissible", not ok4)

# ═══════════════════════════════════════════════════════════════
print("\n=== Pareto Dominance ===")

a = {"sigma": 0.8, "l": 0.8, "o": 0.7, "d": 0.2}
b = {"sigma": 0.7, "l": 0.7, "o": 0.6, "d": 0.3}
check("PD.1 a_dominates_b", pareto_dominates(a, b))
check("PD.2 b_not_dominates_a", not pareto_dominates(b, a))

# Equal states don't dominate
check("PD.3 equal_no_dominance", not pareto_dominates(a, a))

# Incomparable (trade-off)
c = {"sigma": 0.9, "l": 0.6, "o": 0.7, "d": 0.2}
check("PD.4 incomparable", not pareto_dominates(a, c) and not pareto_dominates(c, a))

# ═══════════════════════════════════════════════════════════════
print("\n=== Pareto Front ===")

candidates = [
    {"sigma": 0.8, "l": 0.8, "o": 0.7, "d": 0.2},  # 0: front
    {"sigma": 0.7, "l": 0.7, "o": 0.6, "d": 0.3},  # 1: dominated by 0
    {"sigma": 0.9, "l": 0.6, "o": 0.7, "d": 0.2},  # 2: front (trade-off with 0)
    {"sigma": 0.5, "l": 0.5, "o": 0.5, "d": 0.5},  # 3: dominated
]
front = pareto_front(candidates)
check("PF.1 front_size", len(front) == 2, f"front={front}")
check("PF.2 front_contains_0", 0 in front)
check("PF.3 front_contains_2", 2 in front)
check("PF.4 dominated_excluded", 1 not in front and 3 not in front)

# ═══════════════════════════════════════════════════════════════
print("\n=== Pareto Quality (non-scalar) ===")

q = pareto_quality(s_good)
check("PQ.1 has_profile", "quality_profile" in q)
check("PQ.2 no_scalar_gate", isinstance(q["quality_profile"], dict))
check("PQ.3 display_only", "_display_composite" in q)

# ═══════════════════════════════════════════════════════════════
print("\n=== Select Within Admissible ===")

mixed = [
    {"sigma": 0.8, "l": 0.8, "o": 0.6, "d": 0.2},  # admissible, front
    {"sigma": 0.7, "l": 0.8, "o": 0.1, "d": 0.2},  # inadmissible (low O)
    {"sigma": 0.9, "l": 0.6, "o": 0.5, "d": 0.3},  # admissible, front
    {"sigma": 0.5, "l": 0.5, "o": 0.5, "d": 0.5},  # admissible, dominated
]
adm, front_idx, diag = select_within_admissible(mixed)
check("SA.1 admissible_count", len(adm) == 3, f"adm={adm}")
check("SA.2 inadmissible_excluded", 1 not in adm)
check("SA.3 front_within_admissible", len(front_idx) == 2, f"front={front_idx}")

# All inadmissible
all_bad = [
    {"sigma": 0.01, "l": 0.1, "o": 0.05, "d": 0.9},
    {"sigma": 0.02, "l": 0.1, "o": 0.05, "d": 0.9},
]
adm2, front2, diag2 = select_within_admissible(all_bad)
check("SA.4 no_admissible", len(adm2) == 0)

# ═══════════════════════════════════════════════════════════════
print("\n=== DGM-Runner Bridge ===")

bridge = DGMRunnerBridge()

# Wrap a normal mutation
prompt_meta = {"new_prompt": "test", "original_prompt": "base"}
policy_meta = {"description": "suppressed_by_mode", "new_policy": {}}
prop = bridge.wrap_mutation(prompt_meta, policy_meta, iteration=0)
check("BR.1 proposal_created", prop.change_id is not None)

# Pre-check passes for normal mutation
ok_b, reason_b, _ = bridge.pre_check(prop)
check("BR.2 pre_check_passes", ok_b, f"reason={reason_b}")

# Pre-check fails during hold
bridge.enter_hold("test_hold")
ok_h, reason_h, _ = bridge.pre_check(prop)
check("BR.3 hold_blocks", not ok_h and "hold" in reason_h)
bridge.exit_hold("test_done")

# Post-check with admissible state
from attractor_engine import SystemState

good_state = SystemState(sigma=0.7, l=0.8, o=0.6, d=0.2)
adm_ok, quality_ok, diag_ok = bridge.post_check(
    good_state, good_state, prop)
check("BR.4 admissible_state", adm_ok)

# Post-check with inadmissible state (low O)
bad_state = SystemState(sigma=0.7, l=0.8, o=0.1, d=0.2)
adm_bad, _, diag_bad = bridge.post_check(bad_state, bad_state, prop)
check("BR.5 inadmissible_state", not adm_bad)

# Post-check with blocker active
adm_block, _, _ = bridge.post_check(
    good_state, good_state, prop, drel_status="RED")
check("BR.6 blocker_blocks", not adm_block)

# Audit trail
audit = bridge.get_audit()
check("BR.7 audit_populated", len(audit) >= 3)

# ═══════════════════════════════════════════════════════════════
print("\n=== V8 Integration: Pipeline Order ===")

# The key V8 invariant: DGM pre-check happens BEFORE governance,
# Pareto admissibility happens BEFORE Extended Gate

# Simulate: mutation blocked by DGM → governance never runs
bridge2 = DGMRunnerBridge()
bridge2.enter_hold("truth_check_failed")
prop2 = bridge2.wrap_mutation(prompt_meta, policy_meta, 0)
ok_int, _, _ = bridge2.pre_check(prop2)
check("INT.1 dgm_blocks_before_governance", not ok_int)
bridge2.exit_hold("resolved")

# Simulate: governance passes but Pareto inadmissible → blocked
# (low O state passes attractor but fails Pareto floor)
bridge3 = DGMRunnerBridge()
prop3 = bridge3.wrap_mutation(prompt_meta, policy_meta, 0)
bridge3.pre_check(prop3)
marginal = SystemState(sigma=0.5, l=0.4, o=0.15, d=0.5)
adm_m, _, _ = bridge3.post_check(marginal, marginal, prop3)
check("INT.2 pareto_blocks_marginal", not adm_m)

# Simulate: fully admissible candidate → passes all checks
bridge4 = DGMRunnerBridge()
prop4 = bridge4.wrap_mutation(prompt_meta, policy_meta, 0)
bridge4.pre_check(prop4)
excellent = SystemState(sigma=0.8, l=0.85, o=0.7, d=0.15)
adm_e, q_e, _ = bridge4.post_check(excellent, excellent, prop4)
check("INT.3 excellent_passes", adm_e)
check("INT.4 quality_profile_not_scalar",
      isinstance(q_e.get("quality_profile"), dict))

# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"V8 TESTS: {passed} passed, {failed} failed")
print("=" * 64)
if errors:
    print("FAILURES:"); [print(f"  - {e}") for e in errors]; sys.exit(1)
else:
    print("Alle V8-Tests bestanden.")
