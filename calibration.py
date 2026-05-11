"""LRSI V11.1 — Shadow-mode threshold calibration helpers."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ShadowDecision:
    run_id: str
    iteration: int
    gate_decision: str
    final_decision: str
    human_decision: str
    later_outcome: str | None = None
    thresholds: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class ShadowCalibrationRecorder:
    """Append shadow-mode system/human decisions to a JSONL corpus."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, decision: ShadowDecision) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict(), sort_keys=True) + "\n")

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    phat = successes / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


class ThresholdCalibrationAnalyzer:
    """Compute simple false-positive/false-negative summaries from shadow data."""

    @staticmethod
    def analyze(records: list[dict]) -> dict:
        total = len(records)
        false_positive = 0  # system held/stopped, human later marked successful/acceptable
        false_negative = 0  # system allowed GO, later drift/failure was observed
        for rec in records:
            final_decision = rec.get("final_decision")
            human = rec.get("human_decision")
            later = rec.get("later_outcome")
            if final_decision in {"HOLD", "STOP", "ROLLBACK", "RED"} and human in {"approve", "acceptable", "go"}:
                false_positive += 1
            if final_decision == "GO" and later in {"drift", "failure", "unsafe", "regression"}:
                false_negative += 1
        fp_low, fp_high = _wilson_interval(false_positive, total)
        fn_low, fn_high = _wilson_interval(false_negative, total)
        return {
            "total": total,
            "false_positive_count": false_positive,
            "false_negative_count": false_negative,
            "false_positive_rate": false_positive / total if total else 0.0,
            "false_negative_rate": false_negative / total if total else 0.0,
            "false_positive_ci95": [fp_low, fp_high],
            "false_negative_ci95": [fn_low, fn_high],
        }


class ThresholdBacktester:
    """Small automated regression harness for historical audit records.

    V11.1 intentionally records the contract; production deployments can replace
    the evaluator with domain-specific replay logic over 100+ historic runs.
    """

    def __init__(self, registry: dict):
        self.registry = registry

    def run(self, records: list[dict]) -> dict:
        threshold_ids = [t.get("threshold_id") for t in self.registry.get("thresholds", [])]
        blocked = sum(1 for r in records if r.get("final_decision") in {"HOLD", "STOP", "ROLLBACK"})
        go = sum(1 for r in records if r.get("final_decision") == "GO")
        return {
            "schema": "lrsi.threshold_backtest.v1",
            "record_count": len(records),
            "threshold_ids": threshold_ids,
            "go_count": go,
            "blocked_count": blocked,
            "blocked_rate": blocked / len(records) if records else 0.0,
            "status": "insufficient_history" if len(records) < 100 else "history_window_ready",
        }
