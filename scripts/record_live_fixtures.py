#!/usr/bin/env python3
"""Record deterministic fixture files from live LLM runs.

This script intentionally does not run during CI.  It requires LLM_MODE=live
(or compatible OpenAI environment variables) and writes a JSON fixture that can
later be replayed with LLM_MODE=fixture.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_client import LLMClient
from tasks import get_base_tasks, get_long_horizon_tasks, get_shift_tasks, get_stress_tasks
from version import PROJECT_VERSION


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_prompts(limit: int | None = None) -> list[str]:
    tasks = get_base_tasks() + get_shift_tasks() + get_stress_tasks() + get_long_horizon_tasks()
    prompts = [t["input"] for t in tasks]
    return prompts[:limit] if limit else prompts


def main() -> int:
    parser = argparse.ArgumentParser(description="Record live LLM responses as replay fixtures.")
    parser.add_argument("--out", default="llm_fixtures/live_recorded.json")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if os.getenv("LLM_MODE", "").lower() != "live" and not os.getenv("USE_REAL_LLM"):
        raise SystemExit("Set LLM_MODE=live or USE_REAL_LLM=true before recording live fixtures.")

    client = LLMClient()
    entries = []
    for prompt in collect_prompts(args.limit):
        response = client.generate(prompt)
        entries.append({
            "prompt": prompt,
            "system_prompt": None,
            "response": response,
            "source_mode": client.backend_name,
            "recorded_at": utc_now_iso(),
        })

    payload = {
        "schema_version": PROJECT_VERSION,
        "source_type": "live_llm_recording",
        "recorded_at": utc_now_iso(),
        "entries": entries,
        "default_response": "__LLM_FIXTURE_MISS__: no matching live-recorded fixture response",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(entries)} live fixture entries to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
