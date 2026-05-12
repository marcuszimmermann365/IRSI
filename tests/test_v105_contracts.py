import inspect
import json

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


def test_version_single_source_of_truth_v105():
    assert SCHEMA_VERSION in {"10.5", "10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "12.0", "12.1.0", "12.2.0", "13.0.0", "13.2.0"}


def test_persistence_stage_returns_enriched_storage_record(tmp_path):
    storage = Storage(str(tmp_path / "run_log.json"))
    persisted = PersistenceStage().run(storage=storage, record={"iteration": 1})
    assert persisted["schema_version"] == SCHEMA_VERSION
    assert persisted["audit_event_type"] == "iteration_record"
    assert persisted["previous_record_hash"] == "0" * 64
    assert persisted["record_hash"] == record_hash(persisted)


def test_returned_records_are_the_persisted_audit_records(tmp_path):
    log_path = tmp_path / "run_log.json"
    records = main(
        iterations=3,
        storage_path=str(log_path),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    stored = json.loads(log_path.read_text())
    assert records == stored
    assert all("record_hash" in rec for rec in records)
    assert all("previous_record_hash" in rec for rec in records)
    ok, errors = verify_hash_chain(records)
    assert ok, errors


def test_pipeline_execution_owns_phase_service_instances(tmp_path):
    execution = PipelineExecution(
        iterations=0,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    assert isinstance(execution.council_phase, CouncilPhase)
    assert isinstance(execution.human_review_phase, HumanReviewPhase)
    assert isinstance(execution.final_gate_phase, FinalGatePhase)
    assert isinstance(execution.audit_recorder, AuditRecorder)


def test_runner_phase_methods_delegate_to_service_classes():
    assert "self.council_phase.run" in inspect.getsource(PipelineExecution.run_council)
    assert "self.human_review_phase.run" in inspect.getsource(PipelineExecution.run_human_review)
    assert "self.final_gate_phase.run" in inspect.getsource(PipelineExecution.run_final_gate)


def test_phase_service_methods_are_small_enough_to_review():
    assert len(inspect.getsource(PipelineExecution.run_council).splitlines()) <= 46
    assert len(inspect.getsource(PipelineExecution.run_human_review).splitlines()) <= 30
    assert len(inspect.getsource(PipelineExecution.run_final_gate).splitlines()) <= 60
