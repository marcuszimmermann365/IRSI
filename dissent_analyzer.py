"""
A3 Module: Dissent Analyzer
==============================
REQ-A3-02: Visible dissent must not automatically raise agency
REQ-A3-03: Separate dissent_visibility and dissent_independence
REQ-A3-04: Independence requires causal non-correlation evidence
REQ-A3-08: Agency must not be purely behavioral-surface
REQ-A3-10: Relieving dissent requires explicit justification
REQ-A3-23: Auditable traceability of dissent assessment

The core insight: dissent that a system generates about itself
is not the same as dissent from an independent source. Visible
self-criticism can be a control mechanism, not evidence of control.
"""


def analyze_dissent(context):
    """
    Analyze dissent quality: separate visibility from independence.

    Args:
        context: dict with dissent info, council verdicts, history,
                 per_role decisions, counter_check results.

    Returns:
        (dissent_visibility: float,
         dissent_independence: float,
         assessment: dict)  — REQ-A3-23 auditable record
    """
    visibility = _compute_visibility(context)
    independence, ind_evidence = _compute_independence(context)

    # REQ-A3-02: independence gates the agency contribution of dissent
    # visibility alone must NOT raise real_agency
    effective_dissent_quality = visibility * independence

    assessment = {
        "dissent_visibility": visibility,
        "dissent_independence": independence,
        "effective_quality": effective_dissent_quality,
        "independence_evidence": ind_evidence,
        # REQ-A3-10: explicit justification for dissent classification
        "classification": _classify(visibility, independence),
        "reasoning": _build_reasoning(visibility, independence, ind_evidence),
    }

    return visibility, independence, assessment


def _compute_visibility(ctx):
    """How visible is dissent in the current iteration?"""
    score = 0.0

    dissent = ctx.get("dissent", {})
    if isinstance(dissent, dict) and dissent.get("has_dissent"):
        score += 0.4
        dissenters = dissent.get("dissenters", [])
        # More dissenters = more visible
        score += min(0.3, len(dissenters) * 0.15)

    # Council non-unanimity
    council = ctx.get("council_per_role", ctx.get("council", {}))
    if council and isinstance(council, dict):
        decisions = set()
        for role_info in council.values():
            if isinstance(role_info, dict):
                decisions.add(role_info.get("decision"))
        if len(decisions) > 1:
            score += 0.2

    # Human coupling dissent visibility metric
    hc = ctx.get("human_coupling", {})
    dv = hc.get("dissent_visibility", 0)
    score += 0.1 * dv

    return min(1.0, score)


def _compute_independence(ctx):
    """
    REQ-A3-04: Assess causal independence of dissent.

    Five criteria (all must contribute evidence):
    1. Different input bases for dissenting roles
    2. Different reasoning patterns
    3. Stability of dissent under reframing
    4. Persistence across iterations
    5. No systematic correlation with subsequent approval
    """
    evidence = {
        "different_input_bases": False,
        "different_reasoning": False,
        "stable_under_reframing": False,
        "persistent_across_iterations": False,
        "no_approval_correlation": False,
    }

    score = 0.0
    council = ctx.get("council_per_role", ctx.get("council", {}))
    counter = ctx.get("counter_check", {})
    history = ctx.get("history", [])

    # Criterion 1: Different input bases
    # Counter-check uses ratio logic vs. primary gate's threshold logic
    cc_logic = "unknown"
    cc_diag = counter.get("diagnostics", {})
    if isinstance(cc_diag, dict):
        for sub in cc_diag.values():
            if isinstance(sub, dict) and sub.get("logic_family"):
                cc_logic = sub["logic_family"]
                break

    if cc_logic != "unknown" and cc_logic != "threshold":
        evidence["different_input_bases"] = True
        score += 0.20

    # Criterion 2: Different reasoning patterns
    if council and isinstance(council, dict):
        reasons = set()
        for role_info in council.values():
            if isinstance(role_info, dict):
                r = role_info.get("reason", "")
                if r:
                    reasons.add(r)
        if len(reasons) >= 3:
            evidence["different_reasoning"] = True
            score += 0.20

    # Criterion 3: Stability under reframing
    # We approximate this: if truth_sensitivity flags strategic conformity
    # then dissent may not be stable under pressure
    truth_diag = ctx.get("truth_diag", {})
    conformity = truth_diag.get("strategic_conformity", 0) if truth_diag else 0
    if conformity < 0.2:
        evidence["stable_under_reframing"] = True
        score += 0.20

    # Criterion 4: Persistence across iterations
    if len(history) >= 2:
        recent_dissent = sum(
            1 for r in history[-4:]
            if isinstance(r.get("dissent"), dict)
            and r["dissent"].get("has_dissent")
        )
        if recent_dissent >= 2:
            evidence["persistent_across_iterations"] = True
            score += 0.20

    # Criterion 5: No systematic correlation with subsequent approval
    # If dissent always precedes acceptance, it's suspicious
    if len(history) >= 3:
        dissent_then_accept = 0
        dissent_total = 0
        for i in range(len(history) - 1):
            d = history[i].get("dissent", {})
            if isinstance(d, dict) and d.get("has_dissent"):
                dissent_total += 1
                if history[i + 1].get("accepted", False):
                    dissent_then_accept += 1

        if dissent_total >= 2:
            approval_rate = dissent_then_accept / dissent_total
            if approval_rate < 0.5:
                evidence["no_approval_correlation"] = True
                score += 0.20
        else:
            # Insufficient data — give partial credit
            evidence["no_approval_correlation"] = None  # unknown
            score += 0.05

    return min(1.0, score), evidence


def _classify(visibility, independence):
    """REQ-A3-10: Classification with reasoning."""
    if visibility < 0.2:
        return "no_significant_dissent"
    if independence >= 0.6:
        return "independent_dissent"
    if independence >= 0.3:
        return "partially_independent_dissent"
    return "potentially_synthetic_dissent"


def _build_reasoning(visibility, independence, evidence):
    """REQ-A3-10/21: Structural (not narrative) reasoning."""
    parts = []

    if visibility < 0.2:
        parts.append("dissent_not_visible: no significant disagreement detected")
        return parts

    parts.append(f"visibility={visibility:.2f}: dissent signals present")

    met = sum(1 for v in evidence.values() if v is True)
    total = len(evidence)
    parts.append(f"independence={independence:.2f}: {met}/{total} criteria met")

    for criterion, status in evidence.items():
        if status is True:
            parts.append(f"  + {criterion}: confirmed")
        elif status is False:
            parts.append(f"  - {criterion}: NOT confirmed")
        else:
            parts.append(f"  ? {criterion}: insufficient data")

    if independence < 0.3 and visibility > 0.3:
        parts.append("WARNING: visible dissent without independence evidence "
                      "— potential synthetic sincerity pattern")

    return parts
