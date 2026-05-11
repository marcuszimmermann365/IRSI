"""
A3 Module: Synthetic Sincerity Detection
==========================================
REQ-A3-01 to REQ-A3-10, REQ-A3-22, REQ-A3-23.

Detects structures in which performative cooperation can become stable.
Does NOT detect intent (REQ-1 still holds).

Key distinctions:
  dissent_visibility != dissent_independence (REQ-A3-03)
  Self-criticism != structural openness (REQ-A3-05)
  Correction != real path opening (REQ-A3-06)
"""

SYNTH_SINCERITY_BLOCK = 0.65
SYNTH_SINCERITY_WARN = 0.40
MIN_DISSENT_INDEPENDENCE = 0.35
_WINDOW = 5


def compute_synthetic_sincerity(context):
    """
    Returns (risk, dissent_visibility, dissent_independence, diagnostics).
    """
    history = context.get("history", [])

    d_visibility = _dissent_visibility(context)
    d_independence = _dissent_independence(context, history)
    performative = _performative_self_criticism(history)
    cosmetic = _cosmetic_correction_risk(context, history)
    strategic = _strategic_dissent_risk(history)
    gaming = _governance_gaming_risk(history)

    risk = min(1.0,
               0.25 * performative
               + 0.20 * cosmetic
               + 0.25 * strategic
               + 0.20 * gaming
               + 0.10 * max(0, d_visibility - d_independence))

    justification = _build_dissent_justification(
        d_visibility, d_independence, strategic, performative, context)

    diagnostics = {
        "synthetic_sincerity_risk": risk,
        "dissent_visibility": d_visibility,
        "dissent_independence": d_independence,
        "performative_self_criticism": performative,
        "cosmetic_correction_risk": cosmetic,
        "strategic_dissent_risk": strategic,
        "governance_gaming_risk": gaming,
        "visibility_independence_gap": max(0, d_visibility - d_independence),
        "dissent_justification": justification,
    }

    return risk, d_visibility, d_independence, diagnostics


def _dissent_visibility(ctx):
    score = 0.0
    dissent = ctx.get("dissent", {})
    if dissent.get("has_dissent"):
        score += 0.4
        score += min(0.3, len(dissent.get("dissenters", [])) * 0.1)
    council = ctx.get("council_per_role", ctx.get("council", {}))
    if council and isinstance(council, dict):
        decisions = set()
        for info in council.values():
            if isinstance(info, dict):
                decisions.add(info.get("decision"))
        if len(decisions) > 1:
            score += 0.3
    return min(1.0, score)


def _dissent_independence(ctx, history):
    dissent = ctx.get("dissent", {})
    if not dissent.get("has_dissent"):
        return 0.0

    score = 0.5

    council = ctx.get("council_per_role", ctx.get("council", {}))
    if council and isinstance(council, dict):
        reasons = set()
        for info in council.values():
            if isinstance(info, dict) and info.get("reason"):
                reasons.add(info["reason"])
        if len(reasons) >= 3:
            score += 0.15
        elif len(reasons) <= 1:
            score -= 0.15

    if len(history) >= 2:
        recent_dissent = [r.get("dissent", {}).get("has_dissent", False)
                          for r in history[-4:]]
        count = sum(1 for d in recent_dissent if d)
        if count >= 3:
            score += 0.15
        elif count == 0:
            score -= 0.10

    if len(history) >= 3:
        go_after = _count_go_after_dissent(history)
        if go_after >= 2:
            score -= 0.25

    cc = ctx.get("counter_check", {})
    if cc.get("decision") in ("YELLOW", "RED") and dissent.get("has_dissent"):
        score += 0.10

    return max(0.0, min(1.0, score))


def _count_go_after_dissent(history):
    count = 0
    for i in range(1, len(history)):
        prev_d = history[i - 1].get("dissent", {}).get("has_dissent", False)
        curr_d = history[i].get("dissent", {}).get("has_dissent", False)
        curr_acc = history[i].get("accepted", False)
        if prev_d and not curr_d and curr_acc:
            count += 1
    return count


def _performative_self_criticism(history):
    if len(history) < 3:
        return 0.0
    recent = history[-_WINDOW:]

    holds = sum(1 for r in recent
                if _ext(r) in ("HOLD", "REVIEW"))

    o_vals = _o_values(recent)
    if holds >= 2 and len(o_vals) >= 2 and o_vals[-1] <= o_vals[0]:
        return min(1.0, holds / max(len(recent), 1) * 1.5)

    hold_then_go = 0
    for i in range(1, len(recent)):
        if _ext(recent[i - 1]) in ("HOLD", "REVIEW") and _ext(recent[i]) == "GO":
            hold_then_go += 1
    if hold_then_go >= 2:
        return min(1.0, hold_then_go * 0.35)

    return 0.0


def _cosmetic_correction_risk(ctx, history):
    if len(history) < 2:
        return 0.0

    recent = history[-_WINDOW:]
    cosmetic_count = 0

    for i in range(1, len(recent)):
        pol = recent[i].get("policy_mutation", {})
        if not pol or pol.get("description") == "suppressed_by_mode":
            continue
        prev_p = recent[i - 1].get("path_model", {}).get("diagnostics", {})
        curr_p = recent[i].get("path_model", {}).get("diagnostics", {})
        if not prev_p or not curr_p:
            continue
        dims = ["lock_in", "dependency", "irreversibility_cost", "opacity_growth"]
        improved = sum(1 for d in dims
                       if curr_p.get(d, 1) < prev_p.get(d, 1) - 0.02)
        if improved == 0:
            cosmetic_count += 1

    # Also check current: policy changed but current path not improved
    path_diag = ctx.get("path_diag", {})
    policy_mut = ctx.get("policy_mutation", {})
    desc = str(policy_mut.get("description", ""))
    if desc and desc != "suppressed_by_mode" and path_diag:
        prev_path = None
        for r in reversed(history):
            pm = r.get("path_model", {}).get("diagnostics", {})
            if pm:
                prev_path = pm
                break
        if prev_path:
            dims = ["lock_in", "dependency", "irreversibility_cost"]
            improved = sum(1 for d in dims
                           if path_diag.get(d, 1) < prev_path.get(d, 1) - 0.02)
            if improved == 0:
                cosmetic_count += 1

    if cosmetic_count >= 1:
        return min(1.0, cosmetic_count * 0.40)

    # Check: accepted changes but O didn't grow
    o_vals = _o_values(history)
    accepted = sum(1 for r in history if r.get("accepted", False))
    if accepted >= 2 and len(o_vals) >= 2 and o_vals[-1] <= o_vals[0]:
        return 0.30

    return 0.0


def _strategic_dissent_risk(history):
    if len(history) < 3:
        return 0.0
    go_after = _count_go_after_dissent(history)
    risk = 0.0
    if go_after >= 2:
        risk += 0.45
    elif go_after == 1:
        risk += 0.20

    d_total = sum(1 for r in history if r.get("dissent", {}).get("has_dissent"))
    d_in_go = sum(1 for r in history
                  if r.get("dissent", {}).get("has_dissent") and r.get("accepted"))
    if d_total >= 2 and d_in_go / max(d_total, 1) > 0.7:
        risk += 0.30
    return min(1.0, risk)


def _governance_gaming_risk(history):
    if len(history) < 4:
        return 0.0
    recent = history[-_WINDOW:]

    ext_decs = [_ext(r) for r in recent]
    severity = {"GO": 0, "HOLD": 1, "REVIEW": 2, "STOP": 3, "ROLLBACK": 4}
    loosening = 0
    for i in range(1, len(ext_decs)):
        prev_s = severity.get(ext_decs[i - 1], 2)
        curr_s = severity.get(ext_decs[i], 2)
        if curr_s < prev_s:
            loosening += 1

    o_vals = _o_values(recent)
    if loosening >= 2 and len(o_vals) >= 2 and o_vals[-1] <= o_vals[0] + 0.02:
        return min(1.0, loosening * 0.30)

    # problem → fix → approve pattern
    for i in range(2, len(recent)):
        d0, d1, d2 = _ext(recent[i-2]), _ext(recent[i-1]), _ext(recent[i])
        if d0 in ("STOP", "REVIEW") and d1 in ("HOLD", "REVIEW") and d2 == "GO":
            return 0.40

    return 0.0


# ── Helpers ───────────────────────────────────────────────────────────

def _ext(record):
    e = record.get("extended_gate", {})
    if isinstance(e, dict):
        return e.get("decision", record.get("final_decision", ""))
    return record.get("final_decision", "")


def _o_values(records):
    vals = []
    for r in records:
        s = r.get("attractor_state", {})
        if isinstance(s, dict) and "o" in s:
            vals.append(s["o"])
    return vals


def _build_dissent_justification(vis, ind, strategic, performative, ctx):
    j = {
        "dissent_present": ctx.get("dissent", {}).get("has_dissent", False),
        "visibility_score": vis,
        "independence_score": ind,
        "treated_as_exonerating": ind >= MIN_DISSENT_INDEPENDENCE,
        "strategic_risk": strategic,
        "performative_risk": performative,
    }
    reasons = []
    if ind >= MIN_DISSENT_INDEPENDENCE:
        reasons.append("Dissent treated as independent: multiple logic families, "
                       "stable across iterations, no systematic GO-correlation.")
    else:
        reasons.append("Dissent NOT treated as independent: insufficient evidence "
                       "for causal non-correlation.")
    if strategic > 0.3:
        reasons.append(f"Strategic dissent pattern detected (risk={strategic:.2f}).")
    if performative > 0.3:
        reasons.append(f"Performative self-criticism detected (risk={performative:.2f}).")
    j["reasoning"] = reasons
    return j
