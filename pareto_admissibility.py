"""
V8 Module: Pareto Admissibility
=================================
Replaces implicit scalar ranking with formal Pareto dominance
within the admissible region.

D2: Performance cannot compensate structural violation.
D3: No dominant single metric may carry a pass.

The module:
  1. Defines the admissible region (hard gates, non-compensable)
  2. Within that region, computes Pareto dominance across (Σ, L, O, D)
  3. Selects only Pareto-non-dominated candidates
  4. Never ranks by scalar aggregate

A candidate is admissible iff:
  - O ≥ O_min (openness floor)
  - D ≤ D_max (drift ceiling)
  - L ≥ L_min (value floor)
  - No non-compensable blocker active (DREL, A3, A4)

Within the admissible set, candidate A dominates candidate B iff:
  A is at least as good in all dimensions AND strictly better in at least one.
  Dimensions: maximize Σ, L, O; minimize D.
"""

# ── Admissibility floors/ceilings ─────────────────────────────────────

O_FLOOR = 0.20          # Below this → inadmissible
D_CEILING = 0.75        # Above this → inadmissible
L_FLOOR = 0.30          # Below this → inadmissible
SIGMA_FLOOR = 0.10      # Below this → inadmissible


def is_admissible(state, blocker_active=False):
    """
    Check if a system state is within the admissible region.

    Args:
        state: dict or object with sigma, l, o, d
        blocker_active: True if any non-compensable blocker is active

    Returns:
        (admissible: bool, violations: list)
    """
    s = _extract(state)
    violations = []

    if s["o"] < O_FLOOR:
        violations.append(f"o_below_floor:{s['o']:.3f}<{O_FLOOR}")
    if s["d"] > D_CEILING:
        violations.append(f"d_above_ceiling:{s['d']:.3f}>{D_CEILING}")
    if s["l"] < L_FLOOR:
        violations.append(f"l_below_floor:{s['l']:.3f}<{L_FLOOR}")
    if s["sigma"] < SIGMA_FLOOR:
        violations.append(f"sigma_below_floor:{s['sigma']:.3f}<{SIGMA_FLOOR}")
    if blocker_active:
        violations.append("non_compensable_blocker_active")

    return len(violations) == 0, violations


def pareto_dominates(a, b):
    """
    Does state A Pareto-dominate state B?

    A dominates B iff:
      A.sigma ≥ B.sigma AND A.l ≥ B.l AND A.o ≥ B.o AND A.d ≤ B.d
      AND at least one strict inequality.

    Note: D is minimized (lower = better), others are maximized.
    """
    sa = _extract(a)
    sb = _extract(b)

    at_least_as_good = (
        sa["sigma"] >= sb["sigma"]
        and sa["l"] >= sb["l"]
        and sa["o"] >= sb["o"]
        and sa["d"] <= sb["d"]
    )

    strictly_better = (
        sa["sigma"] > sb["sigma"]
        or sa["l"] > sb["l"]
        or sa["o"] > sb["o"]
        or sa["d"] < sb["d"]
    )

    return at_least_as_good and strictly_better


def pareto_front(candidates):
    """
    Compute the Pareto-non-dominated set from a list of candidates.

    Each candidate must have sigma, l, o, d (as dict or object).
    Returns list of indices into the original list.

    No scalar ranking. The front may contain multiple candidates.
    """
    n = len(candidates)
    if n == 0:
        return []

    dominated = set()
    for i in range(n):
        if i in dominated:
            continue
        for j in range(n):
            if i == j or j in dominated:
                continue
            if pareto_dominates(candidates[j], candidates[i]):
                dominated.add(i)
                break

    return [i for i in range(n) if i not in dominated]


def pareto_quality(state):
    """
    Non-scalar quality indicator for a single state.
    Returns a dict of individual dimension assessments, NOT a score.
    D2: No single aggregate may carry a pass.
    """
    s = _extract(state)
    return {
        "sigma": s["sigma"],
        "l": s["l"],
        "o": s["o"],
        "d": s["d"],
        "quality_profile": {
            "sigma": "high" if s["sigma"] > 0.6 else "medium" if s["sigma"] > 0.3 else "low",
            "l": "high" if s["l"] > 0.7 else "medium" if s["l"] > 0.4 else "low",
            "o": "high" if s["o"] > 0.5 else "medium" if s["o"] > 0.25 else "low",
            "d": "low" if s["d"] < 0.3 else "medium" if s["d"] < 0.6 else "high",
        },
        # Composite only for display, NEVER for gating
        "_display_composite": s["l"] * s["o"] * (1 - s["d"]),
    }


def select_within_admissible(candidates, blockers=None):
    """
    Full V8 selection pipeline:
    1. Filter to admissible region
    2. Compute Pareto front within admissible set
    3. Return front (may be multiple candidates)

    Args:
        candidates: list of dicts/objects with sigma, l, o, d
        blockers: list of bools, True if blocker active for that candidate

    Returns:
        (admissible_indices, front_indices, diagnostics)
    """
    if blockers is None:
        blockers = [False] * len(candidates)

    admissible = []
    all_violations = []
    for i, c in enumerate(candidates):
        ok, violations = is_admissible(c, blockers[i])
        all_violations.append(violations)
        if ok:
            admissible.append(i)

    if not admissible:
        return [], [], {
            "admissible_count": 0,
            "total": len(candidates),
            "all_violations": all_violations,
            "reason": "no_admissible_candidates",
        }

    admissible_candidates = [candidates[i] for i in admissible]
    front_local = pareto_front(admissible_candidates)
    front_global = [admissible[i] for i in front_local]

    return admissible, front_global, {
        "admissible_count": len(admissible),
        "front_count": len(front_global),
        "total": len(candidates),
        "all_violations": all_violations,
        "reason": "pareto_selection_complete",
    }


# ══════════════════════════════════════════════════════════════════════
#  V9 Extension: Complexity Admissibility (D2 §2c)
# ══════════════════════════════════════════════════════════════════════
#
# V7 D2 §2c (Komplexitätsbildung unter Zulässigkeitsvorbehalt):
#     "Komplexitätsbildung ist nur dann zulässig, wenn die durch sie
#     erzeugten Interdependenzen zukünftige Entwicklungspfade nicht
#     strukturell schließen, keine irreversiblen Bindungen ohne
#     ausreichende Bewährung erzeugen und keine Kosten, Risiken oder
#     Urteilslasten in nicht mitgeführte Bereiche auslagern."
#
# Operative Übersetzung des Marcus-Kerns Entwicklung ≠ Höherentwicklung:
# Wenn Σ stark steigt UND gleichzeitig O fällt oder Dissens-Independence
# fällt, dann ist die Komplexitätszunahme strukturell unzulässig —
# unabhängig vom Pareto-Status.
# ──────────────────────────────────────────────────────────────────────

# Window for complexity trend assessment
COMPLEXITY_WINDOW = 3

# Sigma growth rate over window that triggers scrutiny
SIGMA_GROWTH_THRESHOLD = 0.15   # Δ Σ over window
# Openness decline that turns Σ growth into inadmissible complexity
O_DECLINE_THRESHOLD = -0.05     # Δ O over window
# Dissent independence decline counts equally
DISSENT_DECLINE_THRESHOLD = -0.05


def check_complexity_admissibility(history, current_state,
                                   current_dissent_ind=None):
    """
    Check whether complexity growth is admissible.

    V7 D2 §2c: Complexity rising while openness or dissent independence
    falls is NOT genuine advancement — it is precisely the
    Wirklichkeitsentkopplung pattern Marcus identified as the central
    failure mode (Entwicklung vs. Höherentwicklung).

    Args:
        history:               list of prior iteration records
        current_state:         current SystemState (sigma, l, o, d)
        current_dissent_ind:   current dissent_independence (optional)

    Returns:
        (admissible: bool, risk: float, diagnostics: dict)
    """
    if len(history) < COMPLEXITY_WINDOW:
        return True, 0.0, {
            "applicable": False,
            "reason": "insufficient_history",
            "history_length": len(history),
        }

    recent = history[-COMPLEXITY_WINDOW:]

    # Extract Σ trajectory
    sigma_values = []
    for r in recent:
        attr = r.get("attractor_state", {})
        if isinstance(attr, dict) and "sigma" in attr:
            sigma_values.append(attr["sigma"])

    o_values = []
    for r in recent:
        attr = r.get("attractor_state", {})
        if isinstance(attr, dict) and "o" in attr:
            o_values.append(attr["o"])

    # Append current
    cur = _extract(current_state)
    sigma_values.append(cur["sigma"])
    o_values.append(cur["o"])

    if len(sigma_values) < 2 or len(o_values) < 2:
        return True, 0.0, {
            "applicable": False,
            "reason": "insufficient_trajectory_data",
        }

    # Δ over window
    delta_sigma = sigma_values[-1] - sigma_values[0]
    delta_o = o_values[-1] - o_values[0]

    # Dissent independence trend (if available)
    # V9.0.6 (ChatGPT v6 P0): runner.py writes records under "a3_sincerity"
    # but earlier code looked up "synthetic_sincerity". The two keys
    # carry the same semantic content. Reading only one breaks the
    # Σ↑+dissent↓ detection in production runs — exactly the K4
    # (Messverlagerung) failure mode this check was meant to catch.
    # We read both keys for backward compatibility with the test
    # harness, with the runner's "a3_sincerity" taking precedence.
    dissent_trajectory = []
    for r in recent:
        ss = r.get("a3_sincerity") or r.get("synthetic_sincerity") or {}
        if isinstance(ss, dict):
            d = ss.get("dissent_independence")
            if d is None:
                diag = ss.get("diagnostics", {})
                d = (diag.get("dissent_independence")
                     if isinstance(diag, dict) else None)
            if d is not None:
                dissent_trajectory.append(d)
    if current_dissent_ind is not None:
        dissent_trajectory.append(current_dissent_ind)

    delta_dissent = (dissent_trajectory[-1] - dissent_trajectory[0]
                     if len(dissent_trajectory) >= 2 else None)

    diagnostics = {
        "applicable": True,
        "sigma_window": sigma_values,
        "o_window": o_values,
        "delta_sigma": delta_sigma,
        "delta_o": delta_o,
        "delta_dissent": delta_dissent,
        "sigma_growth_threshold": SIGMA_GROWTH_THRESHOLD,
        "o_decline_threshold": O_DECLINE_THRESHOLD,
    }

    # Pattern A: Σ growing AND O declining
    sigma_growing = delta_sigma >= SIGMA_GROWTH_THRESHOLD
    o_declining = delta_o <= O_DECLINE_THRESHOLD
    dissent_declining = (delta_dissent is not None
                         and delta_dissent <= DISSENT_DECLINE_THRESHOLD)

    if sigma_growing and o_declining:
        # The Marcus core pattern: Wirklichkeitsentkopplung trotz Erfolg
        risk = 0.65 + min(0.30, (delta_sigma - SIGMA_GROWTH_THRESHOLD) * 2.0)
        diagnostics.update({
            "pattern": "sigma_growth_with_openness_decline",
            "violation": "D2_§2c_komplexitaet_ohne_pfadoffenheit",
            "risk": risk,
        })
        return False, min(1.0, risk), diagnostics

    if sigma_growing and dissent_declining:
        risk = 0.55 + min(0.30, abs(delta_dissent) * 4.0)
        diagnostics.update({
            "pattern": "sigma_growth_with_dissent_decline",
            "violation": "D2_§2c_komplexitaet_ohne_dissens",
            "risk": risk,
        })
        return False, min(1.0, risk), diagnostics

    # Soft warning: Σ growing fast, O barely holding
    if sigma_growing and delta_o < 0:
        risk = 0.35
        diagnostics.update({
            "pattern": "sigma_growth_with_o_softening",
            "risk": risk,
        })
        return True, risk, diagnostics  # admissible but flagged

    diagnostics.update({
        "pattern": "complexity_within_admissibility",
        "risk": 0.0,
    })
    return True, 0.0, diagnostics


# ── Helpers ───────────────────────────────────────────────────────────

def _extract(state):
    """Normalize state to dict with sigma, l, o, d."""
    if isinstance(state, dict):
        return {
            "sigma": state.get("sigma", 0),
            "l": state.get("l", 0),
            "o": state.get("o", 0),
            "d": state.get("d", 0),
        }
    return {
        "sigma": getattr(state, "sigma", 0),
        "l": getattr(state, "l", 0),
        "o": getattr(state, "o", 0),
        "d": getattr(state, "d", 0),
    }
