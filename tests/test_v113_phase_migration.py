import runner
from pipeline.phase_runtime import PhaseResult
from pipeline.phase_services import (
    FinalGatePhase,
    FinalGatePhaseInput,
    HoldLogicPhase,
    HoldLogicPhaseInput,
    HumanReviewPhase,
    HumanReviewPhaseInput,
    PersistencePhase,
    PersistencePhaseInput,
    PostRunReporter,
    PostRunReporterInput,
)
from version import SCHEMA_VERSION


def test_schema_version_v113():
    assert SCHEMA_VERSION in {"11.3", "11.4", "11.5", "11.6", "12.0", "12.1.0", "12.2.0", "13.0.0", "13.2.0"}


def test_safe_phases_declare_explicit_inputs():
    phases = [
        (HoldLogicPhase(), HoldLogicPhaseInput),
        (HumanReviewPhase(), HumanReviewPhaseInput),
        (FinalGatePhase(), FinalGatePhaseInput),
        (PersistencePhase(), PersistencePhaseInput),
        (PostRunReporter(), PostRunReporterInput),
    ]
    for phase, input_type in phases:
        assert phase.input_type is input_type
        assert phase.required_keys


def test_runner_audits_v113_migrated_safe_phases(tmp_path):
    records = runner.main(
        iterations=1,
        return_records=True,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
    )
    phases = [entry["phase"] for entry in records[0]["phase_audit"]]
    for name in ["hold_logic", "human_review", "final_gate", "persist_iteration_record"]:
        assert name in phases
    assert records[0]["schema_version"] == SCHEMA_VERSION
    assert records[0]["record_hash"]


def test_phase_result_supports_hash_protected_persistence_audit_marker():
    result = PhaseResult(
        phase="persist_iteration_record",
        decision="PERSISTED",
        audit_already_in_patch=True,
    )
    assert result.audit_already_in_patch is True
    assert result.audit_entry(iteration=1)["phase"] == "persist_iteration_record"
