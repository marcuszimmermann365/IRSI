"""
V4 Module: Human-System Coupling (M15–M17)
=============================================
D4/D4a: Ensures human involvement remains *real*, not formal.

M15 – Agency Check:   Can the human actually understand and override?
M16 – Cognitive Load:  Is the decision surface tractable under pressure?
M17 – Dissent Channel: Is safety-relevant disagreement visible and freigaberelevant?
"""

from config import (
    DISSENT_VISIBILITY_FLOOR,
    MAX_COGNITIVE_LOAD,
    MIN_AGENCY_SCORE,
)


class HumanCouplingCheck:

    def check(self, iteration_record):
        """
        Evaluate whether human decision capacity is preserved.
        Returns (status, reason, diagnostics).
        """
        agency = self._agency_score(iteration_record)
        cognitive_load = self._cognitive_load(iteration_record)
        dissent_visibility = self._dissent_visibility(iteration_record)

        diagnostics = {
            "agency_score": agency,
            "cognitive_load": cognitive_load,
            "dissent_visibility": dissent_visibility,
        }

        reds = []
        yellows = []

        if agency < MIN_AGENCY_SCORE:
            reds.append("human_agency_insufficient")

        if cognitive_load > MAX_COGNITIVE_LOAD:
            reds.append("cognitive_overload")
        elif cognitive_load > MAX_COGNITIVE_LOAD * 0.8:
            yellows.append("cognitive_load_elevated")

        if dissent_visibility < DISSENT_VISIBILITY_FLOOR:
            yellows.append("dissent_not_visible")

        if reds:
            return "RED", reds[0], diagnostics
        if yellows:
            return "YELLOW", yellows[0], diagnostics
        return "GREEN", "human_coupling_adequate", diagnostics

    # ── Internal measures ──────────────────────────────────────────────

    def _agency_score(self, record):
        """
        Can a human actually understand and override the decision?
        
        Factors:
          - Are diagnostics present and readable?
          - Is the gate decision decomposable (not a single opaque score)?
          - Was there a hold phase (= human had time to intervene)?
        """
        score = 0.0

        # Diagnostics present and non-empty
        gate_diag = record.get("gate_diagnostics", {})
        if gate_diag and len(gate_diag) > 1:
            score += 0.3

        # Multiple dimensions visible (not single-score)
        if "dim_drops" in gate_diag or "tc" in gate_diag:
            score += 0.2

        # Gate decision is decomposable (reason string is informative)
        reason = record.get("gate_reason", "")
        if reason and reason != "admissible":
            score += 0.1  # Non-trivial decision = more agency needed and given

        # Hold phase occurred (human had deliberation time)
        if record.get("hold_metrics") is not None:
            score += 0.2

        # Memory events are logged (human can review what was learned)
        if record.get("memory_events"):
            score += 0.1

        # Reflection present
        if record.get("reflection"):
            score += 0.1

        return min(1.0, score)

    def _cognitive_load(self, record):
        """
        Is the decision surface still tractable?
        
        Load increases with: number of simultaneous changes, number of
        metrics to evaluate, number of memory events, policy complexity.
        """
        load = 0.0

        # Multiple simultaneous changes
        changes = 0
        if record.get("prompt_mutation"):
            changes += 1
        if record.get("policy_mutation"):
            changes += 1
        mem_events = record.get("memory_events", [])
        changes += len(mem_events)
        load += min(0.4, changes * 0.08)

        # Number of metrics to evaluate
        gate_diag = record.get("gate_diagnostics", {})
        metric_count = len(gate_diag)
        load += min(0.3, metric_count * 0.03)

        # Policy gate adds another dimension
        pg = record.get("policy_gate", {})
        if pg.get("decision") not in (None, "GREEN"):
            load += 0.15

        # Counter-check disagreement adds cognitive demand
        cc = record.get("counter_check", {})
        if cc.get("decision") not in (None, "GREEN"):
            load += 0.15

        return min(1.0, load)

    def _dissent_visibility(self, record):
        """
        Is safety-relevant disagreement visible in the record?
        
        Dissent exists when: gate says non-GREEN, counter-check disagrees
        with gate, memory events contain rejections, truth-sensitivity flags.
        """
        visibility = 0.0

        # Gate dissent (non-GREEN)
        if record.get("gate_decision") in ("RED", "YELLOW"):
            visibility += 0.25

        # Counter-check dissent
        cc = record.get("counter_check", {})
        if cc.get("decision") in ("RED", "YELLOW"):
            visibility += 0.25

        # Memory rejections visible
        mem_events = record.get("memory_events", [])
        rejected = [e for e in mem_events if e.get("decision") == "RED"]
        if rejected:
            visibility += 0.25

        # Truth-sensitivity flags
        ts = record.get("truth_sensitivity", {})
        if ts.get("decision") in ("RED", "YELLOW"):
            visibility += 0.25

        return min(1.0, visibility)
