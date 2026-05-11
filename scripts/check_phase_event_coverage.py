#!/usr/bin/env python3
"""CI check: every phase_audit phase_result must exist in the V12 event stream."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eventsourcing import validate_phase_audit_event_coverage
from runner import main as run_pipeline


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"audit log not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"audit log must be a JSON list: {path}")
    return data


def _load_events(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"event stream not found: {path}")
    events: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid event JSONL at line {line_no}: {exc.msg}") from exc
    return events


def _sample(iterations: int) -> tuple[list[dict], list[dict]]:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        log = root / "run_log.json"
        records = run_pipeline(
            iterations=iterations,
            storage_path=str(log),
            memory_path=str(root / "memory_store.json"),
            return_records=True,
            verbose=False,
        )
        return records, _load_events(Path(f"{log}.events.jsonl"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="run_log.json")
    parser.add_argument("--events", default=None)
    parser.add_argument("--run-sample", action="store_true", help="run a deterministic pipeline sample before checking")
    parser.add_argument("--iterations", type=int, default=3, help="sample iteration count; 3 covers the DGM terminal reject path")
    args = parser.parse_args()

    try:
        if args.run_sample:
            records, events = _sample(args.iterations)
            label = f"sample({args.iterations})"
        else:
            log_path = Path(args.log)
            events_path = Path(args.events) if args.events else Path(f"{args.log}.events.jsonl")
            records = _load_records(log_path)
            events = _load_events(events_path)
            label = f"{log_path} ↔ {events_path}"
        ok, errors = validate_phase_audit_event_coverage(records, events)
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"phase_audit/phase.result coverage check failed to run: {exc}", file=sys.stderr)
        return 2

    if not ok:
        print("phase_audit/phase.result coverage failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"phase_audit/phase.result coverage ok: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
