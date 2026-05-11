import inspect

from pipeline.runner_core import (
    IterationContext,
    PipelineExecution,
    PipelineRunner,
    _run_pipeline_legacy_semantics,
)
from runner import main
from version import SCHEMA_VERSION


def test_version_single_source_of_truth_v104():
    assert SCHEMA_VERSION in {"10.4", "10.5", "10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "12.0", "12.1.0", "12.2.0", "13.0.0"}


def test_inner_runner_exposes_required_phase_methods():
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
    assert all(hasattr(PipelineExecution, name) for name in required)


def test_legacy_semantics_wrapper_is_thin():
    src = inspect.getsource(_run_pipeline_legacy_semantics)
    assert "PipelineExecution" in src
    assert len(src.splitlines()) <= 18


def test_run_iteration_is_phase_orchestrator():
    src = inspect.getsource(PipelineExecution.run_iteration)
    for name in [
        "prepare_iteration",
        "run_mutation_contract",
        "run_council",
        "run_human_review",
        "run_attractor_checks",
        "run_adversarial_layers",
        "run_final_gate",
        "apply_or_reject_candidate",
        "persist_iteration_record",
    ]:
        assert name in src
    assert len(src.splitlines()) <= 32


def test_iteration_context_defaults_are_safe():
    ctx = IterationContext(iteration=3)
    assert ctx.iteration == 3
    assert ctx.decision_trace == []
    assert ctx.accepted is False


def test_v104_smoke_preserves_runtime_record_contract(tmp_path):
    records = main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    assert records[0]["schema_version"] == SCHEMA_VERSION
    phases = [entry.get("stage") for entry in records[0].get("decision_trace", [])]
    assert "council" in phases
    assert "extended" in phases


def test_pipeline_runner_facade_uses_pipeline_execution():
    src = inspect.getsource(PipelineRunner.run_structured_iterations)
    assert "PipelineExecution" in src
