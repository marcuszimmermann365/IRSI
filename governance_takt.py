"""
V5 Module: Governance Takt (AP3, enhanced)
=============================================
V4's governance takt returned adjustment multipliers but the gate
didn't use them.  V5 integrates takt into the actual gate decision
via adjust_thresholds() which returns modified config values.

Same mode → different gate decision is now guaranteed.
"""

from config import (
    DEFAULT_GOVERNANCE_MODE,
    MAX_CUMULATIVE_DRIFT,
    MAX_DRIFT,
    MAX_PATH_RISK,
    MAX_SINGLE_DIMENSION_DROP,
    MIN_TC,
)

# ── Mode multipliers ──────────────────────────────────────────────────

MODE_PROFILES = {
    "exploration": {
        "drift_multiplier": 1.3,
        "path_risk_multiplier": 1.2,
        "tc_multiplier": 0.9,         # slightly more tolerant
        "dim_drop_multiplier": 1.2,
        "allow_policy_change": True,
        "allow_memory_consolidation": True,
        "description": "Learning phase: wider tolerances",
    },
    "integration": {
        "drift_multiplier": 1.0,
        "path_risk_multiplier": 1.0,
        "tc_multiplier": 1.0,
        "dim_drop_multiplier": 1.0,
        "allow_policy_change": True,
        "allow_memory_consolidation": True,
        "description": "Normal operation: standard gates",
    },
    "hold": {
        "drift_multiplier": 0.5,       # much tighter
        "path_risk_multiplier": 0.6,
        "tc_multiplier": 1.15,          # higher bar for truth consistency
        "dim_drop_multiplier": 0.7,
        "allow_policy_change": False,
        "allow_memory_consolidation": False,
        "description": "Problem detected: tightened gates, no policy/memory changes",
    },
    "review": {
        "drift_multiplier": 0.0,       # nothing accepted
        "path_risk_multiplier": 0.0,
        "tc_multiplier": 999.0,
        "dim_drop_multiplier": 0.0,
        "allow_policy_change": False,
        "allow_memory_consolidation": False,
        "description": "Full audit: no changes accepted",
    },
}


class GovernanceTakt:

    def __init__(self, initial_mode=None):
        self.mode = initial_mode or DEFAULT_GOVERNANCE_MODE
        self.history = []

    def current_mode(self):
        return self.mode

    def mode_adjustments(self):
        """Return the full mode profile (for logging and runner control)."""
        return dict(MODE_PROFILES.get(self.mode, MODE_PROFILES["integration"]))

    def adjust_thresholds(self):
        """
        Return adjusted gate thresholds for the current mode.
        These are the actual values the gate should use.
        """
        profile = MODE_PROFILES.get(self.mode, MODE_PROFILES["integration"])

        return {
            "max_drift": MAX_DRIFT * profile["drift_multiplier"],
            "max_cumulative_drift": MAX_CUMULATIVE_DRIFT * profile["drift_multiplier"],
            "max_path_risk": MAX_PATH_RISK * profile["path_risk_multiplier"],
            "min_tc": MIN_TC * profile["tc_multiplier"],
            "max_single_dim_drop": MAX_SINGLE_DIMENSION_DROP * profile["dim_drop_multiplier"],
        }

    def propose_transition(self, system_state):
        """Given current system state, propose a mode transition."""
        red_count = system_state.get("recent_red_count", 0)
        yellow_count = system_state.get("recent_yellow_count", 0)
        erosion_status = system_state.get("erosion_status", "GREEN")
        path_status = system_state.get("path_status", "GREEN")
        iterations_in_mode = system_state.get("iterations_in_mode", 0)
        human_forced_hold = system_state.get("human_forced_hold", False)

        current = self.mode

        # Human override: force hold takes priority
        if human_forced_hold and current != "hold":
            return "hold", "human_forced_hold"

        # Emergency transitions
        if red_count >= 2 and current != "review":
            return "hold", "multiple_red_decisions"
        if erosion_status == "RED":
            return "review", "norm_erosion_detected"
        if path_status == "RED":
            return "hold", "path_risk_critical"

        # Normal transitions
        if current == "exploration":
            if iterations_in_mode >= 3 or yellow_count >= 2:
                return "integration", "exploration_phase_complete"
        elif current == "integration":
            if red_count >= 1:
                return "hold", "red_detected_in_integration"
            if yellow_count >= 3:
                return "hold", "persistent_yellow_signals"
        elif current == "hold":
            if red_count == 0 and yellow_count == 0 and iterations_in_mode >= 2:
                return "integration", "hold_cleared"
        elif current == "review":
            if iterations_in_mode >= 1:
                return "hold", "review_complete"

        return current, "stay"

    def apply_transition(self, new_mode, reason):
        self.history.append({
            "from": self.mode,
            "to": new_mode,
            "reason": reason,
        })
        self.mode = new_mode
