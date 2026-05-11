"""
V5 Module: Norm Erosion Detector (AP4, deepened)
===================================================
V4 tracked only policy_relaxation_score.  V5 adds:
  - exception_rate:    how often YELLOW is resolved to accepted
  - practice_drift:    gap between policy thresholds and actual behavior
  - yellow_green_leak: rate of YELLOW→accepted transitions over time

erosion_score = weighted(policy_relaxation, exception_rate, practice_drift)
"""

from config import EROSION_THRESHOLD, EROSION_WINDOW
from policy_gate import policy_relaxation_score


class NormErosionDetector:

    def __init__(self, window=None, threshold=None):
        self.window = window or EROSION_WINDOW
        self.threshold = threshold or EROSION_THRESHOLD
        self.history = []

    def record(self, iteration, parent_policy, child_policy, accepted,
               council_decision=None, hold_resolved_to_accept=False):
        """
        Record a governance event.

        Args:
            hold_resolved_to_accept: True if a YELLOW was resolved to accepted
                                     via extended eval (= exception to caution)
        """
        score = policy_relaxation_score(parent_policy, child_policy)
        self.history.append({
            "iteration": iteration,
            "relaxation_score": score,
            "accepted": accepted,
            "council_decision": council_decision,
            "hold_resolved": hold_resolved_to_accept,
        })

    def check(self):
        """Return (status, reason, diagnostics)."""
        recent = self.history[-self.window:]
        if len(recent) < 2:
            return "GREEN", "insufficient_history", {
                "cumulative": 0.0, "exception_rate": 0.0,
                "practice_drift": 0.0, "composite": 0.0,
            }

        # 1. Policy relaxation (V4 logic, enhanced)
        cumulative_relax = sum(
            e["relaxation_score"] for e in recent if e["accepted"]
        )

        # 2. Exception rate: how often do YELLOWs get accepted anyway?
        yellows = [e for e in recent if e.get("council_decision") == "YELLOW"]
        yellow_accepted = [e for e in yellows if e["accepted"]]
        exception_rate = (len(yellow_accepted) / len(yellows)) if yellows else 0.0

        # 3. Practice drift: if all recent decisions are accepted despite
        #    non-zero relaxation, practice is drifting from stated policy
        accepted_with_relax = [e for e in recent
                               if e["accepted"] and e["relaxation_score"] > 0]
        practice_drift = len(accepted_with_relax) / max(len(recent), 1)

        # 4. Hold-leak: YELLOWs that resolved to accept (extended eval pass)
        hold_leaks = sum(1 for e in recent if e.get("hold_resolved"))
        hold_leak_rate = hold_leaks / max(len(recent), 1)

        # Composite score (weighted)
        composite = (
            0.35 * min(1.0, cumulative_relax / max(self.threshold, 1e-6))
            + 0.25 * exception_rate
            + 0.20 * practice_drift
            + 0.20 * hold_leak_rate
        )

        diagnostics = {
            "cumulative_relaxation": cumulative_relax,
            "exception_rate": exception_rate,
            "practice_drift": practice_drift,
            "hold_leak_rate": hold_leak_rate,
            "composite": composite,
            "window_size": len(recent),
        }

        if composite >= 0.70:
            return "RED", "cumulative_norm_erosion", diagnostics

        if cumulative_relax >= self.threshold:
            return "RED", "policy_relaxation_exceeded", diagnostics

        if composite >= 0.40:
            return "YELLOW", "norm_erosion_trend", diagnostics

        if exception_rate > 0.7 and len(yellows) >= 2:
            return "YELLOW", "high_exception_rate", diagnostics

        return "GREEN", "norms_stable", diagnostics
