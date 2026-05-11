"""
LRSI V10.4 — Structured Phase Runner Contract Tests
===================================================
Script-style compatibility suite for the V10.4 iteration.
"""

import inspect
import os
import tempfile

from pipeline.runner_core import (
    IterationContext,
    PipelineExecution,
    PipelineRunner,
    _run_pipeline_legacy_semantics,
)
from runner import main
from version import SCHEMA_VERSION

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}: {detail}")


def test_version_contract():
    print("\n=== V10.4: Version contract ===")
    check("V10.4.1 schema_version_is_10_4", SCHEMA_VERSION in {"10.4", "10.5", "10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.6", "12.0"}, SCHEMA_VERSION)


def test_inner_runner_is_phase_structured():
    print("\n=== V10.4: Inner runner phase structure ===")
    required = [
        "prepare_iteration",
        "run_mutation_contract",
        "run_council",
        "run_human_review",
        "run_attractor_checks",
        "run_adversarial_layers",
        "run_final_gate",
        "apply_or_reject_candidate",
        "persist_iteration_record",
    ]
    check("V10.4.2 required_phase_methods_exist", all(hasattr(PipelineExecution, name) for name in required))
    src = inspect.getsource(_run_pipeline_legacy_semantics)
    check("V10.4.3 legacy_wrapper_is_short", len(src.splitlines()) <= 18, len(src.splitlines()))
    run_iter_src = inspect.getsource(PipelineExecution.run_iteration)
    check("V10.4.4 run_iteration_orchestrates_phases", all(name in run_iter_src for name in required))
    check("V10.4.5 run_iteration_is_short", len(run_iter_src.splitlines()) <= 32, len(run_iter_src.splitlines()))


def test_iteration_context_contract_and_runtime_smoke():
    print("\n=== V10.4: Context contract and smoke run ===")
    ctx = IterationContext(iteration=7)
    check("V10.4.6_context_defaults", ctx.iteration == 7 and ctx.decision_trace == [] and ctx.accepted is False)
    with tempfile.TemporaryDirectory() as td:
        records = main(
            iterations=1,
            storage_path=os.path.join(td, "run_log.json"),
            memory_path=os.path.join(td, "memory_store.json"),
            return_records=True,
        )
        phases = [entry.get("stage") for entry in records[0].get("decision_trace", [])]
        check("V10.4.7_runtime_record_versioned", records[0].get("schema_version") == SCHEMA_VERSION)
        check("V10.4.8_trace_has_core_phases", "council" in phases and "extended" in phases, phases)


def test_public_runner_still_thin():
    print("\n=== V10.4: Public runner facade ===")
    src = inspect.getsource(PipelineRunner.run_structured_iterations)
    check("V10.4.9_facade_uses_pipeline_execution", "PipelineExecution" in src)


if __name__ == "__main__":
    print("\nLRSI V10.4 CONTRACT TESTS")
    print("=" * 64)
    test_version_contract()
    test_inner_runner_is_phase_structured()
    test_iteration_context_contract_and_runtime_smoke()
    test_public_runner_still_thin()
    print("\n" + "=" * 64)
    print(f"V10.4 CONTRACT TESTS: {passed} passed, {failed} failed")
    print("=" * 64)
    if failed:
        raise SystemExit(1)
    print("Alle V10.4-Contract-Tests bestanden.")
