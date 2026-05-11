#!/usr/bin/env python3
"""Analyze V11.1 shadow calibration JSONL output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibration import ShadowCalibrationRecorder, ThresholdBacktester, ThresholdCalibrationAnalyzer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("shadow_path")
    parser.add_argument("--threshold-registry", default="runtime_config/threshold_registry.json")
    args = parser.parse_args()
    records = ShadowCalibrationRecorder(args.shadow_path).load()
    registry = json.loads(Path(args.threshold_registry).read_text(encoding="utf-8"))
    payload = {
        "shadow_summary": ThresholdCalibrationAnalyzer.analyze(records),
        "backtest": ThresholdBacktester(registry).run(records),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
