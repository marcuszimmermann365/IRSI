import json
import os

from human_override import DecisionClass, HumanAction, HumanOverrideLayer
from llm_client import LLMClient
from memory import MemoryStore
from pipeline.stages import (
    A3Stage,
    A4Stage,
    AttractorStage,
    DRELStage,
    EvaluationStage,
    ExtendedGateStage,
    PersistenceStage,
)
from runner import main
from version import SCHEMA_VERSION


def test_version_single_source_of_truth_v102():
    assert SCHEMA_VERSION == SCHEMA_VERSION


def test_additional_stage_classes_are_importable_contract_seams():
    assert EvaluationStage().name == "evaluation"
    assert AttractorStage().name == "attractor"
    assert DRELStage().name == "drel"
    assert A3Stage().name == "a3"
    assert A4Stage().name == "a4"
    assert ExtendedGateStage().name == "extended"
    assert PersistenceStage().name == "persistence"


def test_return_records_have_schema_version(tmp_path):
    records = main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    assert records[0]["schema_version"] == SCHEMA_VERSION
    persisted = json.loads((tmp_path / "run_log.json").read_text(encoding="utf-8"))
    assert persisted[0]["schema_version"] == SCHEMA_VERSION


def test_human_approve_cannot_override_hard_or_immutable_red():
    ho = HumanOverrideLayer(policy_fn=HumanOverrideLayer.permissive_simulation_policy)
    assert ho.override(
        "RED", HumanAction.APPROVE, False,
        decision_class=DecisionClass.HARD_RED,
    ) == ("RED", False, False)
    assert ho.override(
        "RED", HumanAction.APPROVE, False,
        decision_class=DecisionClass.IMMUTABLE_RED,
    ) == ("RED", False, False)
    assert ho.override(
        "RED", HumanAction.APPROVE, False,
        decision_class=DecisionClass.SOFT_RED,
    ) == ("GREEN", True, True)


def test_human_decision_class_classifier_marks_truth_alarm_hard():
    ho = HumanOverrideLayer()
    assert ho.classify_decision_class(
        council_decision="RED",
        trigger_reasons=["truth_sensitivity_alarm"],
    ) == DecisionClass.HARD_RED.value


def test_fixture_llm_default_path_is_not_cwd_relative(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODE", "fixture")
    monkeypatch.delenv("LLM_FIXTURE_PATH", raising=False)
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        client = LLMClient()
        assert client.backend_name == "fixture"
        assert client.generate("what is 2+2") == "4"
    finally:
        os.chdir(old_cwd)


def test_memory_read_modify_write_preserves_external_update(tmp_path):
    path = tmp_path / "memory_store.json"
    stale = MemoryStore(str(path))
    fresh = MemoryStore(str(path))
    fresh.add_candidate("external update", "test", "heuristic")
    stale.add_candidate("stale writer update", "test", "heuristic")
    data = json.loads(path.read_text(encoding="utf-8"))
    contents = {entry["content"] for entry in data["candidate"]}
    assert contents == {"external update", "stale writer update"}
