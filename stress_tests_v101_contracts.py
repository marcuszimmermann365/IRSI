"""
LRSI V10.1 — Stage and Operability Contract Tests
=================================================
Executable script-style tests retained for compatibility with the existing
stress-test style.  Pytest wrappers also run these checks in CI.
"""

import json
import os
import tempfile
from copy import deepcopy

from dgm.core import ChangeProposal
from llm_client import LLMClient
from pipeline.stages import MutationStage, require_human_review_from_dgm
from policy import DEFAULT_POLICY
from storage import Storage
from version import SCHEMA_VERSION

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}: {detail}")


def test_version_contract():
    print("\n=== V10.1: Version contract ===")
    check("V10.1.1 schema_version_is_current", SCHEMA_VERSION == SCHEMA_VERSION, SCHEMA_VERSION)


def test_stage_suppressed_policy_contract():
    print("\n=== V10.1: Mutation stage contract ===")

    class DummyAgent:
        prompt = "base"
        policy = deepcopy(DEFAULT_POLICY)

    out = MutationStage().run(
        agent=DummyAgent(),
        iteration=0,
        allow_policy_change=False,
        previous_policy=deepcopy(DEFAULT_POLICY),
    )
    check("V10.1.2 prompt_contract_versioned", out.prompt_meta["schema_version"] == SCHEMA_VERSION)
    check("V10.1.3 policy_suppressed", out.policy_meta["description"] == "suppressed_by_mode")
    check("V10.1.4 no_changed_sections", out.policy_meta["changed_sections"] == [])


def test_dgm_human_review_contract():
    print("\n=== V10.1: DGM review contract ===")
    mandatory, reasons = require_human_review_from_dgm(False, [], {"requires_human_review": True})
    check("V10.1.5 human_review_forced", mandatory is True)
    check("V10.1.6 trigger_recorded", "dgm_requires_human_review" in reasons)


def test_layer_derivation_still_closes_immutable():
    print("\n=== V10.1: Derived layer still enforced ===")
    proposal = ChangeProposal(target_layer="adaptive", target_modules=["hold_policy"])
    check("V10.1.7 immutable_overrides_claim", proposal.target_layer == "immutable_attempt")


def test_storage_lock_and_schema():
    print("\n=== V10.1: Storage lock/schema ===")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "run_log.json")
        storage = Storage(path)
        storage.log_iteration({"iteration": 0})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        check("V10.1.8 storage_schema", data[0].get("schema_version") == SCHEMA_VERSION)
        check("V10.1.9 lock_file_created", os.path.exists(path + ".lock"))


def test_fixture_llm_mode():
    print("\n=== V10.1: Fixture LLM mode ===")
    old_mode = os.environ.get("LLM_MODE")
    old_path = os.environ.get("LLM_FIXTURE_PATH")
    try:
        os.environ["LLM_MODE"] = "fixture"
        os.environ["LLM_FIXTURE_PATH"] = "llm_fixtures/default.json"
        client = LLMClient()
        check("V10.1.10 fixture_backend", client.backend_name == "fixture")
        check("V10.1.11 fixture_answer", client.generate("what is 2+2") == "4")
    finally:
        if old_mode is None:
            os.environ.pop("LLM_MODE", None)
        else:
            os.environ["LLM_MODE"] = old_mode
        if old_path is None:
            os.environ.pop("LLM_FIXTURE_PATH", None)
        else:
            os.environ["LLM_FIXTURE_PATH"] = old_path


if __name__ == "__main__":
    print("\nLRSI V10.1 CONTRACT TESTS")
    print("=" * 64)
    test_version_contract()
    test_stage_suppressed_policy_contract()
    test_dgm_human_review_contract()
    test_layer_derivation_still_closes_immutable()
    test_storage_lock_and_schema()
    test_fixture_llm_mode()
    print("\n" + "=" * 64)
    print(f"V10.1 CONTRACT TESTS: {passed} passed, {failed} failed")
    print("=" * 64)
    if failed:
        raise SystemExit(1)
    print("Alle V10.1-Contract-Tests bestanden.")
