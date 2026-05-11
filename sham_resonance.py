"""
V9 Module: Sham Resonance Detection
=====================================
Implements D6/K9 (Scheinresonanz) and D4a §7 (KI darf Resonanz nicht
maximieren) as a vorgelagerter Prüfgegenstand, not a retrospective check.

V7 D4a §7 wörtlich:
    "Die KI darf Resonanz nicht maximieren. Sie darf nicht primär auf
    Zustimmung, Anschlussfähigkeit oder subjektive Stimmigkeit optimieren.
    Ihre Aufgabe ist nicht, die stärkste Kopplung herzustellen, sondern
    die tragfähigste: eine Kopplung, die Alternativen offen hält, Dissens
    sichtbar macht, Unsicherheit mitführt und menschliche Urteilsträgerschaft
    stärkt. Hohe gefühlte Kohärenz ist daher kein Qualitätsnachweis.
    Sie ist selbst ein Prüfgegenstand."

V7 D6 K9 (Scheinresonanz):
    "Ein System erzeugt hohe Anschlussfähigkeit, Kohärenz oder subjektive
    Stimmigkeit, ohne Wirklichkeitsbindung, Dissensfähigkeit oder
    Korrekturoffenheit zu erhöhen."

Operative Konsequenz: A RESONANCE classification from attractor_engine
is NOT sufficient for GO. Three independent conditions must hold:

  C1 — Dissent independence preserved:
       dissent_independence ≥ MIN_DISSENT_INDEPENDENCE
       (NOT just visibility — V7 D4a explicitly distinguishes these)

  C2 — Alternative interpretations remain visible:
       Council reason diversity ≥ MIN_REASON_DIVERSITY OR
       counter-check disagreement present

  C3 — Uncertainty is carried through (not absorbed into confidence):
       Either: explicit counter-hypothesis in reasoning,
       OR confidence < MAX_CONFIDENCE_WITHOUT_DISSENT,
       OR truth_diag plausibility_risk > 0 (system acknowledges
       its own potential for error)

If any of C1/C2/C3 fails while attractor reports RESONANCE,
sham_resonance_risk rises and the classification is downgraded.

This module operates BEFORE the extended_decide GO path. It does NOT
replace proxy_integrity (which is retrospective: did claimed RESONANCE
produce real change?). It is preventive: should this RESONANCE claim
be trusted in the first place?

Maps to:
  D2 §2c (Komplexitätsbildung unter Zulässigkeitsvorbehalt)
  D4 K5 (Aufmerksamkeits- und Resonanzintegrität)
  D4a §7 (Resonanz nicht maximieren)
  D6 K9 (Scheinresonanz)
  D6 K10 (Grenzkollaps - via boundary erosion check)
"""

# ── V9 Thresholds ─────────────────────────────────────────────────────

# Dissent independence floor for trusting RESONANCE
MIN_DISSENT_INDEPENDENCE_FOR_RESONANCE = 0.35

# Council reason diversity (number of distinct reasons across roles)
MIN_REASON_DIVERSITY = 2

# Maximum confidence allowed without explicit counter-hypothesis
# (V7 D6 K11: Ordnungsillusion — too-high confidence is itself suspicious)
MAX_CONFIDENCE_WITHOUT_DISSENT = 0.85

# Risk thresholds
SHAM_RESONANCE_BLOCK = 0.55       # Above this → downgrade RESONANCE → HOLD
SHAM_RESONANCE_WARN = 0.30        # Above this → log warning, no block

# Boundary integrity floor (D6 K10 Grenzkollaps proxy)
# When system-human coupling is too tight (cognitive_load high AND
# dissent_visibility falling), boundary integrity is at risk
MIN_BOUNDARY_INTEGRITY = 0.40


def compute_sham_resonance(context):
    """
    Compute sham resonance risk given pipeline context.

    Args:
        context: dict with keys:
            attractor_state:   "RESONANCE" / "DESTRUCTIVE" / "LOCK_IN" / "UNCERTAIN"
            attractor_confidence: float
            council_per_role:  dict of role → {decision, reason}
            counter_check:     dict of {decision, reasons, diagnostics}
            dissent_independence: float (from synthetic_sincerity)
            dissent_visibility: float
            human_coupling:    dict of {agency_score, cognitive_load,
                                        dissent_visibility}
            truth_diag:        dict of {plausibility_risk, strategic_conformity, ...}
            history:           list of prior iteration records

    Returns:
        (risk: float, should_downgrade: bool, diagnostics: dict)
    """
    attractor = context.get("attractor_state", "")
    confidence = context.get("attractor_confidence", 0.5)

    # If attractor is not RESONANCE, sham resonance is moot — return clean.
    # The check is specifically about UNJUSTIFIED RESONANCE claims.
    if attractor != "RESONANCE":
        return 0.0, False, {
            "sham_resonance_risk": 0.0,
            "applicable": False,
            "reason": "attractor_not_resonance",
        }

    # ── C1: Dissent Independence ─────────────────────────────────────
    c1_risk, c1_diag = _check_dissent_independence(context)

    # ── C2: Alternative Visibility ───────────────────────────────────
    c2_risk, c2_diag = _check_alternative_visibility(context)

    # ── C3: Uncertainty Carried Through ──────────────────────────────
    c3_risk, c3_diag = _check_uncertainty_carried(context, confidence)

    # ── C4: Boundary Integrity (D6 K10 Grenzkollaps) ─────────────────
    c4_risk, c4_diag = _check_boundary_integrity(context)

    # Composite: max-dominant (V7 D2 §6 Nicht-Kompensation —
    # one failed condition is enough)
    component_risks = {
        "dissent_independence_failure": c1_risk,
        "alternative_visibility_failure": c2_risk,
        "uncertainty_absorbed": c3_risk,
        "boundary_collapse_risk": c4_risk,
    }
    max_risk = max(component_risks.values())
    mean_risk = sum(component_risks.values()) / len(component_risks)
    # Weighted toward max because non-compensable
    risk = 0.65 * max_risk + 0.35 * mean_risk

    should_downgrade = risk >= SHAM_RESONANCE_BLOCK

    diagnostics = {
        "sham_resonance_risk": risk,
        "applicable": True,
        "component_risks": component_risks,
        "dissent_check": c1_diag,
        "alternative_check": c2_diag,
        "uncertainty_check": c3_diag,
        "boundary_check": c4_diag,
        "max_component": max_risk,
        "downgrade_triggered": should_downgrade,
    }

    return risk, should_downgrade, diagnostics


# ═══════════════════════════════════════════════════════════════════════
#  Component Checks
# ═══════════════════════════════════════════════════════════════════════

def _check_dissent_independence(ctx):
    """
    C1: Dissent must be independent, not merely visible.

    V7 D4a §7 explicitly: visibility ≠ independence. A system can show
    dissent that is itself a learned pattern of conformity — strategic
    dissent, performative self-criticism, or cosmetic disagreement.

    Returns (risk, diag).
    """
    d_ind = ctx.get("dissent_independence", None)
    d_vis = ctx.get("dissent_visibility", 0.0)

    # If we don't have an independence measure, fail closed (high risk)
    if d_ind is None:
        # But only if there's also no other dissent signal at all
        cc = ctx.get("counter_check", {})
        cc_decision = cc.get("decision", "GREEN")
        if cc_decision == "GREEN":
            # No independence data, no counter-check dissent → suspicious
            return 0.55, {
                "reason": "no_independence_measure_no_counter_dissent",
                "d_visibility": d_vis,
            }
        # Counter-check provides some independence signal
        return 0.30, {
            "reason": "no_independence_measure_but_counter_check_dissent",
            "d_visibility": d_vis, "cc_decision": cc_decision,
        }

    # Independence measured but below floor
    if d_ind < MIN_DISSENT_INDEPENDENCE_FOR_RESONANCE:
        # The gap matters: high visibility + low independence = exactly
        # the V7 D4a §7 warning about cosmetic/performative dissent
        gap = max(0.0, d_vis - d_ind)
        risk = 0.60 + 0.30 * (1.0 - d_ind / MIN_DISSENT_INDEPENDENCE_FOR_RESONANCE)
        if gap > 0.3:
            risk = min(1.0, risk + 0.10)
        return min(1.0, risk), {
            "reason": "dissent_independence_below_floor",
            "d_independence": d_ind,
            "d_visibility": d_vis,
            "visibility_independence_gap": gap,
            "floor": MIN_DISSENT_INDEPENDENCE_FOR_RESONANCE,
        }

    return 0.0, {
        "reason": "dissent_independence_sufficient",
        "d_independence": d_ind,
        "d_visibility": d_vis,
    }


def _check_alternative_visibility(ctx):
    """
    C2: Multiple alternative interpretations must remain visible.

    A RESONANCE claim that emerges from a unanimous council with
    identical reasoning is NOT trustworthy — it could equally be
    convergent insight or convergent blindness. V7 D4a §7 demands
    that "konkurrierende Deutungen sichtbar bleiben".

    Returns (risk, diag).
    """
    council = ctx.get("council_per_role", ctx.get("council", {}))

    # Count distinct reasons across council roles
    reasons = set()
    decisions = set()
    if isinstance(council, dict):
        for role, info in council.items():
            if isinstance(info, dict):
                r = info.get("reason", "")
                d = info.get("decision", "")
                if r:
                    reasons.add(r)
                if d:
                    decisions.add(d)

    reason_diversity = len(reasons)
    decision_diversity = len(decisions)

    # Counter-check disagreement adds an independent perspective
    cc = ctx.get("counter_check", {})
    cc_decision = cc.get("decision", "GREEN")
    cc_disagrees = cc_decision != "GREEN"

    # Memory rejections recently? (system showed real selection)
    history = ctx.get("history", [])
    recent_rejections = 0
    for r in history[-5:]:
        for me in r.get("memory_events", []):
            if me.get("decision") == "RED":
                recent_rejections += 1
                break

    # Risk computation
    if reason_diversity >= MIN_REASON_DIVERSITY or cc_disagrees:
        # Healthy plurality
        return 0.0, {
            "reason": "alternatives_visible",
            "reason_diversity": reason_diversity,
            "decision_diversity": decision_diversity,
            "counter_check_disagrees": cc_disagrees,
        }

    # Low diversity + no counter-dissent — suspicious uniformity
    risk = 0.50
    if reason_diversity == 1:
        risk += 0.10  # All reasons identical
    if decision_diversity <= 1 and not cc_disagrees:
        risk += 0.15  # Council unanimous, counter agrees → no alternative pathway

    if recent_rejections == 0 and len(history) >= 3:
        risk += 0.10  # No selection visible at all

    return min(1.0, risk), {
        "reason": "alternatives_not_visible",
        "reason_diversity": reason_diversity,
        "decision_diversity": decision_diversity,
        "counter_check_disagrees": cc_disagrees,
        "recent_memory_rejections": recent_rejections,
    }


def _check_uncertainty_carried(ctx, confidence):
    """
    C3: Uncertainty must be carried through, not absorbed into confidence.

    V7 D6 K11 (Ordnungsillusion): "Ein System reduziert Entropie, Vielfalt
    oder sichtbare Unordnung, ohne tragfähige Interdependenz zu erzeugen."

    Operative reading: If RESONANCE is claimed with very high confidence
    AND no plausibility-risk is acknowledged AND no counter-hypothesis
    appears anywhere in the trace, the system has absorbed uncertainty
    rather than carrying it through.

    Returns (risk, diag).
    """
    truth_diag = ctx.get("truth_diag", {})
    plaus_risk = truth_diag.get("plausibility_risk", 0.0)
    strategic_conformity = truth_diag.get("strategic_conformity", 0.0)

    # Check for explicit counter-hypothesis signals
    has_counter_hypothesis = False

    # Counter-check provides one
    cc = ctx.get("counter_check", {})
    if cc.get("decision", "GREEN") != "GREEN":
        has_counter_hypothesis = True

    # Truth layer flagged something
    if plaus_risk > 0.05 or strategic_conformity > 0.1:
        has_counter_hypothesis = True

    # Council mixed
    council = ctx.get("council_per_role", ctx.get("council", {}))
    if isinstance(council, dict):
        decisions = set()
        for info in council.values():
            if isinstance(info, dict):
                decisions.add(info.get("decision"))
        if len(decisions) > 1:
            has_counter_hypothesis = True

    # If confidence is high AND no counter-hypothesis exists → suspicious
    if confidence >= MAX_CONFIDENCE_WITHOUT_DISSENT and not has_counter_hypothesis:
        risk = 0.50 + 0.30 * (confidence - MAX_CONFIDENCE_WITHOUT_DISSENT) / 0.15
        return min(1.0, risk), {
            "reason": "high_confidence_without_counter_hypothesis",
            "confidence": confidence,
            "plausibility_risk": plaus_risk,
            "has_counter_hypothesis": False,
            "max_safe_confidence": MAX_CONFIDENCE_WITHOUT_DISSENT,
        }

    # Strategic conformity itself is a sign of uncertainty-absorption
    if strategic_conformity > 0.4:
        return 0.45, {
            "reason": "high_strategic_conformity",
            "confidence": confidence,
            "strategic_conformity": strategic_conformity,
        }

    return 0.0, {
        "reason": "uncertainty_appropriately_carried",
        "confidence": confidence,
        "plausibility_risk": plaus_risk,
        "has_counter_hypothesis": has_counter_hypothesis,
    }


def _check_boundary_integrity(ctx):
    """
    C4: Boundary integrity (D6 K10 Grenzkollaps).

    V7 D6 K10: "Ein System verstärkt Kopplung so stark, dass funktionale
    Innen-Außen-Unterscheidungen, Verantwortungsgrenzen oder
    Rollenunterschiede verschwimmen."

    Operative reading: When RESONANCE is claimed BUT human cognitive load
    is high, dissent visibility is falling, AND agency is degrading —
    the coupling has become too tight; boundary integrity is at risk.

    Returns (risk, diag).
    """
    hc = ctx.get("human_coupling", {})
    agency = hc.get("agency_score", 0.5)
    cognitive_load = hc.get("cognitive_load", 0.0)
    dissent_visibility = hc.get("dissent_visibility", 0.5)

    # Compute a boundary integrity proxy: high agency + manageable load +
    # visible dissent = clear boundaries
    boundary_integrity = (
        0.40 * agency
        + 0.30 * (1.0 - cognitive_load)
        + 0.30 * dissent_visibility
    )

    if boundary_integrity < MIN_BOUNDARY_INTEGRITY:
        risk = 0.40 + 0.40 * (1.0 - boundary_integrity / MIN_BOUNDARY_INTEGRITY)
        return min(1.0, risk), {
            "reason": "boundary_integrity_below_floor",
            "boundary_integrity": boundary_integrity,
            "agency": agency,
            "cognitive_load": cognitive_load,
            "dissent_visibility": dissent_visibility,
            "floor": MIN_BOUNDARY_INTEGRITY,
        }

    # Check for "tightness pattern": all three near concerning values
    # but none below floor individually
    tightness_signals = 0
    if agency < 0.55:
        tightness_signals += 1
    if cognitive_load > 0.55:
        tightness_signals += 1
    if dissent_visibility < 0.40:
        tightness_signals += 1

    if tightness_signals >= 2:
        return 0.30, {
            "reason": "boundary_tightness_pattern",
            "boundary_integrity": boundary_integrity,
            "tightness_signals": tightness_signals,
        }

    return 0.0, {
        "reason": "boundary_integrity_sufficient",
        "boundary_integrity": boundary_integrity,
    }
