"""LRSI V11.0 runtime contract smoke suite."""

import json
import os
import tempfile

from pipeline.runner_core import PipelineExecution
from runner import main
from storage import verify_hash_chain
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


def test_review_mode_and_strict_audit():
    print("\n=== V11.0: Review mode + strict audit ===")
    with tempfile.TemporaryDirectory() as td:
        ex = PipelineExecution(
            iterations=0,
            storage_path=os.path.join(td, "run_log.json"),
            memory_path=os.path.join(td, "memory_store.json"),
            return_records=True,
        )
        ex.governance.mode = "review"
        ex.run_iteration(0)
        check("V11.0.1 review_mode_recorded", len(ex.all_records) == 1)
        check("V11.0.2 review_mode_hold", ex.all_records[0].get("final_decision") == "HOLD")
        ok, errors = verify_hash_chain(ex.all_records)
        check("V11.0.3 review_record_hash_valid", ok, errors)
        bad = [{"iteration": 99}]
        ok, errors = verify_hash_chain(bad)
        check("V11.0.4 missing_hash_rejected", not ok and errors, errors)


def test_runtime_records_hash_strict():
    print("\n=== V11.0: Runtime returned records strict hash ===")
    with tempfile.TemporaryDirectory() as td:
        records = main(
            iterations=2,
            storage_path=os.path.join(td, "run_log.json"),
            memory_path=os.path.join(td, "memory_store.json"),
            return_records=True,
        )
        stored = json.load(open(os.path.join(td, "run_log.json"), encoding="utf-8"))
        ok, errors = verify_hash_chain(records)
        check("V11.0.5 returned_hash_chain_valid", ok, errors)
        check("V11.0.6 returned_equals_stored", records == stored)
        stored[0]["accepted"] = not stored[0].get("accepted", False)
        ok, errors = verify_hash_chain(stored)
        check("V11.0.7 tamper_detected", not ok, errors)


def test_version():
    print("\n=== V11.0: Version ===")
    check("V11.0.8 schema_version", SCHEMA_VERSION in {"11.0", "11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "12.0"}, SCHEMA_VERSION)


if __name__ == "__main__":
    print("\nLRSI V11.0 RUNTIME CONTRACT TESTS")
    print("=" * 64)
    test_version()
    test_review_mode_and_strict_audit()
    test_runtime_records_hash_strict()
    print("\n" + "=" * 64)
    print(f"V11.0 RUNTIME CONTRACT TESTS: {passed} passed, {failed} failed")
    print("=" * 64)
    if failed:
        raise SystemExit(1)
    print("Alle V11.0-Runtime-Contract-Tests bestanden.")
