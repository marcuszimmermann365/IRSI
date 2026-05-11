"""
LRSI V10.2 — Decomposition and Operability Contract Tests
=========================================================
Executable script-style tests retained for compatibility with the existing
stress-test style. Pytest wrappers also run these checks in CI.
"""

import json
import os
import tempfile
from pathlib import Path

from human_override import DecisionClass, HumanAction, HumanOverrideLayer
from llm_client import LLMClient
from memory import MemoryStore
from pipeline.stages import (
    A3Stage,
    A4Stage,
    AttractorStage,
    DRELStage,
    EvaluationStage,
    ExtendedGateStage,
    PersistenceStage,
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
    print("\n=== V10.2: Version contract ===")
    check("V10.2.1 schema_version_is_10_2", SCHEMA_VERSION == SCHEMA_VERSION, SCHEMA_VERSION)


def test_new_stage_classes_exist():
    print("\n=== V10.2: Additional stage seams ===")
    stages = [
        EvaluationStage(), AttractorStage(), DRELStage(), A3Stage(), A4Stage(),
        ExtendedGateStage(), PersistenceStage(),
    ]
    check("V10.2.2 stage_names", [s.name for s in stages] == [
        "evaluation", "attractor", "drel", "a3", "a4", "extended", "persistence",
    ])


def test_runtime_records_are_versioned_in_memory():
    print("\n=== V10.2: Runtime record schema ===")
    with tempfile.TemporaryDirectory() as td:
        records = main(
            iterations=1,
            storage_path=os.path.join(td, "run_log.json"),
            memory_path=os.path.join(td, "memory_store.json"),
            return_records=True,
        )
        check("V10.2.3 return_record_versioned", records[0].get("schema_version") == SCHEMA_VERSION)
        with open(os.path.join(td, "run_log.json"), "r", encoding="utf-8") as f:
            persisted = json.load(f)
        check("V10.2.4 persisted_record_versioned", persisted[0].get("schema_version") == SCHEMA_VERSION)


def test_human_override_hard_classes_block_approval():
    print("\n=== V10.2: Human override classes ===")
    ho = HumanOverrideLayer(policy_fn=HumanOverrideLayer.permissive_simulation_policy)
    d, a, applied = ho.override(
        "RED", HumanAction.APPROVE, False,
        decision_class=DecisionClass.HARD_RED,
    )
    check("V10.2.5 hard_red_approve_blocked", d == "RED" and a is False and applied is False)
    d, a, applied = ho.override(
        "RED", HumanAction.APPROVE, False,
        decision_class=DecisionClass.SOFT_RED,
    )
    check("V10.2.6 soft_red_approve_allowed", d == "GREEN" and a is True and applied is True)
    klass = ho.classify_decision_class(
        council_decision="RED",
        trigger_reasons=["truth_sensitivity_alarm"],
    )
    check("V10.2.7 truth_alarm_is_hard", klass == DecisionClass.HARD_RED.value)


def test_fixture_mode_resolves_without_cwd_dependency():
    print("\n=== V10.2: Fixture path independence ===")
    old_mode = os.environ.get("LLM_MODE")
    old_path = os.environ.get("LLM_FIXTURE_PATH")
    old_cwd = os.getcwd()
    try:
        os.environ["LLM_MODE"] = "fixture"
        os.environ.pop("LLM_FIXTURE_PATH", None)
        os.chdir(tempfile.gettempdir())
        client = LLMClient()
        check("V10.2.8 fixture_backend", client.backend_name == "fixture")
        check("V10.2.9 fixture_answer", client.generate("what is 2+2") == "4")
    finally:
        os.chdir(old_cwd)
        if old_mode is None:
            os.environ.pop("LLM_MODE", None)
        else:
            os.environ["LLM_MODE"] = old_mode
        if old_path is None:
            os.environ.pop("LLM_FIXTURE_PATH", None)
        else:
            os.environ["LLM_FIXTURE_PATH"] = old_path


def test_memory_locked_read_modify_write_preserves_external_update():
    print("\n=== V10.2: Memory read-modify-write lock ===")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "memory_store.json")
        stale = MemoryStore(path)
        fresh = MemoryStore(path)
        fresh.add_candidate("external update", "test", "heuristic")
        stale.add_candidate("stale writer update", "test", "heuristic")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        contents = {entry["content"] for entry in data["candidate"]}
        check("V10.2.10 no_lost_memory_update", contents == {"external update", "stale writer update"}, contents)


if __name__ == "__main__":
    print("\nLRSI V10.2 CONTRACT TESTS")
    print("=" * 64)
    test_version_contract()
    test_new_stage_classes_exist()
    test_runtime_records_are_versioned_in_memory()
    test_human_override_hard_classes_block_approval()
    test_fixture_mode_resolves_without_cwd_dependency()
    test_memory_locked_read_modify_write_preserves_external_update()
    print("\n" + "=" * 64)
    print(f"V10.2 CONTRACT TESTS: {passed} passed, {failed} failed")
    print("=" * 64)
    if failed:
        raise SystemExit(1)
    print("Alle V10.2-Contract-Tests bestanden.")
