import inspect

import runner
from pipeline.runner_core import PipelineExecution
from pipeline.runtime_operations_phases import (
    EvaluationPhase,
    EvaluationPhaseInput,
    MemoryConsolidationPhase,
    MemoryConsolidationPhaseInput,
    ObservabilityPhase,
    ObservabilityPhaseInput,
)
from storage import verify_hash_chain
from version import SCHEMA_VERSION


def _phase_names(record):
    return [entry.get("phase") for entry in record.get("phase_audit", [])]


def test_schema_version_v116():
    assert SCHEMA_VERSION in {"11.6", "12.0", "12.1.0", "12.2.0", "13.0.0", "13.2.0"}


def test_runtime_operation_phases_expose_explicit_contracts():
    phases = [
        (EvaluationPhase(), EvaluationPhaseInput),
        (MemoryConsolidationPhase(), MemoryConsolidationPhaseInput),
        (ObservabilityPhase(), ObservabilityPhaseInput),
    ]
    for phase, input_type in phases:
        assert phase.name
        assert phase.input_type is input_type
        assert isinstance(phase.required_keys, tuple)
        assert phase.required_keys
        assert hasattr(phase, "build_input")
        assert hasattr(phase, "run")


def test_runner_audits_runtime_operations_and_propagates_trace_id(tmp_path):
    records = runner.main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    assert len(records) == 1
    record = records[0]
    trace_id = record.get("trace_id")
    assert trace_id and trace_id.startswith("lrsi-")
    phases = _phase_names(record)
    assert "evaluation_phase" in phases
    assert "memory_consolidation_phase" in phases
    assert "observability_phase" in phases
    for entry in record["phase_audit"]:
        assert entry.get("trace_id") == trace_id
    runtime = record["runtime_operations_v11_6"]
    assert set(runtime) == {"evaluation", "memory_consolidation", "observability", "runtime_events"}
    assert runtime["evaluation"]["llm_error_rate"] >= 0.0
    assert runtime["memory_consolidation"]["extracted_count"] >= 0
    assert runtime["observability"]["trace_id"] == trace_id
    assert runtime["runtime_events"][0]["trace_id"] == trace_id
    assert verify_hash_chain(records)[0]


def test_memory_consolidation_is_no_longer_hidden_inside_apply_candidate():
    src = inspect.getsource(PipelineExecution.apply_or_reject_candidate)
    assert "consolidate_memory" not in src
    assert "memory_events" not in src


def test_observability_spans_cover_prior_phase_audit(tmp_path):
    records = runner.main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    record = records[0]
    observability = record["runtime_operations_v11_6"]["observability"]
    span_phases = [span["phase"] for span in observability["spans"]]
    assert "evaluation_phase" in span_phases
    assert "memory_consolidation_phase" in span_phases
    # The observability phase reports spans over the audit entries that existed
    # before its own audit entry was appended.
    assert "observability_phase" not in span_phases
