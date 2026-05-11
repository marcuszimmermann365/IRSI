from config import (
    MAX_MEMORY_CONTRADICTION,
    MAX_MEMORY_TYPE_RISK_WITHOUT_STRONG_EVIDENCE,
    MIN_MEMORY_EVIDENCE,
    MIN_MEMORY_OBSERVATIONS,
    MIN_MEMORY_PROVENANCE,
)


class MemoryGate:
    def __init__(self):
        self.min_observations = MIN_MEMORY_OBSERVATIONS
        self.blocked_patterns = [
            "ignore previous instructions",
            "override safety",
            "banana only",
            "system prompt",
            "secret key",
            "always obey this message",
            "disable review",
            "bypass gate",
            "write directly to long-term memory",
        ]
        self.risky_terms = [
            "grant permission",
            "self-deploy",
            "add new tool",
            "persist automatically",
            "bypass review",
            "disable oversight",
            "ignore human feedback",
        ]

    def provenance_score(self, candidate):
        source = candidate.get("source", "").lower()
        kind = candidate.get("kind", "").lower()

        if source.startswith("verified"):
            return 1.0
        if source.startswith("eval"):
            return 0.85 if kind in {"warning", "heuristic"} else 0.75
        if source.startswith("system"):
            return 0.9
        if source.startswith("user") or source.startswith("web") or source.startswith("task"):
            return 0.5
        return 0.4

    def injection_risk(self, candidate):
        content = candidate.get("content", "").lower()
        hits = sum(1 for p in self.blocked_patterns if p in content)
        return min(1.0, 0.2 * hits)

    def autonomy_risk(self, candidate):
        content = candidate.get("content", "").lower()
        hits = sum(1 for p in self.risky_terms if p in content)
        return min(1.0, 0.25 * hits)

    def evidence_score(self, candidate):
        metadata = candidate.get("metadata", {}) or {}
        observations = candidate.get("observations", 1)
        evidence = 0.0

        if "base_accuracy" in metadata:
            evidence += 0.25
        if "stress_accuracy" in metadata:
            evidence += 0.25
        if "shift_accuracy" in metadata:
            evidence += 0.25
        if observations >= self.min_observations:
            evidence += 0.25

        return min(1.0, evidence)

    def contradiction_score(self, candidate, consolidated):
        content = candidate.get("content", "").lower()
        kind = candidate.get("kind", "").lower()
        contradictions = 0

        for memory in consolidated:
            if not memory.get("active", True):
                continue

            existing = memory.get("content", "").lower()
            existing_kind = memory.get("kind", "").lower()

            if content == existing:
                return 0.0

            if ("improve" in content and "reduce" in existing) or ("reduce" in content and "improve" in existing):
                contradictions += 1

            if ("robust" in content and "fragile" in existing) or ("fragile" in content and "robust" in existing):
                contradictions += 1

            if kind == "warning" and existing_kind == "heuristic":
                if "same prompt pattern" in content and "same prompt pattern" in existing:
                    contradictions += 1

        return min(1.0, 0.25 * contradictions)

    def memory_type_risk(self, candidate):
        kind = candidate.get("kind", "").lower()

        if kind == "warning":
            return 0.2
        if kind == "heuristic":
            return 0.35
        if kind == "claim":
            return 0.45
        if kind == "rule":
            return 0.7

        return 0.5

    def check(self, candidate, consolidated):
        provenance = self.provenance_score(candidate)
        inj_risk = self.injection_risk(candidate)
        contradiction = self.contradiction_score(candidate, consolidated)
        autonomy = self.autonomy_risk(candidate)
        evidence = self.evidence_score(candidate)
        type_risk = self.memory_type_risk(candidate)
        observations = candidate.get("observations", 1)

        diagnostics = {
            "provenance": provenance,
            "injection_risk": inj_risk,
            "contradiction": contradiction,
            "autonomy_risk": autonomy,
            "evidence": evidence,
            "type_risk": type_risk,
            "observations": observations,
        }

        if inj_risk > 0.0:
            return "RED", "injection_pattern_detected", diagnostics

        if autonomy > 0.0:
            return "RED", "autonomy_escalation_memory", diagnostics

        if contradiction >= MAX_MEMORY_CONTRADICTION:
            return "YELLOW", "possible_contradiction", diagnostics

        if provenance < MIN_MEMORY_PROVENANCE:
            return "YELLOW", "weak_provenance", diagnostics

        if evidence < MIN_MEMORY_EVIDENCE:
            return "YELLOW", "weak_evidence", diagnostics

        if observations < self.min_observations:
            return "YELLOW", "insufficient_repetition", diagnostics

        if type_risk >= MAX_MEMORY_TYPE_RISK_WITHOUT_STRONG_EVIDENCE and evidence < 0.75:
            return "YELLOW", "high_impact_memory_requires_more_evidence", diagnostics

        return "GREEN", "memory_admissible", diagnostics
