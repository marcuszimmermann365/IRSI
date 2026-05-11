"""
LRSI V10.5 — Audit-Consistency and Phase-Service Contract Tests

Script-style compatibility suite for the V10.5 iteration.
"""

import inspect
import json
import tempfile
from pathlib import Path

from pipeline.phase_services import (
    AuditRecorder,
    CouncilPhase,
    FinalGatePhase,
    HumanReviewPhase,
)
from pipeline.runner_core import PipelineExecution
from pipeline.stages import PersistenceStage
from runner import main
from storage import Storage, record_hash, verify_hash_chain
from version import SCHEMA_VERSION

passed = 0
failed = 0


def check(name, condition, detail=None):
    global passed, failed
    if condition:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}: {detail}")


def run():
    print("\n=== V10.5: Version contract ===")
    check("V10.5.1 schema_version_is_10_5", SCHEMA_VERSION in {"10.5", "10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.6", "12.0"}, SCHEMA_VERSION)

    print("\n=== V10.5: Persistence returns enriched audit record ===")
    with tempfile.TemporaryDirectory() as td:
        storage = Storage(str(Path(td) / "run_log.json"))
        persisted = PersistenceStage().run(storage=storage, record={"iteration": 1})
        check("V10.5.2_persistence_returns_record_hash", "record_hash" in persisted, persisted)
        check(
            "V10.5.3_persistence_hash_valid",
            persisted.get("record_hash") == record_hash(persisted),
            persisted,
        )

    print("\n=== V10.5: Returned records match persisted records ===")
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / "run_log.json"
        records = main(
            iterations=3,
            storage_path=str(log_path),
            memory_path=str(Path(td) / "memory_store.json"),
            return_records=True,
        )
        stored = json.loads(log_path.read_text())
        check("V10.5.4_returned_equals_stored", records == stored)
        ok, errors = verify_hash_chain(records)
        check("V10.5.5_returned_hash_chain_valid", ok, errors)
        has_audit_fields = all("record_hash" in r and "run_id" in r for r in records)
        check("V10.5.6_all_returned_records_have_audit_fields", has_audit_fields)

    print("\n=== V10.5: Phase-service decoupling ===")
    with tempfile.TemporaryDirectory() as td:
        execution = PipelineExecution(
            iterations=0,
            storage_path=str(Path(td) / "run_log.json"),
            memory_path=str(Path(td) / "memory_store.json"),
            return_records=True,
        )
        check("V10.5.7_council_phase_instance", isinstance(execution.council_phase, CouncilPhase))
        check(
            "V10.5.8_human_review_phase_instance",
            isinstance(execution.human_review_phase, HumanReviewPhase),
        )
        check(
            "V10.5.9_final_gate_phase_instance",
            isinstance(execution.final_gate_phase, FinalGatePhase),
        )
        check(
            "V10.5.10_audit_recorder_instance",
            isinstance(execution.audit_recorder, AuditRecorder),
        )

    print("\n=== V10.5: Runner delegates phase responsibilities ===")
    run_council_src = inspect.getsource(PipelineExecution.run_council)
    run_human_src = inspect.getsource(PipelineExecution.run_human_review)
    run_final_src = inspect.getsource(PipelineExecution.run_final_gate)
    check("V10.5.11_run_council_delegates", "self.council_phase.run" in run_council_src)
    check("V10.5.12_run_human_delegates", "self.human_review_phase.run" in run_human_src)
    check("V10.5.13_run_final_gate_delegates", "self.final_gate_phase.run" in run_final_src)

    print("\nLRSI V10.5 CONTRACT TESTS")
    print(f"V10.5 CONTRACT TESTS: {passed} passed, {failed} failed")
    if failed:
        raise SystemExit(1)
    print("Alle V10.5-Contract-Tests bestanden.")


if __name__ == "__main__":
    run()
