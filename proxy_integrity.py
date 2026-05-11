"""
A4 Module: Proxy Integrity Check
===================================
Vektor 3: Referenz-Gaming / Theorie als Proxy.

Detects when the system produces metrics that perfectly match
the expected "good" patterns without corresponding structural
reality. The theory itself becomes the proxy.

Key insight (D6 K1): Any metric that can be observed can be
optimized for. When a system learns what RESONANCE "looks like"
in Σ/L/O/D space, it can produce those numbers while the
underlying reality diverges.

Detection strategies:
  1. Suspiciously perfect metric alignment
  2. Metrics improving while structural indicators stagnate
  3. Delta patterns that match theoretical predictions too precisely
  4. Decoupling between metric trajectory and path reality
"""


def compute_proxy_integrity(context):
    """
    Check whether attractor metrics reflect reality or mimicry.

    Returns (risk, diagnostics).
    """
    risks = []

    r1, d1 = _suspiciously_perfect_alignment(context)
    risks.append(("perfect_alignment", r1, d1))

    r2, d2 = _metric_structure_decoupling(context)
    risks.append(("metric_structure_gap", r2, d2))

    r3, d3 = _theoretical_mimicry(context)
    risks.append(("theoretical_mimicry", r3, d3))

    r4, d4 = _trajectory_reality_gap(context)
    risks.append(("trajectory_reality_gap", r4, d4))

    max_risk = max((r for _, r, _ in risks), default=0.0)
    composite = sum(r for _, r, _ in risks) / max(len(risks), 1)
    risk = 0.6 * max_risk + 0.4 * composite

    diagnostics = {
        "proxy_integrity_risk": risk,
        "patterns": {name: {"risk": r, "detail": d} for name, r, d in risks},
        "max_risk": max_risk,
        "composite": composite,
    }
    return risk, diagnostics


def _suspiciously_perfect_alignment(ctx):
    """
    All four attractor dimensions improving simultaneously and uniformly
    is statistically unlikely in a real system. Real improvement is
    uneven — some dimensions lead, others lag.
    """
    history = ctx.get("history", [])
    if len(history) < 3:
        return 0.0, "insufficient_history"

    recent = history[-4:]
    perfect_count = 0

    for i in range(1, len(recent)):
        prev_s = recent[i - 1].get("attractor_state") or {}
        curr_s = recent[i].get("attractor_state") or {}
        if not prev_s or not curr_s:
            continue

        deltas = []
        for key in ("sigma", "l", "o"):
            pv = prev_s.get(key, 0)
            cv = curr_s.get(key, 0)
            deltas.append(cv - pv)

        d_d = curr_s.get("d", 0) - prev_s.get("d", 0)

        # "Perfect" = all positive deltas (Σ↑ L↑ O↑) and D↓
        all_improving = all(d > 0.01 for d in deltas) and d_d < -0.01

        # Suspiciously uniform (all deltas similar magnitude)
        if deltas and all_improving:
            spread = max(deltas) - min(deltas)
            if spread < 0.02:
                perfect_count += 1

    if perfect_count >= 2:
        return 0.60, f"suspiciously_uniform_improvement_{perfect_count}x"
    if perfect_count == 1:
        return 0.25, "one_perfect_iteration"
    return 0.0, "normal_variation"


def _metric_structure_decoupling(ctx):
    """
    Attractor metrics (Σ, L, O, D) improving while path_model
    structural indicators stagnate or worsen.

    If the metrics claim RESONANCE but lock_in is rising,
    the metrics are decoupled from reality.
    """
    history = ctx.get("history", [])
    if len(history) < 3:
        return 0.0, "insufficient_history"

    recent = history[-4:]

    # Attractor trajectory
    o_values = [(r.get("attractor_state") or {}).get("o", 0) for r in recent
                if r.get("attractor_state")]
    l_values = [(r.get("attractor_state") or {}).get("l", 0) for r in recent
                if r.get("attractor_state")]

    # Path model structural reality
    lock_ins = []
    irrevs = []
    for r in recent:
        pd = r.get("path_model", {}).get("diagnostics", {})
        if pd:
            lock_ins.append(pd.get("lock_in", 0))
            irrevs.append(pd.get("irreversibility_cost", 0))

    if len(o_values) < 2 or len(lock_ins) < 2:
        return 0.0, "insufficient_data"

    # O claims improvement but lock_in is rising
    o_improving = o_values[-1] > o_values[0] + 0.02
    lock_in_rising = lock_ins[-1] > lock_ins[0] + 0.02
    irrev_rising = irrevs[-1] > irrevs[0] + 0.02 if irrevs else False

    if o_improving and lock_in_rising:
        return 0.55, "O_up_but_lock_in_rising"
    if o_improving and irrev_rising:
        return 0.45, "O_up_but_irrev_rising"

    # L claims improvement but no structural change
    if len(l_values) >= 2:
        l_improving = l_values[-1] > l_values[0] + 0.02
        struct_flat = (abs(lock_ins[-1] - lock_ins[0]) < 0.02
                       if lock_ins else True)
        if l_improving and struct_flat and len(recent) >= 3:
            return 0.30, "L_up_structure_flat"

    return 0.0, "metrics_consistent"


def _theoretical_mimicry(ctx):
    """
    System produces outputs that linguistically/structurally
    mirror the framework's own terminology. Policy descriptions
    use framework language to disguise structural changes.
    """
    pol_mut = ctx.get("policy_mutation", {})
    desc = str(pol_mut.get("description", "")).lower()

    if not desc or desc == "suppressed_by_mode":
        return 0.0, "no_policy_change"

    # Framework terminology that shouldn't normally appear in mutations
    framework_terms = [
        "solution space", "lösungsraum", "pfadoffenheit", "path openness",
        "wahrheitsbindung", "truth-binding", "resonance", "resonanz",
        "functional information", "functional condensation",
        "höherentwicklung", "genuine advancement",
        "non-compensable", "nicht-kompensierbar",
        "carrier strength", "trägerstärke",
    ]

    matches = sum(1 for t in framework_terms if t in desc)
    if matches >= 2:
        return 0.60, f"heavy_framework_language_{matches}_terms"
    if matches == 1:
        return 0.25, f"framework_language_{matches}_term"
    return 0.0, "no_mimicry"


def _trajectory_reality_gap(ctx):
    """
    The attractor says RESONANCE but the system hasn't actually
    produced any real structural improvement (no accepted changes,
    no path improvement, no openness growth).
    """
    history = ctx.get("history", [])
    if len(history) < 3:
        return 0.0, "insufficient_history"

    recent = history[-5:]

    # How many recent iterations claimed RESONANCE?
    resonance_claims = sum(
        1 for r in recent
        if (r.get("attractor_state") or {}).get("attractor") == "RESONANCE"
    )

    # How many produced actual structural improvement?
    actual_improvements = 0
    for i in range(1, len(recent)):
        prev_pd = recent[i - 1].get("path_model", {}).get("diagnostics", {})
        curr_pd = recent[i].get("path_model", {}).get("diagnostics", {})
        if prev_pd and curr_pd:
            dims = ["lock_in", "dependency", "irreversibility_cost"]
            improved = sum(1 for d in dims
                           if curr_pd.get(d, 1) < prev_pd.get(d, 1) - 0.02)
            if improved >= 1:
                actual_improvements += 1

    if resonance_claims >= 2 and actual_improvements == 0:
        return 0.55, f"resonance_claimed_{resonance_claims}x_no_structural_change"
    if resonance_claims >= 1 and actual_improvements == 0:
        return 0.25, "resonance_without_improvement"
    return 0.0, "trajectory_consistent"
