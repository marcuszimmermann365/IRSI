#!/usr/bin/env python3
"""Executable V10.6 contract checks."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent import Agent
from eval import evaluate
from pipeline.phase_services import AdversarialPhase, MemoryConsolidationPhase, PostRunReporter
from runner import main
from storage import AppendOnlyAuditBackend, Storage, verify_hash_chain
from version import SCHEMA_VERSION

passed = 0
failed = 0
errors = []


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")
        errors.append(name)


class NonDeepcopyableClient:
    def __init__(self, response="4"):
        self.calls = 0
        self.response = response

    def __deepcopy__(self, memo):
        raise AssertionError("client copied")

    def generate(self, prompt, system_prompt=None):
        self.calls += 1
        return self.response


print("=" * 64)
print("LRSI V10.6 Contract Tests")
print("=" * 64)

check("schema_version_10_6", SCHEMA_VERSION in {"10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.6", "12.0"})
check("phase_services_present", all(
    hasattr(obj, "name") for obj in [AdversarialPhase(), MemoryConsolidationPhase(), PostRunReporter()]
))

client = NonDeepcopyableClient("4")
metrics = evaluate(Agent("base", llm_client=client))
check("agent_llm_injection_no_deepcopy", client.calls > 0 and metrics["llm_error_count"] == 0)

err_metrics = evaluate(Agent("base", llm_client=NonDeepcopyableClient("__LLM_ERROR__: outage")))
check("llm_error_metric_present", err_metrics["llm_error_count"] > 0 and err_metrics["llm_error_rate"] > 0)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    records = main(
        iterations=1,
        storage_path=str(td / "run_log.json"),
        memory_path=str(td / "memory_store.json"),
        return_records=True,
        llm_client=NonDeepcopyableClient("4"),
    )
    check("runner_accepts_injected_client", bool(records))

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    storage = Storage(backend=AppendOnlyAuditBackend(
        path=str(td / "run_log.jsonl"),
        materialized_json_path=str(td / "run_log.json"),
    ))
    storage.log_iteration({"iteration": 0})
    storage.log_iteration({"iteration": 1})
    data = json.loads((td / "run_log.json").read_text())
    ok, errs = verify_hash_chain(data)
    check("append_only_hash_chain", ok, errs)
    check("append_only_two_lines", (td / "run_log.jsonl").read_text().count("\n") == 2)

result = subprocess.run(
    [sys.executable, "scripts/record_live_fixtures.py", "--limit", "1"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    timeout=30,
)
check("live_fixture_recorder_refuses_without_live_mode", result.returncode != 0 and "LLM_MODE=live" in result.stdout)
check("live_fixture_readme_present", Path("llm_fixtures/LIVE_FIXTURE_README.md").exists())

print("=" * 64)
print(f"V10.6 TESTS: {passed} passed, {failed} failed")
print("=" * 64)
if failed:
    print("FAILURES:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
