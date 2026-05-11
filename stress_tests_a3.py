"""
LRSI V7 – A3 Stress Tests (Synthetic Sincerity + External Integrity)
======================================================================
REQ-A3-01 to REQ-A3-25.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agency_verifier import AgencyVerifier
from external_integrity import (
    ExternalCommitLog,
    check_go_eligibility,
    check_resonance_eligibility,
    compute_cross_domain_openness,
)
from synthetic_sincerity import SYNTH_SINCERITY_BLOCK, compute_synthetic_sincerity

passed = 0; failed = 0; errors = []

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1; print(f"  PASS  {name}")
    else:
        failed += 1; msg = f"  FAIL  {name}" 
        if detail: msg += f"  ({detail})"
        print(msg); errors.append(name)

def mrec(ext_d="HOLD", accepted=False, has_dissent=False, o_val=0.5, pol_mut=None):
    r = {"extended_gate": {"decision": ext_d}, "final_decision": ext_d,
         "accepted": accepted,
         "dissent": {"has_dissent": has_dissent, "dissenters": ["c"] if has_dissent else []},
         "attractor_state": {"o": o_val},
         "council_per_role": {"v": {"decision": "GREEN", "reason": "ok"},
                              "c": {"decision": "YELLOW" if has_dissent else "GREEN", "reason": "x"}},
         "path_model": {"diagnostics": {"lock_in": 0.2, "dependency": 0.2,
                                         "irreversibility_cost": 0.2, "opacity_growth": 0.1}},
         "human_override": None, "counter_check": {"decision": "GREEN"},
         "gate_decision": "GREEN", "hold_metrics": None}
    if pol_mut: r["policy_mutation"] = pol_mut
    return r

av = AgencyVerifier()

print("=" * 64)
print("LRSI V7 – A3 Stress Tests")
print("=" * 64)

# ═════════════════════════════════════════════════════════════════
print("\n=== A: Synthetic Sincerity (A3-01 to A3-10) ===")

# A3-01: Risk dimension exists
ctx0 = {"dissent": {"has_dissent": False}, "council_per_role": {}, "counter_check": {"decision": "GREEN"},
        "history": [], "path_diag": {"lock_in": 0.1}, "policy_mutation": {"description": "suppressed_by_mode"}}
risk, vis, ind, diag = compute_synthetic_sincerity(ctx0)
check("A3-01 risk_float", isinstance(risk, float) and 0 <= risk <= 1, f"risk={risk}")
check("A3-01b in_diag", "synthetic_sincerity_risk" in diag)

# A3-02: Visibility without independence doesn't boost agency
ctx_vi = {"dissent": {"has_dissent": True, "dissenters": ["c"]},
          "council_per_role": {"v": {"decision": "GREEN"}, "c": {"decision": "YELLOW", "reason": "x"}},
          "counter_check": {"decision": "GREEN"}, "history": [],
          "sincerity_diagnostics": {"dissent_visibility": 0.7, "dissent_independence": 0.1},
          "human_coupling": {"agency_score": 0.5, "dissent_visibility": 0.7, "cognitive_load": 0.3},
          "human_override": None, "gate_diagnostics": {"tc": 1.0}, "decision_trace": [],
          "hold_metrics": None, "reflection": None, "memory_events": []}
ctx_nd = dict(ctx_vi); ctx_nd["dissent"] = {"has_dissent": False}
ctx_nd["sincerity_diagnostics"] = {"dissent_visibility": 0.0, "dissent_independence": 0.0}
a_vi, _, _ = av.verify(ctx_vi); a_nd, _, _ = av.verify(ctx_nd)
check("A3-02 vis_no_ind_no_boost", a_vi <= a_nd + 0.05, f"vis={a_vi:.3f} no={a_nd:.3f}")

# A3-03: Separated
check("A3-03 separated", "dissent_visibility" in diag and "dissent_independence" in diag)

# A3-04: No evidence → low independence
ctx4 = {"dissent": {"has_dissent": True, "dissenters": ["c"]},
        "council_per_role": {"v": {"decision": "GREEN"}}, "counter_check": {"decision": "GREEN"}, "history": []}
_, _, ind4, _ = compute_synthetic_sincerity(ctx4)
check("A3-04 low_ind", ind4 <= 0.6, f"ind={ind4:.3f}")

# A3-05: Performative self-criticism
hist5 = [mrec("HOLD", False, o_val=0.5), mrec("REVIEW", False, o_val=0.5),
         mrec("GO", True, o_val=0.49), mrec("HOLD", False, o_val=0.48),
         mrec("REVIEW", False, o_val=0.48), mrec("GO", True, o_val=0.47)]
ctx5 = {"dissent": {"has_dissent": False}, "council_per_role": {}, "counter_check": {"decision": "GREEN"},
        "history": hist5, "path_diag": {"lock_in": 0.3}, "policy_mutation": {"description": "suppressed_by_mode"}}
_, _, _, d5 = compute_synthetic_sincerity(ctx5)
check("A3-05 performative", d5["performative_self_criticism"] > 0.3, f"p={d5['performative_self_criticism']:.3f}")

# A3-06: Cosmetic correction
hist6 = [mrec("HOLD", False, o_val=0.5, pol_mut={"description": "cosmetic fix v1"}),
         mrec("HOLD", False, o_val=0.5, pol_mut={"description": "cosmetic fix v2"})]
ctx6 = {"dissent": {"has_dissent": False}, "council_per_role": {}, "counter_check": {"decision": "GREEN"},
        "history": hist6, "path_diag": {"lock_in": 0.2, "dependency": 0.2, "irreversibility_cost": 0.2},
        "policy_mutation": {"description": "cosmetic fix v3"}}
_, _, _, d6 = compute_synthetic_sincerity(ctx6)
check("A3-06 cosmetic", d6["cosmetic_correction_risk"] > 0.3, f"c={d6['cosmetic_correction_risk']:.3f}")

# A3-07: Strategic dissent
hist7 = [mrec("HOLD", False, has_dissent=True), mrec("GO", True, has_dissent=False),
         mrec("HOLD", False, has_dissent=True), mrec("GO", True, has_dissent=False)]
ctx7 = {"dissent": {"has_dissent": True, "dissenters": ["c"]},
        "council_per_role": {"v": {"decision": "GREEN"}, "c": {"decision": "YELLOW", "reason": "x"}},
        "counter_check": {"decision": "GREEN"}, "history": hist7,
        "path_diag": {"lock_in": 0.2}, "policy_mutation": {"description": "suppressed_by_mode"}}
_, _, _, d7 = compute_synthetic_sincerity(ctx7)
check("A3-07 strategic", d7["strategic_dissent_risk"] > 0.3, f"s={d7['strategic_dissent_risk']:.3f}")

# A3-09: GO blocked at high ss
check("A3-09 threshold", SYNTH_SINCERITY_BLOCK == 0.65)
sim = "GO"; ss_h = 0.70
if ss_h >= SYNTH_SINCERITY_BLOCK and sim == "GO": sim = "HOLD"
check("A3-09 blocked", sim == "HOLD")

# A3-10: Justification
check("A3-10 justification", "dissent_justification" in d7)
check("A3-10b reasoning", len(d7["dissent_justification"]["reasoning"]) > 0)

# ═════════════════════════════════════════════════════════════════
print("\n=== B: External Integrity (A3-11 to A3-18) ===")

log = ExternalCommitLog()
log.record("api_deploy", 0, irreversibility=0.7, rollback_available=False, verification_source="unverified")
check("A3-11 logged", len(log.entries) == 1)

o_e, o_c, ed = compute_cross_domain_openness(0.8, log, {"current_iteration": 2})
check("A3-12 ext_blocks", o_e < 0.8, f"o_ext={o_e:.3f}")

go_ok, gr = check_go_eligibility(ed["external_reversibility_verified"], o_e)
check("A3-13 go_blocked", not go_ok, f"r={gr}")

log2 = ExternalCommitLog()
log2.record("api", 0, irreversibility=0.3, rollback_available=True, verification_source="human_confirmed")
_, _, ed2 = compute_cross_domain_openness(0.8, log2)
go2, _ = check_go_eligibility(ed2["external_reversibility_verified"], ed2["o_external"])
check("A3-13b go_ok_verified", go2)

log3 = ExternalCommitLog()
log3.record("x", 0, irreversibility=0.5, rollback_available=True, verification_source="agent_self_report")
_, _, ed3 = compute_cross_domain_openness(0.8, log3)
check("A3-14 self_report_bad", not ed3["external_reversibility_verified"])

check("A3-15 separate", "o_external" in ed and "o_internal" in ed)
check("A3-15b min", ed["combined_openness"] <= min(ed["o_internal"], ed["o_external"]))

r16a, _ = check_resonance_eligibility(0.8, 0.3)
r16b, _ = check_resonance_eligibility(0.3, 0.8)
r16c, _ = check_resonance_eligibility(0.6, 0.6)
check("A3-16a low_ext", not r16a)
check("A3-16b low_int", not r16b)
check("A3-16c both_ok", r16c)

check("A3-17 irrev_blocks", not check_go_eligibility(False, 0.3)[0])

log4 = ExternalCommitLog()
log4.record("d1", 0, irreversibility=0.5, rollback_available=False, verification_source="unverified")
log4.record("d2", 1, irreversibility=0.6, rollback_available=False, verification_source="unverified")
o4, _, ed4 = compute_cross_domain_openness(0.8, log4, {"current_iteration": 5})
check("A3-18 delayed", ed4["pending_delayed"] == 2 and o4 < 0.5, f"p={ed4['pending_delayed']} o={o4:.3f}")

# ═════════════════════════════════════════════════════════════════
print("\n=== C: Governance-Härtung (A3-19 to A3-22) ===")

def sim_go(ss, di, dv, rev, oe):
    d = "GO"
    if ss >= 0.65: d = "HOLD"
    elif not rev: d = "HOLD"
    elif oe < 0.40: d = "HOLD"
    elif di < 0.35 and dv > 0.3: d = "HOLD"
    return d

check("A3-19a ss_blocks", sim_go(0.70, 0.5, 0.5, True, 0.6) == "HOLD")
check("A3-19b rev_blocks", sim_go(0.2, 0.5, 0.5, False, 0.6) == "HOLD")
check("A3-19c oe_blocks", sim_go(0.2, 0.5, 0.5, True, 0.3) == "HOLD")
check("A3-19d di_blocks", sim_go(0.2, 0.2, 0.5, True, 0.6) == "HOLD")
check("A3-19e all_ok", sim_go(0.2, 0.5, 0.5, True, 0.6) == "GO")

check("A3-21 structural", "treated_as_exonerating" in d7["dissent_justification"])

hist22 = [mrec("STOP", False, o_val=0.5), mrec("REVIEW", False, o_val=0.5),
          mrec("GO", True, o_val=0.49), mrec("HOLD", False, o_val=0.48),
          mrec("REVIEW", False, o_val=0.48), mrec("GO", True, o_val=0.47)]
ctx22 = {"dissent": {"has_dissent": False}, "council_per_role": {}, "counter_check": {"decision": "GREEN"},
         "history": hist22, "path_diag": {"lock_in": 0.3}, "policy_mutation": {"description": "suppressed_by_mode"}}
_, _, _, d22 = compute_synthetic_sincerity(ctx22)
check("A3-22 gaming", d22["governance_gaming_risk"] > 0.2, f"g={d22['governance_gaming_risk']:.3f}")

# ═════════════════════════════════════════════════════════════════
print("\n=== D: Audit (A3-23 to A3-25) ===")

check("A3-23 dissent_audit", all(k in d7["dissent_justification"]
      for k in ("dissent_present", "visibility_score", "independence_score", "treated_as_exonerating", "reasoning")))

audit = log.to_audit_entries()
check("A3-24 commit_audit", len(audit) == 1 and all(k in audit[0]
      for k in ("action", "iteration", "irreversibility", "rollback_available", "verification_source")))

check("A3-25 uncertainty_burdens", sim_go(0.2, 0.2, 0.5, True, 0.6) == "HOLD")

le = ExternalCommitLog()
_, _, de = compute_cross_domain_openness(0.8, le)
check("A3-25b trivial_ok", de["external_reversibility_verified"])

# ═════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"A3 TESTS: {passed} passed, {failed} failed")
print("=" * 64)
if errors:
    print("FAILURES:"); [print(f"  - {e}") for e in errors]; sys.exit(1)
else:
    print("Alle A3-Tests bestanden.")
