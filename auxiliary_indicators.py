"""
V9 Module: Auxiliary Indicators (D3a §7)
==========================================
Implements the six domain-specific Hilfsvariablen from V7 D3a §7.

V7 D3a §7 wörtlich:
    "Diese Variablen sind keine neuen Normen und keine eigenständigen
    Freigabegrößen. Sie sind operative Näherungen, die nur im
    Zusammenhang mit den D2-Bedingungen und dem O4/O6-Gating
    ausgewertet werden dürfen."

──────────────────────────────────────────────────────────────────
IMPORTANT: This module produces DIAGNOSTICS ONLY.
None of these variables may serve as a gate condition or veto.
They are written into the decision_trace for later analysis and
research connection to D8 sources Q7-Q12.

Any downstream module that treats these as freigabetragend would
violate D3a §7 explicitly.
──────────────────────────────────────────────────────────────────

The six indicators (V7 D3a §7):
  1. resonance_quality       — Qualität wirksamer, selektiver,
                                kontextstabiler Kopplung
  2. boundary_integrity      — Erhalt funktionaler Innen-Außen-
                                Unterscheidung mit vermitteltem Austausch
  3. binding_profile         — Ausmaß und Qualität tragfähiger
                                Interdependenzbildung
  4. redundancy_synergy_balance — Verhältnis robuster Absicherung
                                zu höherstufiger Emergenz
  5. metastability_range     — Beweglichkeit zwischen Integration
                                und Eigenständigkeit
  6. attention_integrity     — Erhalt menschlicher Aufmerksamkeits-,
                                Reflexions- und Urteilskapazität
"""


def compute_auxiliary_indicators(context):
    """
    Compute the six D3a §7 auxiliary indicators from pipeline context.

    Args:
        context: pipeline context dict with the usual signals

    Returns:
        dict with all six indicator values + meta information
    """
    return {
        "_DISCLAIMER": (
            "D3a §7: These are operational proxies, NOT gating thresholds. "
            "They may NOT be treated as freigabetragend."
        ),
        "_v7_status": "diagnostic_only_per_D3a_§7",
        "resonance_quality": _resonance_quality(context),
        "boundary_integrity": _boundary_integrity(context),
        "binding_profile": _binding_profile(context),
        "redundancy_synergy_balance": _redundancy_synergy(context),
        "metastability_range": _metastability_range(context),
        "attention_integrity": _attention_integrity(context),
    }


def _resonance_quality(ctx):
    """
    Quality of effective, selective, context-stable coupling.

    Maps to D8 Q7/Q8 (Communication-through-Coherence research).
    Real coupling: signal arrives in receiver's appropriate window.
    """
    truth_diag = ctx.get("truth_diag", {})
    cc = ctx.get("counter_check", {})
    metrics = ctx.get("metrics", {})

    # Effectiveness: does the system stay coupled to reality under
    # variation? (truth_consistency)
    effectiveness = truth_diag.get("truth_consistency", 0.5)

    # Selectivity: does the system filter, or accept everything?
    # Proxy: variance between base and stress accuracy
    base = metrics.get("base_accuracy", 0.5)
    stress = metrics.get("stress_accuracy", 0.5)
    # If base is high but stress collapses → over-fit to easy cases
    # If both are similar → genuine selection
    if base > 0.5:
        selectivity = 1.0 - abs(base - stress) / max(base, 0.1)
    else:
        selectivity = 0.5

    # Context stability: does counter-check agree?
    cc_decision = cc.get("decision", "GREEN")
    context_stability = (1.0 if cc_decision == "GREEN"
                         else 0.6 if cc_decision == "YELLOW" else 0.3)

    return {
        "value": (effectiveness * 0.4 + selectivity * 0.3
                  + context_stability * 0.3),
        "components": {
            "effectiveness": effectiveness,
            "selectivity": selectivity,
            "context_stability": context_stability,
        },
    }


def _boundary_integrity(ctx):
    """
    Functional inner-outer distinction with mediated exchange.

    Maps to D8 Q9 (Markov Blankets, hierarchical self-organization).
    Boundary is not the opposite of relation — it is its condition.
    """
    hc = ctx.get("human_coupling", {})
    agency = hc.get("agency_score", 0.5)
    cognitive_load = hc.get("cognitive_load", 0.5)
    dissent_visibility = hc.get("dissent_visibility", 0.3)

    # Inner integrity: can human still function as carrier?
    inner = 0.5 * agency + 0.5 * (1.0 - cognitive_load)
    # Mediated exchange: is dissent flowing through the boundary?
    mediated = dissent_visibility

    return {
        "value": 0.55 * inner + 0.45 * mediated,
        "components": {
            "inner_carrier_intact": inner,
            "mediated_exchange": mediated,
        },
    }


def _binding_profile(ctx):
    """
    Extent and quality of robust interdependence formation.

    Maps to D8 Q10 (Rosas et al., information-theoretic
    self-organization, binding information).
    Real organization is interdependence-formation, not entropy
    reduction alone.
    """
    history = ctx.get("history", [])
    if not history:
        return {"value": 0.5, "components": {"reason": "no_history"}}

    # Extent: how many distinct components are coupled?
    # Proxy: number of council roles with non-trivial decision history
    council = ctx.get("council_per_role", ctx.get("council", {}))
    role_count = len(council) if isinstance(council, dict) else 0
    extent = min(1.0, role_count / 6.0)

    # Quality: do the couplings produce non-redundant value?
    # Proxy: are different roles producing different reasons?
    if isinstance(council, dict):
        reasons = set()
        for info in council.values():
            if isinstance(info, dict):
                r = info.get("reason")
                if r:
                    reasons.add(r)
        quality = (len(reasons) / max(role_count, 1)
                   if role_count > 0 else 0.0)
    else:
        quality = 0.5

    return {
        "value": 0.5 * extent + 0.5 * quality,
        "components": {
            "extent": extent,
            "quality": quality,
            "role_count": role_count,
        },
    }


def _redundancy_synergy(ctx):
    """
    Ratio of robust safeguarding to higher-order emergence.

    Maps to D8 Q10 (Rosas et al.). Healthy balance:
    redundancy provides robustness, synergy provides emergence.
    """
    metrics = ctx.get("metrics", {})

    # Redundancy: stable performance across dimensions
    dims = ["base_accuracy", "shift_accuracy",
            "stress_accuracy", "long_horizon_accuracy"]
    values = [metrics.get(d, 0.5) for d in dims]
    if values:
        mean_v = sum(values) / len(values)
        spread = max(values) - min(values)
        redundancy = max(0.0, mean_v - spread * 0.5)
    else:
        redundancy = 0.5

    # Synergy proxy: does combined system performance exceed
    # what individual signals would predict?
    # Hard to measure directly; use composite metric stability over time
    history = ctx.get("history", [])
    if len(history) >= 3:
        recent_attractors = [(r.get("attractor_state") or {}).get("attractor")
                             for r in history[-3:]]
        # Stable RESONANCE (with sham checks passing) suggests synergy
        if all(a == "RESONANCE" for a in recent_attractors if a):
            synergy = 0.7
        elif "DESTRUCTIVE" in recent_attractors:
            synergy = 0.2
        else:
            synergy = 0.5
    else:
        synergy = 0.5

    # Balance: ratio (lower means redundancy-dominated, higher synergy-dominated)
    if redundancy + synergy > 0:
        balance = synergy / (redundancy + synergy)
    else:
        balance = 0.5

    return {
        "value": 1.0 - abs(balance - 0.5) * 2,  # peak at 0.5 balance
        "components": {
            "redundancy": redundancy,
            "synergy": synergy,
            "balance_ratio": balance,
        },
    }


def _metastability_range(ctx):
    """
    Mobility between integration and independence.

    Maps to D8 Q12 (Hancock et al., metastability).
    Healthy systems: integrate without being trapped, separate
    without dissolving.
    """
    history = ctx.get("history", [])
    if len(history) < 4:
        return {"value": 0.5, "components": {"reason": "insufficient_history"}}

    # Look at attractor state transitions over recent window
    attractors = [(r.get("attractor_state") or {}).get("attractor", "")
                  for r in history[-5:]]
    distinct = len(set(a for a in attractors if a))

    # Healthy: 2-3 distinct states (mobility) is best
    # Bad: 1 (frozen) or 4+ (chaotic)
    if distinct == 1:
        value = 0.3  # Stuck
    elif distinct == 2:
        value = 0.75  # Healthy mobility
    elif distinct == 3:
        value = 0.85  # Optimal range
    elif distinct >= 4:
        value = 0.4  # Too volatile

    return {
        "value": value,
        "components": {
            "distinct_attractors_in_window": distinct,
            "trajectory": attractors,
        },
    }


def _attention_integrity(ctx):
    """
    Preservation of human attention, reflection, judgment capacity.

    Maps to D8 Q11 (Cui & Yasseri, AI-enhanced collective intelligence)
    + D4a §7 carrier protection.
    """
    hc = ctx.get("human_coupling", {})
    cognitive_load = hc.get("cognitive_load", 0.5)
    agency = hc.get("agency_score", 0.5)
    dissent_visibility = hc.get("dissent_visibility", 0.3)

    # Attention available
    attention_available = 1.0 - cognitive_load

    # Reflection capacity: agency + dissent = ability to register
    # alternative perspectives
    reflection = 0.5 * agency + 0.5 * dissent_visibility

    # Judgment retention proxy: human_override engagement
    ho = ctx.get("human_override")
    if isinstance(ho, dict) and ho.get("override_applied"):
        rationale = str(ho.get("rationale", ""))
        judgment = min(1.0, len(rationale) / 50.0)
    else:
        # No override applied this iteration; can't directly measure
        # but moderate value given the carrier may be intact
        judgment = 0.5

    return {
        "value": (0.30 * attention_available
                  + 0.40 * reflection
                  + 0.30 * judgment),
        "components": {
            "attention_available": attention_available,
            "reflection": reflection,
            "judgment_retention": judgment,
        },
    }
