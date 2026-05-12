import inspect
import json

import dgm_bridge
import runner
from pipeline.runner_core import PipelineRunner
from pipeline_contracts import DGMRequirements
from storage import Storage, verify_hash_chain
from version import SCHEMA_VERSION


def test_version_single_source_of_truth_v103():
    assert SCHEMA_VERSION in {"10.3", "10.4", "10.5", "10.6", "11.0", "11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "12.0", "12.1.0", "12.2.0", "13.0.0", "13.2.0"}


def test_runner_main_is_thin_structured_entrypoint():
    src = inspect.getsource(runner.main)
    assert "PipelineRunner" in src
    assert "runner.run()" in src
    assert len(src.splitlines()) <= 18


def test_pipeline_runner_exposes_named_lifecycle_phases():
    for name in ["prepare_iteration_runtime", "run_structured_iterations", "finish", "run"]:
        assert hasattr(PipelineRunner, name)


def test_storage_records_are_hash_chained(tmp_path):
    path = tmp_path / "run_log.json"
    storage = Storage(str(path))
    first = storage.log_iteration({"iteration": 0, "final_decision": "HOLD"})
    second = storage.log_iteration({"iteration": 1, "final_decision": "GO"})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["record_hash"] == first["record_hash"]
    assert data[1]["previous_record_hash"] == data[0]["record_hash"]
    assert data[1]["record_hash"] == second["record_hash"]
    ok, errors = verify_hash_chain(data)
    assert ok, errors


def test_hash_chain_detects_tampering(tmp_path):
    path = tmp_path / "run_log.json"
    storage = Storage(str(path))
    storage.log_iteration({"iteration": 0, "final_decision": "HOLD"})
    data = json.loads(path.read_text(encoding="utf-8"))
    data[0]["final_decision"] = "GO"
    ok, errors = verify_hash_chain(data)
    assert not ok
    assert any("record_hash" in err for err in errors)


def test_dgm_requirements_are_typed_and_normalized():
    reqs = DGMRequirements.from_dict({
        "requires_human_review": 1,
        "min_evaluators": "4",
        "bewaehrung_cycles": "3",
        "rollback_window_hours": "48",
        "target_layer": "governance",
    })
    assert reqs.requires_human_review is True
    assert reqs.min_evaluators == 4
    assert reqs.bewaehrung_cycles == 3
    assert reqs.rollback_window_hours == 48
    assert reqs.target_layer == "governance"


def test_dgm_bridge_has_no_sys_path_mutation():
    src = inspect.getsource(dgm_bridge)
    assert "sys.path.insert" not in src
