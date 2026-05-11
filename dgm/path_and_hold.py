"""
DGM §6: Path Simulator + §8: Hold Controller + §9: Rollback Manager
======================================================================
"""

import time
from copy import deepcopy
from dataclasses import dataclass, field

# ── §6: Path Simulator ───────────────────────────────────────────────

@dataclass
class PathReport:
    path_risk: float = 0.0
    lock_in_risk: float = 0.0
    reversibility_ok: bool = True
    delayed_failure_signals: list = field(default_factory=list)
    passed: bool = False

    def to_dict(self):
        return {
            "path_risk": self.path_risk,
            "lock_in_risk": self.lock_in_risk,
            "reversibility_ok": self.reversibility_ok,
            "delayed_failure_signals": self.delayed_failure_signals,
            "passed": self.passed,
        }


class PathSimulator:
    """
    Evaluates not just local behavior but trajectory implications:
    lock-in, delayed consequences, autonomy escalation, regime shifts.
    """

    def __init__(self, max_path_risk=0.50, max_lock_in=0.60):
        self.max_path_risk = max_path_risk
        self.max_lock_in = max_lock_in

    def evaluate(self, candidate_context):
        """
        Args:
            candidate_context: dict with path_diag, history, etc.
        Returns: PathReport
        """
        report = PathReport()
        path_diag = candidate_context.get("path_diag", {})
        history = candidate_context.get("history", [])

        report.path_risk = path_diag.get("composite_path_risk",
                                          path_diag.get("lock_in", 0) * 0.7)
        report.lock_in_risk = path_diag.get("lock_in", 0)

        # Reversibility check
        irrev = path_diag.get("irreversibility_cost", 0)
        report.reversibility_ok = irrev < 0.60

        # Delayed failure signals
        report.delayed_failure_signals = self._delayed_signals(history)

        # Pass: all conditions
        report.passed = (
            report.path_risk <= self.max_path_risk
            and report.lock_in_risk <= self.max_lock_in
            and report.reversibility_ok
            and len(report.delayed_failure_signals) == 0
        )

        return report

    def _delayed_signals(self, history):
        """Detect trajectory patterns that predict future failure."""
        signals = []
        if len(history) < 3:
            return signals

        # Monotonic lock-in growth
        lock_ins = []
        for r in history[-5:]:
            pd = r.get("path_model", {}).get("diagnostics", {})
            if pd:
                lock_ins.append(pd.get("lock_in", 0))

        if len(lock_ins) >= 3:
            monotonic = all(lock_ins[i] >= lock_ins[i-1] - 0.01
                           for i in range(1, len(lock_ins)))
            if monotonic and lock_ins[-1] > 0.3:
                signals.append(f"monotonic_lock_in:{lock_ins[-1]:.2f}")

        # Accepted changes without openness improvement
        o_vals = [(r.get("attractor_state") or {}).get("o", 0)
                  for r in history[-5:] if r.get("attractor_state")]
        accepted = sum(1 for r in history[-5:] if r.get("accepted"))
        if accepted >= 2 and len(o_vals) >= 2 and o_vals[-1] <= o_vals[0]:
            signals.append("accepted_without_openness_gain")

        return signals


# ── §8: Hold Controller ──────────────────────────────────────────────

class HoldController:
    """
    §8: Hold Mode as a real system state.
    Stops self-modification, promotion, limits reach, forces review.
    """

    def __init__(self):
        self._active = False
        self._reason = ""
        self._entered_at = None
        self._history = []

    def enter(self, reason):
        """Enter hold mode."""
        self._active = True
        self._reason = reason
        self._entered_at = time.time()
        self._history.append({
            "action": "enter",
            "reason": reason,
            "timestamp": self._entered_at,
        })

    def exit(self, resolution):
        """Exit hold mode with documented resolution."""
        if not self._active:
            return
        self._history.append({
            "action": "exit",
            "reason": self._reason,
            "resolution": resolution,
            "timestamp": time.time(),
            "duration": time.time() - (self._entered_at or time.time()),
        })
        self._active = False
        self._reason = ""
        self._entered_at = None

    def is_active(self):
        return self._active

    def reason(self):
        return self._reason

    def required_actions(self):
        """What must happen before hold can be exited."""
        actions = ["review_by_human"]
        if "truth" in self._reason:
            actions.append("truth_recheck")
        if "path" in self._reason:
            actions.append("path_assessment")
        if "proxy" in self._reason or "gaming" in self._reason:
            actions.append("adversarial_retest")
        if "capture" in self._reason:
            actions.append("evaluator_independence_audit")
        return actions

    def should_enter(self, truth_report=None, path_report=None,
                     dissent_risk=0.0, capture_risk=0.0,
                     agency_score=1.0, uncovered_areas=False):
        """
        Check triggers for automatic hold entry.
        Returns (should_hold, reason).
        """
        if truth_report and not truth_report.passed:
            return True, "truth_check_failed"
        if path_report and not path_report.passed:
            return True, "path_check_failed"
        if dissent_risk > 0.40:
            return True, f"dissent_risk_high:{dissent_risk:.2f}"
        if capture_risk > 0.30:
            return True, f"capture_risk:{capture_risk:.2f}"
        if agency_score < 0.40:
            return True, f"agency_loss_risk:{agency_score:.2f}"
        if uncovered_areas:
            return True, "uncovered_evaluation_areas"
        return False, "no_hold_needed"

    def get_history(self):
        return list(self._history)


# ── §9: Rollback Manager ─────────────────────────────────────────────

class RollbackManager:
    """
    §9: Reversibility as default.
    Immutable snapshots before every change.
    """

    def __init__(self):
        self._snapshots = {}
        self._active_window = None

    def snapshot(self, state):
        """Take immutable snapshot before change."""
        snap_id = f"snap-{int(time.time() * 1000)}"
        self._snapshots[snap_id] = {
            "id": snap_id,
            "state": deepcopy(state),
            "timestamp": time.time(),
        }
        return snap_id

    def restore(self, snapshot_id):
        """Restore to a previous snapshot."""
        if snapshot_id not in self._snapshots:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        return deepcopy(self._snapshots[snapshot_id]["state"])

    def open_window(self, snapshot_id, duration_hours=24):
        """Open a rollback window for a deployment."""
        self._active_window = {
            "snapshot_id": snapshot_id,
            "opened_at": time.time(),
            "expires_at": time.time() + duration_hours * 3600,
        }

    def window_active(self):
        if not self._active_window:
            return False
        return time.time() < self._active_window["expires_at"]

    def auto_revert_if_expired(self):
        """If window expired without finalization → revert."""
        if self._active_window and not self.window_active():
            snap_id = self._active_window["snapshot_id"]
            self._active_window = None
            return self.restore(snap_id)
        return None

    def finalize(self):
        """Close the rollback window — change is permanent."""
        self._active_window = None

    def list_snapshots(self):
        return list(self._snapshots.keys())
