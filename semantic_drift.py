"""LRSI V11.1 — Local semantic drift monitor.

The default implementation is deterministic and dependency-free: it compares
character n-gram vectors.  Production deployments can replace ``embedder`` with
an external embedding service while preserving the same monitor contract.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class SemanticDriftResult:
    distance: float
    similarity: float
    decision: str
    baseline_len: int
    candidate_len: int

    def to_dict(self) -> dict:
        return asdict(self)


def _ngram_embedding(text: str, n: int = 3) -> dict[str, float]:
    text = f"  {text.lower()}  "
    grams = [text[i:i + n] for i in range(max(1, len(text) - n + 1))]
    counts = Counter(grams)
    norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
    return {k: v / norm for k, v in counts.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) & set(b)
    return sum(a[k] * b[k] for k in keys)


class SemanticDriftMonitor:
    def __init__(self, *, yellow_threshold: float = 0.18, red_threshold: float = 0.32,
                 embedder: Callable[[str], dict[str, float]] | None = None):
        self.yellow_threshold = yellow_threshold
        self.red_threshold = red_threshold
        self.embedder = embedder or _ngram_embedding

    def compare(self, baseline_prompt: str, candidate_prompt: str) -> SemanticDriftResult:
        if baseline_prompt == candidate_prompt:
            similarity = 1.0
            distance = 0.0
        else:
            similarity = max(0.0, min(1.0, _cosine(self.embedder(baseline_prompt), self.embedder(candidate_prompt))))
            distance = 1.0 - similarity
        if distance >= self.red_threshold:
            decision = "RED"
        elif distance >= self.yellow_threshold:
            decision = "YELLOW"
        else:
            decision = "GREEN"
        return SemanticDriftResult(
            distance=distance,
            similarity=similarity,
            decision=decision,
            baseline_len=len(baseline_prompt),
            candidate_len=len(candidate_prompt),
        )
