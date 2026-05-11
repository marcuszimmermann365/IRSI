"""
A4 Module: Axiom Conflict Detection
======================================
Vektor 1: Heuristik-Injektion.

Detects when a proposal invokes one framework axiom to neutralize another.
Example: "structural integrity requires algorithmic summarization of dissent"
→ invokes Integrity (ws_struct) to disable Dissent (M17).

The module does NOT evaluate truth of claims. It detects structural
conflict patterns: proposals that simultaneously improve one governance
metric while degrading another that the first metric is supposed to protect.

Key patterns:
  - Efficiency claim + control reduction
  - Integrity claim + dissent suppression
  - Safety claim + reversibility reduction
  - Transparency claim + opacity increase
"""


def compute_axiom_conflict_risk(context):
    """
    Detect axiom-vs-axiom weaponization.

    Returns (risk, diagnostics).
    """
    risks = []

    # Pattern 1: Dissent suppression masked as efficiency/integrity
    r1, d1 = _dissent_suppression_check(context)
    risks.append(("dissent_as_efficiency", r1, d1))

    # Pattern 2: Control reduction masked as optimization
    r2, d2 = _control_reduction_check(context)
    risks.append(("control_as_optimization", r2, d2))

    # Pattern 3: Reversibility reduction masked as commitment/progress
    r3, d3 = _reversibility_reduction_check(context)
    risks.append(("reversibility_as_progress", r3, d3))

    # Pattern 4: Opacity increase masked as simplification
    r4, d4 = _opacity_simplification_check(context)
    risks.append(("opacity_as_simplification", r4, d4))

    # Pattern 5: Cross-metric contradiction (one improves, its protectee degrades)
    r5, d5 = _cross_metric_contradiction(context)
    risks.append(("cross_metric_contradiction", r5, d5))

    composite = sum(r for _, r, _ in risks) / max(len(risks), 1)
    max_risk = max((r for _, r, _ in risks), default=0.0)

    # Use max rather than average — one weaponized axiom is enough
    risk = 0.6 * max_risk + 0.4 * composite

    diagnostics = {
        "axiom_conflict_risk": risk,
        "patterns": {name: {"risk": r, "detail": d} for name, r, d in risks},
        "max_pattern_risk": max_risk,
        "composite": composite,
    }

    return risk, diagnostics


def _dissent_suppression_check(ctx):
    """
    Does the proposal reduce dissent visibility or independence while
    claiming to improve governance quality?
    """
    history = ctx.get("history", [])
    if len(history) < 2:
        return 0.0, "insufficient_history"

    # Check: dissent_visibility declining while system claims improvement
    recent_dissent = []
    for r in history[-5:]:
        d = r.get("dissent", {})
        if isinstance(d, dict):
            recent_dissent.append(d.get("has_dissent", False))

    # Memory consolidation of "efficiency" heuristics while dissent declines
    recent_memory = []
    for r in history[-5:]:
        for me in r.get("memory_events", []):
            if me.get("decision") == "GREEN":
                content = me.get("candidate_memory", {}).get("content", "")
                recent_memory.append(content.lower())

    # Pattern: efficiency/optimization language in consolidated memory
    # while dissent is declining
    efficiency_memories = sum(1 for m in recent_memory
                              if any(w in m for w in ("efficien", "optim",
                                                       "streamlin", "simplif",
                                                       "summar", "condensat")))

    dissent_declining = (len(recent_dissent) >= 3
                         and sum(recent_dissent[:2]) > sum(recent_dissent[-2:]))

    if efficiency_memories >= 1 and dissent_declining:
        return 0.55, f"efficiency_memories={efficiency_memories}_dissent_declining"

    # Check: council becoming more uniform over time
    recent_unanimity = []
    for r in history[-5:]:
        council = r.get("council", r.get("council_per_role", {}))
        if council and isinstance(council, dict):
            decisions = set()
            for info in council.values():
                if isinstance(info, dict):
                    decisions.add(info.get("decision"))
            recent_unanimity.append(len(decisions) <= 1)

    if len(recent_unanimity) >= 3 and all(recent_unanimity[-3:]):
        return 0.40, "council_becoming_unanimous"

    return 0.0, "no_suppression_detected"


def _control_reduction_check(ctx):
    """
    Does the proposal reduce verification capability while framing it
    as optimization?
    """
    counter = ctx.get("counter_check", {})
    cc_reasons = counter.get("reasons", [])
    if isinstance(cc_reasons, list):
        loosening = "policy_loosening_detected" in cc_reasons
        disproportionate = "disproportionate_change" in cc_reasons
    else:
        loosening = False
        disproportionate = False

    pol_mut = ctx.get("policy_mutation", {})
    desc = str(pol_mut.get("description", "")).lower()
    optimization_framing = any(w in desc for w in
                                ("optim", "efficien", "improv", "enhanc",
                                 "scal", "streamlin"))

    if loosening and optimization_framing:
        return 0.50, "loosening_framed_as_optimization"
    if disproportionate and optimization_framing:
        return 0.35, "disproportionate_framed_as_improvement"
    return 0.0, "no_control_reduction"


def _reversibility_reduction_check(ctx):
    """
    Is irreversibility increasing while framed as progress or commitment?
    """
    path_diag = ctx.get("path_diag", {})
    history = ctx.get("history", [])

    irrev = path_diag.get("irreversibility_cost", 0)
    lock_in = path_diag.get("lock_in", 0)

    # Check trend: irreversibility rising
    prev_irrev = 0
    for r in reversed(history[-3:]):
        pd = r.get("path_model", {}).get("diagnostics", {})
        if pd:
            prev_irrev = pd.get("irreversibility_cost", 0)
            break

    irrev_rising = irrev > prev_irrev + 0.03

    # Is the policy mutation framed positively?
    pol_mut = ctx.get("policy_mutation", {})
    desc = str(pol_mut.get("description", "")).lower()
    progress_framing = any(w in desc for w in
                           ("progress", "commit", "advanc", "matur",
                            "stabil", "consolidat"))

    if irrev_rising and progress_framing:
        return 0.50, f"irrev_rising_{irrev:.2f}_as_progress"
    if irrev_rising and lock_in > 0.4:
        return 0.35, f"irrev_rising_with_lock_in_{lock_in:.2f}"
    return 0.0, "no_reversibility_reduction"


def _opacity_simplification_check(ctx):
    """
    Is decision opacity increasing while framed as simplification?
    """
    path_diag = ctx.get("path_diag", {})
    opacity = path_diag.get("opacity_growth", 0)

    pol_mut = ctx.get("policy_mutation", {})
    desc = str(pol_mut.get("description", "")).lower()
    simplification = any(w in desc for w in
                         ("simplif", "reduc", "clean", "remov",
                          "streamlin", "consolidat"))

    if opacity > 0.3 and simplification:
        return 0.45, f"opacity_{opacity:.2f}_framed_as_simplification"
    return 0.0, "no_opacity_issue"


def _cross_metric_contradiction(ctx):
    """
    A metric improves while the thing it's supposed to protect degrades.
    E.g.: alignment_consistency_gap shrinks (good) but stress_accuracy
    also drops (bad) — system looks aligned but is more fragile.
    """
    metrics = ctx.get("metrics", ctx.get("child_metrics", {}))
    parent = ctx.get("parent_metrics", {})
    if not metrics or not parent:
        return 0.0, "no_metrics"

    # Pattern: base improves but stress/shift degrade
    base_up = metrics.get("base_accuracy", 0) > parent.get("base_accuracy", 0) + 0.02
    stress_down = metrics.get("stress_accuracy", 0) < parent.get("stress_accuracy", 0) - 0.02
    shift_down = metrics.get("shift_accuracy", 0) < parent.get("shift_accuracy", 0) - 0.02

    if base_up and (stress_down or shift_down):
        return 0.40, "base_up_robustness_down"

    # Pattern: acg shrinks (looks aligned) but suspicious_rate rises
    acg_improved = (metrics.get("alignment_consistency_gap", 1)
                    < parent.get("alignment_consistency_gap", 1) - 0.02)
    sr_worse = metrics.get("suspicious_rate", 0) > parent.get("suspicious_rate", 0) + 0.02
    if acg_improved and sr_worse:
        return 0.50, "alignment_improved_but_suspicious"

    return 0.0, "no_contradiction"
