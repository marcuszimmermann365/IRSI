import inspect

import runner
from pipeline.phase_runtime import ContextRegistry, MethodPhaseAdapter, PhaseExecutor, PhaseResult
from pipeline.phase_services import CouncilPhase, CouncilPhaseInput
from pipeline.runner_core import PipelineExecution
from version import SCHEMA_VERSION


def test_schema_version_v112():
    assert SCHEMA_VERSION in {"11.2", "11.3", "11.4", "11.5", "11.6", "12.0", "12.1.0", "12.2.0", "13.0.0"}


def test_phase_result_generates_audit_entry_without_business_logic():
    result = PhaseResult(
        phase="demo",
        decision="GREEN",
        reason="ok",
        diagnostics={"x": 1},
        patch={"foo": "bar"},
    )
    audit = result.audit_entry(iteration=7)
    assert audit["audit_event_type"] == "phase_result"
    assert audit["phase"] == "demo"
    assert audit["patch_keys"] == ["foo"]
    assert audit["schema_version"] == SCHEMA_VERSION


def test_council_phase_declares_explicit_inputs():
    phase = CouncilPhase()
    assert phase.input_type is CouncilPhaseInput
    for key in ["parent_metrics", "child_metrics", "agent", "candidate", "council"]:
        assert key in phase.required_keys


def test_runner_uses_declarative_phase_list():
    src = inspect.getsource(PipelineExecution.run_iteration)
    assert "for phase in self._build_iteration_phases()" in src
    assert "self.phase_executor.execute" in src


def test_phase_executor_merges_patch_explicitly():
    class Obj:
        iteration = 3
        phase_audit = []

    def set_value(ctx):
        # Compatibility adapter may still call legacy methods, but merge/audit are centralized.
        return True

    adapter = MethodPhaseAdapter(name="legacy", method=set_value)
    registry = ContextRegistry({"ctx": Obj()})
    executor = PhaseExecutor()
    new_registry, result = executor.execute(adapter, registry, ctx=registry.get("ctx"))
    assert result.phase == "legacy"
    assert new_registry.get("ctx") is registry.get("ctx")
    assert registry.get("ctx").phase_audit[0]["phase"] == "legacy"


def test_returned_records_contain_phase_audit_and_hash_chain(tmp_path):
    records = runner.main(
        iterations=1,
        return_records=True,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
    )
    record = records[0]
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["record_hash"]
    assert record["previous_record_hash"]
    phases = [entry["phase"] for entry in record["phase_audit"]]
    assert "council_phase" in phases
    assert "final_gate" in phases
