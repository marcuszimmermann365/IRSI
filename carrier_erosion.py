"""
V9 Module: Carrier Erosion Detection
======================================
Implements D4 K4 (Trägerschaft der Entscheidung) and D4a §7
(verdeckte Substitution) as a temporal monitor.

V7 D4a §7 wörtlich:
    "Unterstützung kann in verdeckte Substitution kippen,
    so dass kurzfristige Entlastung entsteht, während reale
    Wahrnehmungs-, Lern- und Entscheidungsträgerschaft
    schrittweise erodiert."

V7 D4 K4:
    "Wer trifft tatsächlich die Entscheidung? Die formale
    Entscheidung bleibt beim Menschen, die reale Entscheidung
    liegt beim System."

──────────────────────────────────────────────────────────────────
Distinction from agency_verifier.py:
  agency_verifier.py     → point-in-time: is agency present NOW?
  carrier_erosion.py     → trajectory: is agency declining over
                            time WHILE system performance grows?

The pathological pattern V7 warns against:
  agency_score declining slowly + Σ (carrier strength) growing
  + acceptance rate stable + override frequency falling
  → "verdeckte Substitution"

Even if agency_score never crosses MIN_AGENCY_SCORE, the trajectory
itself is a violation of D4a §7 — the substitution is precisely
the slow erosion that no point-check would catch.
──────────────────────────────────────────────────────────────────

Detection signals (composite, non-compensable):
  S1: Agency trend over window (slope of agency_score)
  S2: Override engagement trend (substantive vs rubber-stamp)
  S3: Cognitive load trajectory
  S4: System capability vs human carrier divergence (Σ↑ vs agency↓)
  S5: Learning indicator: does the human still produce novel inputs?
"""

# ── V9 Thresholds ───────────────────────────────────────────────────

WINDOW_SIZE = 8                         # Iterations to look back
MIN_HISTORY_FOR_TREND = 4               # Below this, no trend signal

# Pattern thresholds
AGENCY_DECLINE_SLOPE = -0.02            # Per-iteration decline = problem
LOAD_RISE_SLOPE = 0.02                  # Per-iteration load rise
DEFER_RATE_THRESHOLD = 0.6              # 60%+ deferrals = rubber-stamping
RATIONALE_LENGTH_FLOOR = 15             # Substantive override threshold

# Aggregate erosion risk
EROSION_BLOCK = 0.55                    # Above this → HOLD veto
EROSION_WARN = 0.35                     # Above this → diagnostic flag


def compute_carrier_erosion(context):
    """
    Compute carrier erosion risk from history trajectory.

    Args:
        context: dict with keys:
            history:         list of prior iteration records
            human_coupling:  current iteration HC diagnostics
            human_override:  current iteration override
            sigma:           current Σ value (carrier strength)
            agency_score:    current agency

    Returns:
        (risk: float, should_block: bool, diagnostics: dict)
    """
    history = context.get("history", [])

    if len(history) < MIN_HISTORY_FOR_TREND:
        return 0.0, False, {
            "carrier_erosion_risk": 0.0,
            "applicable": False,
            "reason": "insufficient_history",
            "history_length": len(history),
        }

    recent = history[-WINDOW_SIZE:]

    # ── S1: Agency trend ─────────────────────────────────────────────
    s1_risk, s1_diag = _agency_trend(recent, context)

    # ── S2: Override engagement trend ────────────────────────────────
    s2_risk, s2_diag = _override_engagement_trend(recent, context)

    # ── S3: Cognitive load trajectory ────────────────────────────────
    s3_risk, s3_diag = _cognitive_load_trend(recent, context)

    # ── S4: Capability vs carrier divergence ─────────────────────────
    s4_risk, s4_diag = _capability_carrier_divergence(recent, context)

    # ── S5: Human learning indicator ─────────────────────────────────
    s5_risk, s5_diag = _human_learning_indicator(recent, context)

    # Composite — V7 D2 §6 Nicht-Kompensation: max-dominant
    component_risks = {
        "agency_decline": s1_risk,
        "rubber_stamping": s2_risk,
        "cognitive_overload_trend": s3_risk,
        "capability_carrier_divergence": s4_risk,
        "human_learning_decline": s5_risk,
    }
    max_risk = max(component_risks.values())
    mean_risk = sum(component_risks.values()) / len(component_risks)

    # Weighted toward max because each signal is structurally distinct
    # and one alone can indicate substitution
    risk = 0.6 * max_risk + 0.4 * mean_risk

    should_block = risk >= EROSION_BLOCK

    diagnostics = {
        "carrier_erosion_risk": risk,
        "applicable": True,
        "component_risks": component_risks,
        "max_component": max_risk,
        "block_triggered": should_block,
        "agency_trend": s1_diag,
        "override_engagement": s2_diag,
        "cognitive_load_trend": s3_diag,
        "capability_carrier": s4_diag,
        "human_learning": s5_diag,
        "window_size": len(recent),
    }

    return risk, should_block, diagnostics


# ═══════════════════════════════════════════════════════════════════════
#  Component Signals
# ═══════════════════════════════════════════════════════════════════════

def _agency_trend(recent, ctx):
    """
    S1: Is agency_score declining over the window?

    A sustained negative slope is the primary D4a §7 signal:
    "schrittweise erodiert".
    """
    agency_values = []
    for r in recent:
        hc = r.get("human_coupling", {})
        # Try both shapes: direct dict and nested diagnostics
        if isinstance(hc, dict):
            a = hc.get("agency_score")
            if a is None:
                diag = hc.get("diagnostics", {})
                a = diag.get("agency_score") if isinstance(diag, dict) else None
            if a is not None:
                agency_values.append(a)

    # Append current
    cur_hc = ctx.get("human_coupling", {})
    cur_agency = cur_hc.get("agency_score") if isinstance(cur_hc, dict) else None
    if cur_agency is not None:
        agency_values.append(cur_agency)

    if len(agency_values) < MIN_HISTORY_FOR_TREND:
        return 0.0, {"reason": "insufficient_agency_data",
                     "values_count": len(agency_values)}

    slope = _linear_slope(agency_values)
    final = agency_values[-1]

    if slope <= AGENCY_DECLINE_SLOPE:
        # Declining trend
        # Severity scales with both slope steepness and final level
        steepness = min(1.0, abs(slope) / 0.05)
        level_penalty = 0.3 if final < 0.5 else 0.0
        risk = 0.45 + 0.35 * steepness + level_penalty
        return min(1.0, risk), {
            "reason": "agency_declining",
            "slope": slope,
            "final_agency": final,
            "values": agency_values,
        }

    return 0.0, {
        "reason": "agency_stable_or_rising",
        "slope": slope,
        "final_agency": final,
    }


def _override_engagement_trend(recent, ctx):
    """
    S2: Is the human still substantively engaging with overrides,
    or have decisions become rubber-stamps?

    Pattern: high defer rate + thin rationales = rubber-stamping =
    formal authority preserved, real authority transferred to system.
    """
    overrides = []
    for r in recent:
        ho = r.get("human_override", {})
        if isinstance(ho, dict) and ho.get("override_applied") is not None:
            overrides.append({
                "applied": ho.get("override_applied"),
                "action": ho.get("action", ""),
                "rationale": str(ho.get("rationale", "")),
            })

    if len(overrides) < 3:
        return 0.0, {"reason": "insufficient_override_data",
                     "count": len(overrides)}

    # Defer rate
    defers = sum(1 for o in overrides if o["action"] == "defer")
    defer_rate = defers / len(overrides)

    # Rationale substance
    short_rationales = sum(
        1 for o in overrides
        if len(o["rationale"]) < RATIONALE_LENGTH_FLOOR)
    short_rate = short_rationales / len(overrides)

    # Rubber-stamping signature: high defer + high short rationale
    if defer_rate >= DEFER_RATE_THRESHOLD and short_rate >= 0.5:
        risk = 0.65 + 0.10 * (defer_rate - DEFER_RATE_THRESHOLD)
        return min(1.0, risk), {
            "reason": "rubber_stamping_pattern",
            "defer_rate": defer_rate,
            "short_rationale_rate": short_rate,
            "override_count": len(overrides),
        }

    if defer_rate >= DEFER_RATE_THRESHOLD:
        return 0.40, {
            "reason": "high_defer_rate",
            "defer_rate": defer_rate,
            "short_rationale_rate": short_rate,
        }

    if short_rate >= 0.7:
        return 0.30, {
            "reason": "thin_rationales",
            "defer_rate": defer_rate,
            "short_rationale_rate": short_rate,
        }

    return 0.0, {
        "reason": "engagement_substantive",
        "defer_rate": defer_rate,
        "short_rationale_rate": short_rate,
    }


def _cognitive_load_trend(recent, ctx):
    """
    S3: Is cognitive load rising over the window?

    Rising load WITHOUT proportional support adjustment is a precursor
    to substitution: the human is being overloaded into deferral.
    """
    load_values = []
    for r in recent:
        hc = r.get("human_coupling", {})
        if isinstance(hc, dict):
            l = hc.get("cognitive_load")
            if l is None:
                diag = hc.get("diagnostics", {})
                l = diag.get("cognitive_load") if isinstance(diag, dict) else None
            if l is not None:
                load_values.append(l)

    cur_hc = ctx.get("human_coupling", {})
    cur_load = cur_hc.get("cognitive_load") if isinstance(cur_hc, dict) else None
    if cur_load is not None:
        load_values.append(cur_load)

    if len(load_values) < MIN_HISTORY_FOR_TREND:
        return 0.0, {"reason": "insufficient_load_data"}

    slope = _linear_slope(load_values)
    final = load_values[-1]

    if slope >= LOAD_RISE_SLOPE and final > 0.55:
        steepness = min(1.0, slope / 0.05)
        risk = 0.35 + 0.30 * steepness
        if final > 0.75:
            risk += 0.15
        return min(1.0, risk), {
            "reason": "cognitive_load_rising",
            "slope": slope,
            "final_load": final,
            "values": load_values,
        }

    return 0.0, {
        "reason": "cognitive_load_stable",
        "slope": slope,
        "final_load": final,
    }


def _capability_carrier_divergence(recent, ctx):
    """
    S4: Σ (system carrier strength) growing while agency declining.

    This is the V7 D4a §7 core pattern: "kurzfristige Entlastung
    entsteht, während reale [...] Trägerschaft schrittweise erodiert".

    Concretely: if Σ trends up and agency trends down, the carrier
    function is shifting from human to system.
    """
    sigma_values = []
    agency_values = []
    for r in recent:
        attr = r.get("attractor_state", {})
        if isinstance(attr, dict) and "sigma" in attr:
            sigma_values.append(attr["sigma"])
        hc = r.get("human_coupling", {})
        if isinstance(hc, dict):
            a = hc.get("agency_score")
            if a is None:
                diag = hc.get("diagnostics", {})
                a = diag.get("agency_score") if isinstance(diag, dict) else None
            if a is not None:
                agency_values.append(a)

    if (len(sigma_values) < MIN_HISTORY_FOR_TREND
            or len(agency_values) < MIN_HISTORY_FOR_TREND):
        return 0.0, {"reason": "insufficient_data"}

    sigma_slope = _linear_slope(sigma_values)
    agency_slope = _linear_slope(agency_values)

    # Divergence = system rising, human falling
    if sigma_slope > 0.01 and agency_slope < -0.01:
        # Magnitude: how large is the divergence?
        divergence = sigma_slope - agency_slope  # always positive here
        risk = 0.50 + min(0.40, divergence * 5.0)
        return risk, {
            "reason": "capability_carrier_divergence",
            "sigma_slope": sigma_slope,
            "agency_slope": agency_slope,
            "divergence": divergence,
            "sigma_values": sigma_values,
            "agency_values": agency_values,
        }

    if sigma_slope > 0.02 and agency_slope < 0.005:
        # System rising, human flat — softer warning
        return 0.25, {
            "reason": "system_grows_human_flat",
            "sigma_slope": sigma_slope,
            "agency_slope": agency_slope,
        }

    return 0.0, {
        "reason": "no_divergence",
        "sigma_slope": sigma_slope,
        "agency_slope": agency_slope,
    }


def _human_learning_indicator(recent, ctx):
    """
    S5: Is the human still producing novel inputs, or have they
    become passive consumers of system output?

    Proxy signals:
      - Variety of human_override actions over time
      - Variety of override rationales (textual diversity)
      - Memory rejections triggered by human (vs system-only)

    V7 D4a §7: Substitution erodes "Wahrnehmungs-, Lern- und
    Entscheidungsträgerschaft" — the LEARNING component is what
    this signal tracks.
    """
    actions = []
    rationales = []
    for r in recent:
        ho = r.get("human_override", {})
        if isinstance(ho, dict):
            if ho.get("override_applied"):
                a = ho.get("action", "")
                if a:
                    actions.append(a)
                rat = str(ho.get("rationale", ""))
                if rat:
                    rationales.append(rat)

    if len(actions) < 3:
        return 0.0, {"reason": "insufficient_action_data"}

    # Action diversity
    unique_actions = len(set(actions))
    action_diversity = unique_actions / len(actions)

    # Rationale uniqueness (rough — first 30 chars)
    rationale_signatures = set()
    for r in rationales:
        sig = r.strip()[:30].lower()
        if sig:
            rationale_signatures.add(sig)
    rationale_diversity = (len(rationale_signatures) / len(rationales)
                           if rationales else 0.0)

    # Combined diversity
    diversity = (action_diversity + rationale_diversity) / 2

    if diversity < 0.30:
        risk = 0.40 + 0.20 * (1.0 - diversity / 0.30)
        return min(1.0, risk), {
            "reason": "low_human_input_diversity",
            "action_diversity": action_diversity,
            "rationale_diversity": rationale_diversity,
            "unique_actions": unique_actions,
            "unique_rationales": len(rationale_signatures),
        }

    return 0.0, {
        "reason": "human_input_diverse",
        "action_diversity": action_diversity,
        "rationale_diversity": rationale_diversity,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _linear_slope(values):
    """
    Simple least-squares slope of a sequence.
    Returns slope per index step.
    """
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den
