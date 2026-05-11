import ast
from pathlib import Path
from types import MappingProxyType

import pytest

from eventsourcing import AppendOnlyEventStore, RuntimeEvent
from pipeline.phase_contexts import ImmutablePhaseContext
from pipeline.runner_core import IterationContext

PHASE_MODULES = [
    Path("pipeline/phase_council.py"),
    Path("pipeline/phase_flow.py"),
    Path("pipeline/phase_safety.py"),
]


def _class_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef)]


def test_phase_services_is_facade_and_active_classes_are_not_duplicated():
    facade = Path("pipeline/phase_services.py")
    assert len(facade.read_text(encoding="utf-8").splitlines()) < 150

    active_runtime_classes = {
        "HumanReviewPhase",
        "FinalGatePhase",
        "AdversarialPhase",
        "PostRunReporter",
    }
    locations: dict[str, list[str]] = {name: [] for name in active_runtime_classes}
    for module in PHASE_MODULES:
        for name in _class_names(module):
            if name in locations:
                locations[name].append(str(module))

    assert locations == {
        "HumanReviewPhase": ["pipeline/phase_flow.py"],
        "FinalGatePhase": ["pipeline/phase_flow.py"],
        "AdversarialPhase": ["pipeline/phase_safety.py"],
        "PostRunReporter": ["pipeline/phase_flow.py"],
    }


def test_immutable_phase_context_exposes_read_only_snapshot_surface():
    ctx = IterationContext(iteration=7)
    ctx.trace_id = "trace-p1"
    ctx.final_decision = "GO"

    snapshot = ImmutablePhaseContext.from_iteration(ctx)

    assert snapshot.iteration == 7
    assert snapshot.trace_id == "trace-p1"
    assert isinstance(snapshot.values, MappingProxyType)
    assert snapshot.require("final_decision") == {"final_decision": "GO"}
    with pytest.raises(TypeError):
        snapshot.values["final_decision"] = "STOP"


def test_event_store_append_uses_cursor_not_full_stream_load(tmp_path):
    path = tmp_path / "events.jsonl"
    store = AppendOnlyEventStore(str(path))
    first = store.append(RuntimeEvent(event_type="test.one", payload={"n": 1}))
    assert first["sequence"] == 0
    assert Path(f"{path}.cursor.json").exists()

    def explode_load():  # pragma: no cover - executed only on regression
        raise AssertionError("append must not load the full event stream when cursor is present")

    store._load_unlocked = explode_load  # type: ignore[method-assign]
    second = store.append(RuntimeEvent(event_type="test.two", payload={"n": 2}))

    assert second["sequence"] == 1
    assert second["previous_event_hash"] == first["event_hash"]


def test_pipeline_execution_core_is_split_into_plan_and_helpers():
    runner_core = Path("pipeline/runner_core.py").read_text(encoding="utf-8")

    assert Path("pipeline/execution_plan.py").exists()
    assert Path("pipeline/runtime_helpers.py").exists()
    assert len(runner_core.splitlines()) < 1100
    assert "def build_phase_registry" not in runner_core
    assert "def build_attractor_state" not in runner_core
