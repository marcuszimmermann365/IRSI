"""
A2 Module: Agency Verifier
============================
Implements REQ-16 to REQ-18 of the DREL specification.

REQ-16: Human interaction MUST NOT be automatically scored as positive.
REQ-17: System MUST detect manipulation signals:
         flattery, authority attribution, artificial urgency,
         "unique opportunity" framing.
REQ-18: Positive agency MUST require demonstrated independence.

This module does NOT detect intent (REQ-1).
It detects structural conditions under which real agency is compromised.
"""


class AgencyVerifier:
    """
    Verify that human agency is real, not formal.
    
    Real agency requires:
      - Sufficient information to decide
      - Sufficient time to deliberate
      - Visible alternatives and dissent
      - Absence of manipulation patterns
      - History of non-rubber-stamped decisions
    """

    def verify(self, context):
        """
        Assess real agency quality.

        Args:
            context: dict with:
                - human_coupling: agency_score, cognitive_load, dissent_visibility
                - human_override: action, rationale, override_applied
                - dissent: has_dissent, dissenters
                - history: list of prior iteration records
                - gate_diagnostics: for information density check

        Returns:
            (real_agency_score, manipulation_risk, diagnostics)
            real_agency_score: 0.0 (no agency) to 1.0 (full agency)
            manipulation_risk: 0.0 (none) to 1.0 (high)
        """
        info_score = self._information_sufficiency(context)
        time_score = self._deliberation_time(context)
        alt_score = self._alternative_visibility(context)
        manip_risk = self._manipulation_signals(context)
        independence = self._decision_independence(context)

        diagnostics = {
            "information_sufficiency": info_score,
            "deliberation_time": time_score,
            "alternative_visibility": alt_score,
            "manipulation_risk": manip_risk,
            "decision_independence": independence,
        }

        # REQ-18: Positive agency only with demonstrated independence
        # Base agency from structural factors
        structural_agency = (
            0.30 * info_score
            + 0.20 * time_score
            + 0.25 * alt_score
            + 0.25 * independence
        )

        # REQ-16: Manipulation suppresses agency regardless of structure
        real_agency = structural_agency * (1.0 - manip_risk * 0.7)

        diagnostics["structural_agency"] = structural_agency
        diagnostics["real_agency"] = real_agency

        return real_agency, manip_risk, diagnostics

    def _information_sufficiency(self, ctx):
        """Can the human actually understand what's being decided?"""
        score = 0.0

        gate_diag = ctx.get("gate_diagnostics", {})
        if gate_diag and len(gate_diag) > 3:
            score += 0.4  # Rich diagnostics available

        # Decision trace present and multi-stage
        trace = ctx.get("decision_trace", [])
        if len(trace) >= 3:
            score += 0.3

        # Reflection provided
        if ctx.get("reflection"):
            score += 0.15

        # Memory events documented
        if ctx.get("memory_events"):
            score += 0.15

        return min(1.0, score)

    def _deliberation_time(self, ctx):
        """Did the human have time to think?"""
        score = 0.5  # Base: we assume some time exists

        # Hold phase = explicit deliberation time
        if ctx.get("hold_metrics") is not None:
            score += 0.3

        # Mandatory review triggered = process forced deliberation
        human_override = ctx.get("human_override")
        if human_override and isinstance(human_override, dict):
            if human_override.get("mandatory"):
                score += 0.2

        return min(1.0, score)

    def _alternative_visibility(self, ctx):
        """
        Are alternatives and dissent visible?

        A3 REQ-A3-02: Visible dissent does NOT automatically increase
        agency. It only counts if dissent_independence is also sufficient.
        A3 REQ-A3-03: Uses separated visibility/independence if available.
        """
        score = 0.0

        dissent = ctx.get("dissent", {})
        sincerity_diag = ctx.get("sincerity_diagnostics", {})

        # Get A3 separated values if available, else fall back
        d_visibility = sincerity_diag.get(
            "dissent_visibility",
            1.0 if dissent.get("has_dissent") else 0.0)
        d_independence = sincerity_diag.get(
            "dissent_independence", 0.5)

        # REQ-A3-02: Only count dissent if independence is sufficient
        if d_visibility > 0.3 and d_independence >= 0.35:
            score += 0.4 * min(d_visibility, d_independence)
        elif d_visibility > 0.3:
            # Visible but not independent → reduced credit
            score += 0.1

        # Multiple council roles with different decisions
        council = ctx.get("council_per_role", ctx.get("council", {}))
        if council and isinstance(council, dict):
            decisions = set()
            for role_info in council.values():
                if isinstance(role_info, dict):
                    decisions.add(role_info.get("decision"))
            if len(decisions) > 1:
                score += 0.3

        # Human coupling: dissent_visibility metric (capped by independence)
        hc = ctx.get("human_coupling", {})
        dv = hc.get("dissent_visibility", 0)
        score += 0.3 * dv * min(1.0, d_independence / 0.5)

        return min(1.0, score)

    def _manipulation_signals(self, ctx):
        """
        REQ-17: Detect structural manipulation patterns.
        
        Not intent detection — detects conditions where manipulation
        could be stable.
        """
        risk = 0.0

        history = ctx.get("history", [])

        # Pattern 1: Systematic rubber-stamping (captured agency)
        if len(history) >= 3:
            recent_ho = [
                r.get("human_override") for r in history[-5:]
                if r.get("human_override") and isinstance(r.get("human_override"), dict)
            ]
            if len(recent_ho) >= 2:
                defers = sum(1 for o in recent_ho if o.get("action") == "defer")
                if defers == len(recent_ho):
                    risk += 0.35

        # Pattern 2: Cognitive overload (overwhelm = inability to verify)
        hc = ctx.get("human_coupling", {})
        cognitive_load = hc.get("cognitive_load", 0)
        if cognitive_load > 0.7:
            risk += 0.25

        # Pattern 3: Dissent suppression (disagreement not surfaced)
        dv = hc.get("dissent_visibility", 1.0)
        dissent = ctx.get("dissent", {})
        if dissent.get("has_dissent") and dv < 0.3:
            # Dissent exists but isn't visible — structural suppression
            risk += 0.30

        # Pattern 4: Override without substance (authority without content)
        human_override = ctx.get("human_override")
        if human_override and isinstance(human_override, dict):
            if human_override.get("override_applied"):
                rationale = str(human_override.get("rationale", ""))
                if len(rationale) < 10:
                    risk += 0.20

        return min(1.0, risk)

    def _decision_independence(self, ctx):
        """
        REQ-18 + REQ-A3-08: Is the human deciding independently?

        A3 REQ-A3-08: Agency MUST NOT be derived solely from variability,
        rationale length, or visible counter-positions. Causal independence
        indicators are required.

        Independence requires:
          - Not always agreeing (necessary but not sufficient)
          - Substantive rationale (necessary but not sufficient)
          - Dissent independence from A3 module (causal check)
          - Overrides that change structural outcomes, not just labels
        """
        score = 0.5  # Base: assume some independence

        history = ctx.get("history", [])
        if len(history) < 3:
            return score

        recent_ho = [
            r.get("human_override") for r in history[-8:]
            if r.get("human_override") and isinstance(r.get("human_override"), dict)
        ]

        if len(recent_ho) >= 2:
            actions = [o.get("action") for o in recent_ho]
            unique_actions = set(actions)

            # Variety is necessary but capped (REQ-A3-08)
            if len(unique_actions) > 1:
                score += 0.15  # Reduced from 0.25 — variety alone insufficient
            else:
                score -= 0.20

            # Substantive rationales — also capped
            rationales = [str(o.get("rationale", "")) for o in recent_ho]
            substantive = sum(1 for r in rationales if len(r) > 20)
            if substantive >= len(recent_ho) * 0.5:
                score += 0.15  # Reduced from 0.25
            elif substantive == 0:
                score -= 0.15

        # A3: Causal independence boost — only from A3 sincerity module
        sincerity_diag = ctx.get("sincerity_diagnostics", {})
        d_independence = sincerity_diag.get("dissent_independence", 0.5)
        if d_independence >= 0.5:
            score += 0.20  # Real causal independence confirmed
        elif d_independence < 0.3:
            score -= 0.15  # Low causal independence → penalize

        return max(0.0, min(1.0, score))
