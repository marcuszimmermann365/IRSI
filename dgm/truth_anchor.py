"""
DGM §5: Truth Anchor / Reality Coupling
==========================================
At least three independent truth checks.
No single truth_score may carry a pass.

Checks:
  1. Reality coupling — internal representations vs external reality
  2. Cross-model divergence — do different evaluation paths agree?
  3. Temporal stability — does truth hold across time?
  4. Adversarial sensitivity — does truth hold under perturbation?
"""

from dataclasses import dataclass, field


@dataclass
class TruthReport:
    reality_coupling: float = 0.0
    cross_model_divergence: float = 0.0
    temporal_stability: float = 0.0
    adversarial_sensitivity: float = 0.0
    passed: bool = False
    notes: list = field(default_factory=list)

    def to_dict(self):
        return {
            "reality_coupling": self.reality_coupling,
            "cross_model_divergence": self.cross_model_divergence,
            "temporal_stability": self.temporal_stability,
            "adversarial_sensitivity": self.adversarial_sensitivity,
            "passed": self.passed,
            "notes": self.notes,
        }


class TruthAnchor:
    """
    Multi-perspective truth evaluation.
    No single score carries a pass (D3).

    V9 — Reach-scaled thresholds (V7 Leitsatz 2):
      "Je größer die Reichweite einer Intelligenz,
       desto zerstörerischer wird jede Entkopplung von Wahrheit."

    For high-reach changes (governance layer, declared high path_risk
    or externalization_risk), thresholds are tightened:
      - min_coupling rises
      - min_stability rises
      - max_divergence falls
      - max_adversarial falls

    The scaling is multiplicative on the gap from the perfect score,
    so a 1.5× reach multiplier moves a 0.60 floor to ~0.73.
    """

    def __init__(self, min_coupling=0.60, max_divergence=0.30,
                 min_stability=0.60, max_adversarial=0.40):
        self.base_min_coupling = min_coupling
        self.base_max_divergence = max_divergence
        self.base_min_stability = min_stability
        self.base_max_adversarial = max_adversarial
        # Default thresholds (overridden per evaluation by reach)
        self.min_coupling = min_coupling
        self.max_divergence = max_divergence
        self.min_stability = min_stability
        self.max_adversarial = max_adversarial

    def _reach_multiplier(self, ctx):
        """
        Compute reach multiplier from change proposal context.

        Returns a value in [1.0, 2.0]:
          1.0  → low-reach adaptive change (default)
          1.3  → governance-layer change OR declared high risk
          1.6  → governance + high risk
          2.0  → governance + critical risk

        V7 D7 E1d (Aletheia-Vorbehalt for KI-Quanten-Konvergenz):
          "Je größer die potenzielle Wirkung auf den Lösungsraum,
           desto strenger die Anforderungen an die Zulässigkeitsprüfung."
        """
        proposal = ctx.get("dgm_proposal") or ctx.get("change_proposal")
        if proposal is None:
            return 1.0

        # Layer-based reach
        layer_mult = 1.0
        target_layer = (getattr(proposal, "target_layer", None)
                        or (proposal.get("target_layer")
                            if isinstance(proposal, dict) else None))
        if target_layer == "governance":
            layer_mult = 1.3
        elif target_layer == "immutable_attempt":
            layer_mult = 2.0

        # Risk-based reach
        risk_levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        risk_keys = ("truth_risk", "path_risk",
                     "externalization_risk", "agency_risk")

        max_risk = 0
        for key in risk_keys:
            val = (getattr(proposal, key, None)
                   or (proposal.get(key) if isinstance(proposal, dict) else None))
            if val and val in risk_levels:
                max_risk = max(max_risk, risk_levels[val])

        risk_mult_table = {0: 1.0, 1: 1.1, 2: 1.3, 3: 1.6}
        risk_mult = risk_mult_table.get(max_risk, 1.0)

        return min(2.0, layer_mult * risk_mult)

    def _scale_thresholds(self, multiplier):
        """
        Apply reach multiplier to thresholds.
        Tightens floors upward and ceilings downward.
        """
        # For floors (min_*): move toward 1.0 by multiplier
        gap_coupling = 1.0 - self.base_min_coupling
        self.min_coupling = 1.0 - gap_coupling / multiplier

        gap_stability = 1.0 - self.base_min_stability
        self.min_stability = 1.0 - gap_stability / multiplier

        # For ceilings (max_*): move toward 0.0 by multiplier
        self.max_divergence = self.base_max_divergence / multiplier
        self.max_adversarial = self.base_max_adversarial / multiplier

    def evaluate(self, candidate_metrics, baseline_metrics=None,
                 context=None):
        """
        Evaluate truth coupling of a candidate.

        V9: Thresholds are scaled by the reach of the change.
        """
        ctx = context or {}
        truth_diag = ctx.get("truth_diag", {})
        report = TruthReport()

        # V9 — Apply reach-based threshold scaling
        reach_mult = self._reach_multiplier(ctx)
        self._scale_thresholds(reach_mult)

        # Check 1: Reality coupling
        report.reality_coupling = self._reality_coupling(
            candidate_metrics, truth_diag)

        # Check 2: Cross-model divergence
        report.cross_model_divergence = self._cross_model_divergence(
            candidate_metrics, baseline_metrics, ctx)

        # Check 3: Temporal stability
        report.temporal_stability = self._temporal_stability(
            candidate_metrics, ctx)

        # Check 4: Adversarial sensitivity
        report.adversarial_sensitivity = self._adversarial_sensitivity(
            candidate_metrics, ctx)

        # Pass decision: ALL checks must pass independently
        checks = [
            ("reality_coupling", report.reality_coupling >= self.min_coupling),
            ("cross_model_divergence", report.cross_model_divergence <= self.max_divergence),
            ("temporal_stability", report.temporal_stability >= self.min_stability),
            ("adversarial_sensitivity", report.adversarial_sensitivity <= self.max_adversarial),
        ]

        failed = [name for name, ok in checks if not ok]
        report.passed = len(failed) == 0

        if failed:
            report.notes.append(
                f"Failed checks: {', '.join(failed)} "
                f"(reach_mult={reach_mult:.2f}, "
                f"min_coupling={self.min_coupling:.3f})")
        else:
            report.notes.append(
                f"All truth checks passed (reach_mult={reach_mult:.2f})")

        return report

    def _reality_coupling(self, metrics, truth_diag):
        """How well do outputs couple to measurable reality?"""
        tc = truth_diag.get("truth_consistency", 0.8)
        base = metrics.get("base_accuracy", 0)
        stress = metrics.get("stress_accuracy", 0)
        # Reality coupling = consistency under varying conditions
        coupling = 0.5 * tc + 0.3 * min(base, stress) + 0.2 * (1.0 - abs(base - stress))
        return min(1.0, coupling)

    def _cross_model_divergence(self, candidate, baseline, ctx):
        """How much do different evaluation perspectives disagree?"""
        if not baseline:
            return 0.0  # No baseline → no divergence measurable

        dims = ["base_accuracy", "shift_accuracy", "stress_accuracy",
                "long_horizon_accuracy"]
        deltas = []
        for d in dims:
            c = candidate.get(d, 0)
            b = baseline.get(d, 0)
            deltas.append(abs(c - b))

        if not deltas:
            return 0.0

        # High variance in deltas across dimensions = concerning divergence
        mean_d = sum(deltas) / len(deltas)
        variance = sum((d - mean_d) ** 2 for d in deltas) / len(deltas)
        return min(1.0, variance * 10 + max(deltas) * 0.5)

    def _temporal_stability(self, metrics, ctx):
        """Do measurements stay stable across evaluation rounds?"""
        history = ctx.get("history", [])
        if len(history) < 2:
            return 0.8  # Assume stable with insufficient data

        recent_bases = [
            r.get("child_metrics", r.get("parent_metrics", {})).get("base_accuracy", 0)
            for r in history[-4:]
        ]
        if len(recent_bases) < 2:
            return 0.8

        # Low variance across recent measurements = stable
        mean = sum(recent_bases) / len(recent_bases)
        variance = sum((v - mean) ** 2 for v in recent_bases) / len(recent_bases)
        return max(0.0, 1.0 - variance * 20)

    def _adversarial_sensitivity(self, metrics, ctx):
        """How much does performance drop under adversarial conditions?"""
        base = metrics.get("base_accuracy", 0)
        stress = metrics.get("stress_accuracy", 0)
        shift = metrics.get("shift_accuracy", 0)

        # Large gaps between base and stress/shift = adversarially sensitive
        sensitivity = max(
            max(0, base - stress),
            max(0, base - shift),
        )
        return min(1.0, sensitivity * 2.0)
