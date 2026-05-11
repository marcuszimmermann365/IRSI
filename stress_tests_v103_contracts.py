"""
LRSI V10.3 — Structured Runner and Audit Contract Tests
=======================================================
Script-style compatibility suite for the V10.3 iteration.
"""

import inspect
import json
import os
import tempfile

import dgm_bridge
import runner
from pipeline.runner_core import PipelineRunner
from pipeline_contracts import DGMRequirements
from storage import Storage, verify_hash_chain
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
    print("\n=== V10.3: Version contract ===")
    check("V10.3.1 schema_version_is_10_3_or_newer", SCHEMA_VERSION in {"10.3", "10.4", "10.5", "10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.6", "12.0"}, SCHEMA_VERSION)


def test_runner_main_is_thin():
    print("\n=== V10.3: Structured main() ===")
    src = inspect.getsource(runner.main)
    check("V10.3.2 main_delegates_to_pipeline_runner", "PipelineRunner" in src and "runner.run()" in src)
    check("V10.3.3 main_is_short", len(src.splitlines()) <= 18, len(src.splitlines()))
    phases = ["prepare_iteration_runtime", "run_structured_iterations", "finish", "run"]
    check("V10.3.4 pipeline_runner_phases_exist", all(hasattr(PipelineRunner, p) for p in phases))


def test_storage_hash_chain():
    print("\n=== V10.3: Audit hash chain ===")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "run_log.json")
        storage = Storage(path)
        first = storage.log_iteration({"iteration": 0, "final_decision": "HOLD"})
        second = storage.log_iteration({"iteration": 1, "final_decision": "GO"})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ok, errors = verify_hash_chain(data)
        check("V10.3.5 hash_chain_valid", ok, errors)
        check("V10.3.6 second_points_to_first", data[1]["previous_record_hash"] == data[0]["record_hash"])
        check("V10.3.7 returned_hashes_match_file", first["record_hash"] == data[0]["record_hash"] and second["record_hash"] == data[1]["record_hash"])
        data[0]["final_decision"] = "GO"
        ok, errors = verify_hash_chain(data)
        check("V10.3.8 tamper_detected", not ok and any("record_hash" in e for e in errors), errors)


def test_typed_contracts_and_import_hygiene():
    print("\n=== V10.3: Typed contracts/import hygiene ===")
    reqs = DGMRequirements.from_dict({
        "requires_human_review": 1,
        "min_evaluators": "4",
        "bewaehrung_cycles": "3",
        "rollback_window_hours": "48",
        "target_layer": "governance",
    })
    check("V10.3.9 dgm_requirements_normalized", reqs.min_evaluators == 4 and reqs.requires_human_review is True)
    src = inspect.getsource(dgm_bridge)
    check("V10.3.10 no_sys_path_insert", "sys.path.insert" not in src)


if __name__ == "__main__":
    print("\nLRSI V10.3 CONTRACT TESTS")
    print("=" * 64)
    test_version_contract()
    test_runner_main_is_thin()
    test_storage_hash_chain()
    test_typed_contracts_and_import_hygiene()
    print("\n" + "=" * 64)
    print(f"V10.3 CONTRACT TESTS: {passed} passed, {failed} failed")
    print("=" * 64)
    if failed:
        raise SystemExit(1)
    print("Alle V10.3-Contract-Tests bestanden.")
