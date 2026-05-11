#!/usr/bin/env python3
"""Create a V11.1 Merkle seal for an LRSI audit log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from audit_sinks import LocalWORMDirectorySink
from storage import Storage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="run_log.json")
    parser.add_argument("--sequence-id", required=True)
    parser.add_argument("--worm-dir", default=None)
    parser.add_argument("--backend", default=None, choices=[None, "json", "append-only", "jsonl"])
    args = parser.parse_args()
    sink = LocalWORMDirectorySink(args.worm_dir) if args.worm_dir else None
    seal = Storage(args.log, backend_mode=args.backend).seal_sequence(
        external_sink=sink,
        sequence_id=args.sequence_id,
    )
    print(json.dumps(seal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
