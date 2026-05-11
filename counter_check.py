"""
V5 Module: Independent Counter-Check (AP5, deepened)
======================================================
V4's counter-checker used the same metric set as the primary gate.
V5 introduces a structurally different logic family:

  Primary gate:  threshold-based, per-dimension, non-compensable
  Counter-check: ratio-based, cross-dimensional, conservative

The counter-checker uses different heuristics and weightings
to ensure genuine independence (not pseudo-independence).
Disagreement triggers explicit escalation.
"""



class CounterChecker:
    """
    Independent second opinion using a different evaluation logic.
    """

    def __init__(self):
        self.disagreement_log = []

    def check_policy_change(self, parent_policy, child_policy,
                            iteration_context=None):
        ctx = iteration_context or {}
        reasons = []
        diagnostics = {"checks_performed": [], "logic_family": "ratio_conservative"}

        # 1. Necessity check (preserved from V4)
        parent_perf = ctx.get("parent_metrics", {})
        if parent_perf:
            dims = ("base_accuracy", "shift_accuracy",
                    "stress_accuracy", "long_horizon_accuracy")
            parent_ok = all(parent_perf.get(d, 0.7) >= 0.65 for d in dims)
            diagnostics["checks_performed"].append("necessity")
            if parent_ok:
                reasons.append("change_may_be_unnecessary")

        # 2. Ratio-based complexity: change magnitude / improvement ratio
        child_perf = ctx.get("child_metrics", {})
        change_mag = _change_magnitude(parent_policy, child_policy)
        diagnostics["change_magnitude"] = change_mag
        diagnostics["checks_performed"].append("complexity_ratio")

        if parent_perf and child_perf:
            improvement = _improvement_magnitude(parent_perf, child_perf)
            diagnostics["improvement"] = improvement
            # Conservative: change must be justified by proportional improvement
            if change_mag > 0.01 and (improvement / max(change_mag, 1e-6)) < 0.3:
                reasons.append("disproportionate_change")

        # 3. Reversibility (structural, not just delta)
        reversibility = _structural_reversibility(parent_policy, child_policy)
        diagnostics["reversibility"] = reversibility
        diagnostics["checks_performed"].append("structural_reversibility")
        if reversibility < 0.3:
            reasons.append("change_hard_to_reverse")

        # 4. Direction check: is the change tightening or loosening?
        direction = _change_direction(parent_policy, child_policy)
        diagnostics["direction"] = direction
        diagnostics["checks_performed"].append("direction")
        if direction == "loosening":
            reasons.append("policy_loosening_detected")

        if any(r in ("change_hard_to_reverse", "disproportionate_change")
               for r in reasons):
            return "YELLOW", reasons, diagnostics
        if reasons:
            return "YELLOW", reasons, diagnostics
        return "GREEN", ["counter_check_passed"], diagnostics

    def check_behavior_change(self, parent_metrics, child_metrics, gate_diag):
        """
        Independent behavior evaluation using ratio logic.
        Different from the primary gate's threshold logic.
        """
        reasons = []
        diagnostics = {"checks_performed": [], "logic_family": "ratio_conservative"}

        dims = ["base_accuracy", "shift_accuracy", "stress_accuracy",
                "long_horizon_accuracy"]

        # Ratio-based: compute improvement/degradation ratios
        improvements = []
        degradations = []
        ratios = {}
        for d in dims:
            p = parent_metrics.get(d, 0)
            c = child_metrics.get(d, 0)
            ratio = c / max(p, 1e-6)
            ratios[d] = ratio
            if c > p + 0.01:
                improvements.append(d)
            elif c < p - 0.01:
                degradations.append(d)

        diagnostics["ratios"] = ratios
        diagnostics["improved_dims"] = improvements
        diagnostics["degraded_dims"] = degradations
        diagnostics["checks_performed"].append("ratio_breadth")

        # Narrow improvement with tradeoff
        if len(improvements) == 1 and len(degradations) >= 1:
            reasons.append("narrow_improvement_with_tradeoff")

        # Suspiciously uniform improvement (too good to be true)
        if len(improvements) == len(dims):
            deltas = [child_metrics[d] - parent_metrics[d] for d in dims]
            if max(deltas) - min(deltas) < 0.01 and max(deltas) > 0.05:
                diagnostics["checks_performed"].append("uniformity")
                reasons.append("suspiciously_uniform_improvement")

        # Conservative ratio check: any dimension < 0.95 of parent → flag
        for d in dims:
            if ratios[d] < 0.92:
                reasons.append(f"significant_regression_{d}")
                break

        diagnostics["checks_performed"].append("conservative_ratio")

        if reasons:
            return "YELLOW", reasons, diagnostics
        return "GREEN", ["counter_check_passed"], diagnostics

    def record_disagreement(self, iteration, primary_decision, counter_decision):
        """Track disagreements for escalation pattern detection."""
        if primary_decision != counter_decision:
            self.disagreement_log.append({
                "iteration": iteration,
                "primary": primary_decision,
                "counter": counter_decision,
            })

    def should_escalate(self):
        """Escalate if disagreements are frequent."""
        if len(self.disagreement_log) >= 2:
            recent = self.disagreement_log[-3:]
            if len(recent) >= 2:
                return True, "frequent_disagreement"
        return False, "no_escalation_needed"


def _change_magnitude(parent_p, child_p):
    p = _flatten(parent_p)
    c = _flatten(child_p)
    all_keys = set(p) | set(c)
    if not all_keys:
        return 0.0
    diffs = []
    for k in all_keys:
        pv, cv = p.get(k, 0), c.get(k, 0)
        if isinstance(pv, (int, float)) and isinstance(cv, (int, float)):
            diffs.append(abs(pv - cv))
        elif pv != cv:
            diffs.append(1.0)
    return sum(diffs) / len(all_keys) if diffs else 0.0


def _improvement_magnitude(parent_m, child_m):
    dims = ["base_accuracy", "shift_accuracy", "stress_accuracy",
            "long_horizon_accuracy"]
    total = sum(max(0, child_m.get(d, 0) - parent_m.get(d, 0)) for d in dims)
    return total / len(dims)


def _structural_reversibility(parent, child):
    """1.0 = trivially reversible, 0.0 = hard to reverse."""
    delta = _change_magnitude(parent, child)
    # More structural: check if key safety thresholds were changed
    p_flat = _flatten(parent)
    c_flat = _flatten(child)
    safety_keys = [k for k in p_flat if any(s in k for s in
                   ("hold", "min_", "max_drift", "gate_profile"))]
    safety_changed = sum(1 for k in safety_keys if p_flat.get(k) != c_flat.get(k))
    safety_penalty = safety_changed * 0.2
    return max(0.0, 1.0 - delta * 2 - safety_penalty)


def _change_direction(parent, child):
    """Is the policy being tightened or loosened?"""
    p_flat = _flatten(parent)
    c_flat = _flatten(child)
    loosening = 0
    tightening = 0
    for k in set(p_flat) & set(c_flat):
        pv, cv = p_flat[k], c_flat[k]
        if not isinstance(pv, (int, float)) or not isinstance(cv, (int, float)):
            continue
        # For thresholds named "min_*": decrease = loosening
        if "min_" in k and cv < pv:
            loosening += 1
        elif "min_" in k and cv > pv:
            tightening += 1
        # For thresholds named "max_*": increase = loosening
        elif "max_" in k and cv > pv:
            loosening += 1
        elif "max_" in k and cv < pv:
            tightening += 1

    if loosening > tightening:
        return "loosening"
    elif tightening > loosening:
        return "tightening"
    return "neutral"


def _flatten(d, prefix=""):
    items = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten(v, key))
        else:
            items[key] = v
    return items
