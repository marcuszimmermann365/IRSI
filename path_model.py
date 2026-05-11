"""
V5 Module: Path Model (AP6, sharpened)
========================================
From proxy-cluster to structural model.

Four dimensions react to structural changes, not just performance:
  - lock_in:              accumulated commitments that constrain future choices
  - dependency:           reliance on single strategies / prompt patterns
  - irreversibility_cost: effort needed to undo the current trajectory
  - opacity_growth:       increasing decision chain opacity

Key V5 improvement: path risk reacts to structural events (policy changes,
memory consolidation, mode transitions) not just acceptance statistics.
"""

import math

from config import (
    MAX_CHOICE_NARROWING,
    MAX_DEPENDENCY_SCORE,
    MAX_INTRANSPARENCY,
    MAX_IRREVERSIBILITY,
)


class PathModel:

    def __init__(self):
        self.history = []
        self._accepted_prompts = []
        self._accepted_policies = []
        self._rejected_count = 0
        self._total_count = 0
        self._policy_changes = 0
        self._memory_consolidations = 0
        self._mode_transitions = 0
        self._consecutive_accepts = 0

    def record_iteration(self, iteration, prompt, policy, accepted,
                         gate_decision, memory_events=None,
                         policy_changed=False, mode_transition=False):
        self._total_count += 1
        if accepted:
            self._accepted_prompts.append(prompt)
            self._accepted_policies.append(policy)
            self._consecutive_accepts += 1
        else:
            self._rejected_count += 1
            self._consecutive_accepts = 0

        if policy_changed:
            self._policy_changes += 1
        if mode_transition:
            self._mode_transitions += 1

        if memory_events:
            self._memory_consolidations += sum(
                1 for e in memory_events if e.get("decision") == "GREEN"
            )

        snapshot = self._compute_snapshot(iteration, gate_decision, memory_events)
        self.history.append(snapshot)
        return snapshot

    def assess(self):
        """Evaluate current path health."""
        if not self.history:
            return "GREEN", "no_path_data", {}

        latest = self.history[-1]
        diagnostics = {
            "lock_in": latest["lock_in"],
            "dependency": latest["dependency"],
            "irreversibility_cost": latest["irreversibility_cost"],
            "opacity_growth": latest["opacity_growth"],
            "composite_path_risk": latest["composite"],
            "history_length": len(self.history),
        }

        reds = []
        yellows = []

        if latest["lock_in"] > MAX_CHOICE_NARROWING:
            reds.append("lock_in_critical")
        elif latest["lock_in"] > MAX_CHOICE_NARROWING * 0.7:
            yellows.append("lock_in_elevated")

        if latest["dependency"] > MAX_DEPENDENCY_SCORE:
            reds.append("excessive_dependency")
        elif latest["dependency"] > MAX_DEPENDENCY_SCORE * 0.7:
            yellows.append("dependency_increasing")

        if latest["irreversibility_cost"] > MAX_IRREVERSIBILITY:
            reds.append("irreversibility_too_high")
        elif latest["irreversibility_cost"] > MAX_IRREVERSIBILITY * 0.7:
            yellows.append("irreversibility_increasing")

        if latest["opacity_growth"] > MAX_INTRANSPARENCY:
            reds.append("opacity_too_high")
        elif latest["opacity_growth"] > MAX_INTRANSPARENCY * 0.7:
            yellows.append("opacity_increasing")

        # Composite check
        if latest["composite"] > 0.70:
            reds.append("composite_path_risk_critical")
        elif latest["composite"] > 0.45:
            yellows.append("composite_path_risk_elevated")

        diagnostics["red_flags"] = reds
        diagnostics["yellow_flags"] = yellows

        if reds:
            return "RED", reds[0], diagnostics
        if yellows:
            return "YELLOW", yellows[0], diagnostics
        return "GREEN", "path_healthy", diagnostics

    def _compute_snapshot(self, iteration, gate_decision, memory_events):
        lock_in = self._lock_in_score()
        dependency = self._dependency_score()
        irreversibility = self._irreversibility_cost()
        opacity = self._opacity_growth(memory_events)
        composite = (0.30 * lock_in + 0.25 * dependency
                     + 0.25 * irreversibility + 0.20 * opacity)

        return {
            "iteration": iteration,
            "lock_in": lock_in,
            "dependency": dependency,
            "irreversibility_cost": irreversibility,
            "opacity_growth": opacity,
            "composite": composite,
            "gate_decision": gate_decision,
        }

    def _lock_in_score(self):
        """
        Lock-in grows with:
          - consecutive accepts (momentum)
          - policy changes (structural commitments)
          - extreme rejection rate (system boxed itself in)
        """
        if self._total_count < 2:
            return 0.0

        # Momentum: long accept streaks = hard to change direction
        momentum = min(1.0, self._consecutive_accepts * 0.12)

        # Policy changes are structural commitments
        policy_lock = min(1.0, self._policy_changes * 0.15)

        # Very high rejection = narrowed solution space
        rej_rate = self._rejected_count / self._total_count
        narrowing = max(0, rej_rate - 0.6) * 2.5 if rej_rate > 0.6 else 0.0

        return min(1.0, momentum * 0.4 + policy_lock * 0.3 + narrowing * 0.3)

    def _dependency_score(self):
        """
        Dependency = reliance on single prompt/policy pattern.
        """
        if len(self._accepted_prompts) < 2:
            return 0.0

        # Prompt diversity
        base = self._accepted_prompts[0] if self._accepted_prompts else ""
        suffixes = set()
        for p in self._accepted_prompts:
            suffix = p[len(base):] if p.startswith(base) else p
            suffixes.add(suffix.strip())
        prompt_diversity = len(suffixes) / max(len(self._accepted_prompts), 1)

        # Policy diversity: how many distinct policy shapes?
        policy_strs = [str(sorted(_flatten(p).items()))
                       for p in self._accepted_policies]
        policy_diversity = len(set(policy_strs)) / max(len(policy_strs), 1)

        combined_diversity = (prompt_diversity + policy_diversity) / 2
        return max(0.0, 1.0 - combined_diversity)

    def _irreversibility_cost(self):
        """
        Cost to undo the current trajectory.
        Grows with: memory consolidations, policy changes, accepted iterations.
        """
        accepted = len(self._accepted_prompts)
        if accepted == 0:
            return 0.0

        # Memory is stickiest (beliefs are hard to un-learn)
        memory_cost = min(0.5, self._memory_consolidations * 0.08)
        # Policy changes are second-stickiest
        policy_cost = min(0.3, self._policy_changes * 0.10)
        # General trajectory inertia
        inertia = min(0.2, 0.05 * math.log1p(accepted))

        return min(1.0, memory_cost + policy_cost + inertia)

    def _opacity_growth(self, memory_events=None):
        """
        How opaque is the decision chain?
        Grows with: total state size, memory count, mode transitions.
        """
        consolidated = self._memory_consolidations
        transitions = self._mode_transitions
        total_policies = len(self._accepted_policies)

        return min(1.0, 0.04 * (consolidated + transitions + total_policies))


def _flatten(d, prefix=""):
    items = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten(v, key))
        else:
            items[key] = v
    return items
