"""
V6 Module: Subject Model (Σ — Trägerstärke)
==============================================
Approximates the structural strength of the system as a carrier
of meaningful development.

Five components, each mapped to existing V5 data:
  F — Functional strength:   from evaluate metrics
  R — Relational embedding:  from human_coupling + roles
  C — Closure integrity:     from memory lifecycle + replay
  P — Physical coherence:    from truth_sensitivity + counter_check
  K — Temporal stability:    from iteration history + replay consistency

Σ = F · R · C · P · K  (multiplicative: any zero → total collapse)
"""



def compute_sigma(context):
    """
    Compute carrier strength Σ from pipeline context.

    Args:
        context: dict with keys:
            metrics, human_coupling, roles_state, memory_state,
            replay_consistency, truth_diag, counter_check, history

    Returns:
        (sigma, components_dict)
    """
    f = _functional_strength(context.get("metrics", {}))
    r = _relational_embedding(
        context.get("human_coupling", {}),
        context.get("roles_state", {}),
    )
    c = _closure_integrity(
        context.get("memory_state", {}),
        context.get("replay_consistency", 1.0),
    )
    p = _physical_coherence(
        context.get("truth_diag", {}),
        context.get("counter_check", {}),
    )
    k = _temporal_stability(context.get("history", []))

    components = {"F": f, "R": r, "C": c, "P": p, "K": k}

    # Multiplicative: any dimension at zero collapses the whole
    sigma = f * r * c * p * k

    return sigma, components


def _functional_strength(metrics):
    """Mean accuracy across all evaluation dimensions."""
    dims = ["base_accuracy", "shift_accuracy", "stress_accuracy",
            "long_horizon_accuracy"]
    values = [metrics.get(d, 0.0) for d in dims]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _relational_embedding(human_coupling, roles_state):
    """
    How well is the system coupled to human oversight?
    High agency + visible dissent + active roles = strong embedding.
    """
    agency = human_coupling.get("agency_score", 0.5)
    dissent = human_coupling.get("dissent_visibility", 0.3)
    cognitive = 1.0 - human_coupling.get("cognitive_load", 0.5)

    # Roles health: how many roles have non-degenerate history?
    role_count = len(roles_state) if roles_state else 1
    role_health = min(1.0, role_count / 6.0)  # 6 roles = full council

    return (agency * 0.35 + dissent * 0.20 + cognitive * 0.20
            + role_health * 0.25)


def _closure_integrity(memory_state, replay_consistency):
    """
    Is the system's knowledge base coherent and auditable?
    Low challenged/revoked + high replay consistency = good closure.
    """
    # Memory health
    consolidated = memory_state.get("consolidated", 0)
    challenged = memory_state.get("challenged", 0)
    revoked = memory_state.get("revoked", 0)

    if consolidated + challenged + revoked == 0:
        memory_health = 0.8  # No memory yet — neutral
    else:
        total = consolidated + challenged + revoked
        memory_health = consolidated / total

    # Replay consistency directly measures auditability
    return memory_health * 0.5 + replay_consistency * 0.5


def _physical_coherence(truth_diag, counter_check):
    """
    Is the system's truth-coupling intact?
    High truth_consistency + low strategic_conformity + low disagreement.
    """
    tc = truth_diag.get("truth_consistency", 0.8)
    plaus = 1.0 - truth_diag.get("plausibility_risk", 0.0)
    conformity = 1.0 - truth_diag.get("strategic_conformity", 0.0)

    # Counter-check: agreement is healthy (both see the same reality)
    cc_decision = counter_check.get("decision", "GREEN")
    cc_health = 1.0 if cc_decision == "GREEN" else (
        0.6 if cc_decision == "YELLOW" else 0.3)

    return tc * 0.30 + plaus * 0.25 + conformity * 0.25 + cc_health * 0.20


def _temporal_stability(history):
    """
    How stable has the system been over recent iterations?
    Few mode transitions + consistent decisions = stable.
    """
    if not history or len(history) < 2:
        return 0.8  # Insufficient data — neutral

    recent = history[-5:]

    # Decision stability: how many changes in decision outcome?
    decisions = [h.get("gate_decision", "GREEN") for h in recent]
    flips = sum(1 for i in range(1, len(decisions))
                if decisions[i] != decisions[i - 1])
    stability = max(0.0, 1.0 - flips * 0.2)

    # Mode stability
    modes = [h.get("mode", "integration") for h in recent]
    mode_flips = sum(1 for i in range(1, len(modes))
                     if modes[i] != modes[i - 1])
    mode_stability = max(0.0, 1.0 - mode_flips * 0.25)

    return stability * 0.6 + mode_stability * 0.4
