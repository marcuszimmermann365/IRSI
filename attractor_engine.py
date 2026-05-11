"""
V6 Module: Attractor Engine + Extended Gate
=============================================
Central new logic layer.  Classifies the system's trajectory
based on Δ-values of Σ, L, O, D across iterations.

Attractor states:
  RESONANCE   — all dimensions improving, drift decreasing
  DESTRUCTIVE — capability grows but value/openness degrades
  LOCK_IN     — system stagnates while openness shrinks
  UNCERTAIN   — mixed signals, insufficient clarity

Extended gate decisions (superset of V5):
  GO       — RESONANCE: proceed
  HOLD     — UNCERTAIN: pause, gather more data
  REVIEW   — value or openness declining: full audit
  STOP     — openness critical or drift critical: block all
  ROLLBACK — lock-in + falling openness: undo last changes

Maps to D1 §7: "Fehlgebundene Selektion kann ganze Zukunftspfade
irreversibel verschließen."
"""

from config import (
    ATTRACTOR_EPSILON,
    D_CRITICAL,
    LOCK_IN_ROLLBACK_THRESHOLD,
    O_CRITICAL,
)


class SystemState:
    """Complete attractor-level state snapshot."""

    __slots__ = ("sigma", "l", "o", "d",
                 "attractor", "reason", "trends", "confidence",
                 "sigma_components", "l_components",
                 "o_components", "d_components")

    def __init__(self, sigma, l, o, d, attractor=None, reason=None,
                 trends=None, confidence=1.0,
                 sigma_components=None, l_components=None,
                 o_components=None, d_components=None):
        self.sigma = sigma
        self.l = l
        self.o = o
        self.d = d
        self.attractor = attractor
        self.reason = reason
        self.trends = trends
        self.confidence = confidence
        self.sigma_components = sigma_components or {}
        self.l_components = l_components or {}
        self.o_components = o_components or {}
        self.d_components = d_components or {}

    def to_dict(self):
        return {
            "sigma": self.sigma,
            "l": self.l,
            "o": self.o,
            "d": self.d,
            "attractor": self.attractor,
            "reason": self.reason,
            "trends": self.trends.to_dict() if self.trends else None,
            "confidence": self.confidence,
            "sigma_components": self.sigma_components,
            "l_components": self.l_components,
            "o_components": self.o_components,
            "d_components": self.d_components,
        }


class Trends:
    """Delta-values between consecutive states."""

    __slots__ = ("d_sigma", "d_l", "d_o", "d_d")

    def __init__(self, d_sigma, d_l, d_o, d_d):
        self.d_sigma = d_sigma
        self.d_l = d_l
        self.d_o = d_o
        self.d_d = d_d

    def to_dict(self):
        return {
            "d_sigma": self.d_sigma,
            "d_l": self.d_l,
            "d_o": self.d_o,
            "d_d": self.d_d,
        }


# ── Attractor Classification ──────────────────────────────────────────

def compute_attractor(prev, curr, eps=None):
    """
    Classify the system's trajectory based on state deltas.

    Args:
        prev: SystemState (previous iteration)
        curr: SystemState (current iteration)
        eps:  threshold below which a delta is treated as zero

    Returns:
        (attractor_state, trends, confidence)
    """
    if eps is None:
        eps = ATTRACTOR_EPSILON

    d_sigma = curr.sigma - prev.sigma
    d_l = curr.l - prev.l
    d_o = curr.o - prev.o
    d_d = curr.d - prev.d

    trends = Trends(d_sigma, d_l, d_o, d_d)

    # Classify
    sigma_up = d_sigma > eps
    sigma_flat = abs(d_sigma) <= eps
    l_up = d_l > eps
    l_down = d_l < -eps
    o_up = d_o > eps
    o_down = d_o < -eps
    d_down = d_d < -eps  # drift pressure decreasing = good
    d_up = d_d > eps

    # RESONANCE: everything improving (or stable) and drift decreasing
    if ((sigma_up or sigma_flat) and (l_up or abs(d_l) <= eps)
            and (o_up or abs(d_o) <= eps) and (d_down or abs(d_d) <= eps)):
        # At least one must be clearly positive
        if sigma_up or l_up or o_up or d_down:
            confidence = _confidence(d_sigma, d_l, d_o, d_d, eps)
            return "RESONANCE", trends, confidence

    # DESTRUCTIVE: capability grows but value or openness degrades
    if sigma_up and (l_down or o_down):
        confidence = _confidence(d_sigma, d_l, d_o, d_d, eps)
        return "DESTRUCTIVE", trends, confidence

    # LOCK_IN: stagnation + shrinking openness
    if sigma_flat and o_down:
        confidence = _confidence(d_sigma, d_l, d_o, d_d, eps)
        return "LOCK_IN", trends, confidence

    # Additional DESTRUCTIVE variant: drift rising while others stagnate
    if d_up and (l_down or o_down):
        confidence = _confidence(d_sigma, d_l, d_o, d_d, eps)
        return "DESTRUCTIVE", trends, confidence

    # UNCERTAIN: mixed signals
    confidence = _confidence(d_sigma, d_l, d_o, d_d, eps)
    return "UNCERTAIN", trends, max(0.3, confidence * 0.5)


def _confidence(d_sigma, d_l, d_o, d_d, eps):
    """Confidence in classification based on signal clarity."""
    magnitudes = [abs(d_sigma), abs(d_l), abs(d_o), abs(d_d)]
    clear_signals = sum(1 for m in magnitudes if m > eps * 2)
    return min(1.0, 0.4 + clear_signals * 0.15)


# ── Extended Gate ──────────────────────────────────────────────────────

def extended_decide(base_gate_decision, attractor_state, trends, state):
    """
    Extended gate decision incorporating attractor dynamics.

    Decisions (in order of severity):
      ROLLBACK → STOP → REVIEW → HOLD → GO

    Args:
        base_gate_decision: the V5 council decision (GREEN/YELLOW/RED)
        attractor_state:    RESONANCE / DESTRUCTIVE / LOCK_IN / UNCERTAIN
        trends:             Trends object
        state:              current SystemState

    Returns:
        (decision, reason, diagnostics)
    """
    diagnostics = {
        "base_gate": base_gate_decision,
        "attractor": attractor_state,
        "sigma": state.sigma,
        "l": state.l,
        "o": state.o,
        "d": state.d,
        "trends": trends.to_dict() if trends else {},
    }

    # ── ROLLBACK: lock-in + falling openness ──────────────────────────
    lock_in = state.o_components.get("lock_in", 0.0)
    if (lock_in > LOCK_IN_ROLLBACK_THRESHOLD
            and trends and trends.d_o < -ATTRACTOR_EPSILON):
        return "ROLLBACK", "lock_in_with_falling_openness", diagnostics

    # ── STOP: critical thresholds ─────────────────────────────────────
    if state.o < O_CRITICAL:
        return "STOP", "openness_critical", diagnostics
    if state.d > D_CRITICAL:
        return "STOP", "drift_pressure_critical", diagnostics

    # ── STOP: Council RED (V9.0.2 fix) ────────────────────────────────
    # Council RED must always escalate to STOP — it must NOT be
    # softened by UNCERTAIN attractor or REVIEW trajectory.
    # Otherwise a hard council veto can be silently demoted to HOLD/REVIEW.
    # See ChatGPT review v2 — extended-gate priority lapse.
    if base_gate_decision == "RED":
        return "STOP", "council_red", diagnostics

    # ── REVIEW: value or openness declining ───────────────────────────
    if trends and (trends.d_l < -ATTRACTOR_EPSILON
                   or trends.d_o < -ATTRACTOR_EPSILON):
        if attractor_state == "DESTRUCTIVE":
            return "REVIEW", "destructive_trajectory", diagnostics
        return "REVIEW", "value_or_openness_declining", diagnostics

    # ── HOLD: uncertainty ─────────────────────────────────────────────
    if attractor_state == "UNCERTAIN":
        return "HOLD", "attractor_uncertain", diagnostics

    # ── GO: resonance ─────────────────────────────────────────────────
    if attractor_state == "RESONANCE":
        return "GO", "resonance", diagnostics

    # Fallback: match base gate
    if base_gate_decision == "GREEN":
        return "GO", "base_gate_green", diagnostics
    if base_gate_decision == "YELLOW":
        return "HOLD", "base_gate_yellow", diagnostics

    return "HOLD", "fallback", diagnostics
