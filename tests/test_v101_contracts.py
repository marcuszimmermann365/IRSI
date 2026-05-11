import json
from copy import deepcopy

from dgm.core import ChangeProposal, classify_layer
from llm_client import LLMClient
from pipeline.stages import (
    CouncilStage,
    DGMPrecheckStage,
    GovernanceStage,
    MutationStage,
    require_human_review_from_dgm,
)
from policy import DEFAULT_POLICY
from storage import Storage
from version import SCHEMA_VERSION


def test_version_single_source_of_truth():
    assert SCHEMA_VERSION == SCHEMA_VERSION


def test_stage_classes_are_importable_contract_seams():
    assert GovernanceStage().name == "governance"
    assert MutationStage().name == "mutation"
    assert DGMPrecheckStage().name == "dgm_pre"
    assert CouncilStage().name == "council"


def test_dgm_human_review_requirement_is_hard_contract():
    mandatory, reasons = require_human_review_from_dgm(
        False, [], {"requires_human_review": True}
    )
    assert mandatory is True
    assert reasons == ["dgm_requires_human_review"]


def test_change_proposal_layer_still_derived():
    proposal = ChangeProposal(target_layer="adaptive", target_modules=["hold_policy"])
    assert proposal.target_layer == "immutable_attempt"
    assert classify_layer(proposal.target_modules) == "immutable_attempt"


def test_storage_uses_v101_schema(tmp_path):
    path = tmp_path / "run_log.json"
    storage = Storage(str(path))
    storage.log_iteration({"iteration": 0})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0]["schema_version"] == SCHEMA_VERSION
    assert data[0]["run_id"].startswith("run-")
    assert (tmp_path / "run_log.json.lock").exists()


def test_fixture_llm_mode(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "fixture")
    monkeypatch.setenv("LLM_FIXTURE_PATH", "llm_fixtures/default.json")
    client = LLMClient()
    assert client.backend_name == "fixture"
    assert client.generate("what is 2+2") == "4"


def test_mutation_stage_suppresses_policy_contract():
    class DummyAgent:
        prompt = "base"
        policy = deepcopy(DEFAULT_POLICY)

    out = MutationStage().run(
        agent=DummyAgent(),
        iteration=0,
        allow_policy_change=False,
        previous_policy=deepcopy(DEFAULT_POLICY),
    )
    assert out.policy_meta["description"] == "suppressed_by_mode"
    assert out.policy_meta["changed_sections"] == []
    assert out.policy_meta["schema_version"] == SCHEMA_VERSION
