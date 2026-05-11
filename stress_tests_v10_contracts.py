"""
LRSI V10 Contract-Bound Pipeline Tests
======================================
These tests guard the V10 contract layer:
  - hold_policy mutation is an immutable attempt at runtime
  - target_layer is derived from target_modules, not trusted metadata
  - policy metadata carries old/new/section contract information
  - storage writes versioned records atomically
"""

import json
import os
import sys
import tempfile
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dgm.core import ChangeProposal, ScopeChecker
from dgm_bridge import DGMRunnerBridge, changed_policy_sections
from meta import mutate_policy
from policy import DEFAULT_POLICY
from storage import Storage
from version import SCHEMA_VERSION

PASSES = []
FAILS = []


def check(name, condition, details=""):
    if condition:
        PASSES.append(name)
        print(f"  PASS  {name}")
    else:
        FAILS.append((name, details))
        print(f"  FAIL  {name}  {details}")


def test_hold_policy_runtime_mutation_is_immutable_attempt():
    print("\n=== V10: Immutable HOLD contract ===")
    policy_meta = mutate_policy(deepcopy(DEFAULT_POLICY), 2)
    check("V10.1 mutation_marks_hold_section",
          policy_meta.get("section") == "hold_policy",
          f"meta={policy_meta}")
    check("V10.2 mutation_carries_old_policy",
          policy_meta.get("old_policy") == DEFAULT_POLICY)
    check("V10.3 diff_detects_hold_policy",
          changed_policy_sections(policy_meta["old_policy"], policy_meta["new_policy"]) == ["hold_policy"])

    bridge = DGMRunnerBridge()
    proposal = bridge.wrap_mutation(
        prompt_meta={"original_prompt": "p", "new_prompt": "p"},
        policy_meta=policy_meta,
        iteration=2,
    )
    check("V10.4 proposal_targets_hold_policy",
          "hold_policy" in proposal.target_modules,
          f"targets={proposal.target_modules}")
    check("V10.5 proposal_layer_is_immutable_attempt",
          proposal.target_layer == "immutable_attempt",
          f"layer={proposal.target_layer}")

    allowed, reason, _ = bridge.pre_check(proposal)
    check("V10.6 dgm_pre_rejects_immutable_hold",
          allowed is False and reason == "immutable_core_violation",
          f"allowed={allowed} reason={reason}")


def test_target_layer_is_derived_not_trusted():
    print("\n=== V10: Derived target_layer ===")
    cp = ChangeProposal(target_layer="adaptive", target_modules=["policy_config"])
    check("V10.7 target_layer_recomputed_to_governance",
          cp.target_layer == "governance",
          f"layer={cp.target_layer}")

    cp2 = ChangeProposal(target_layer="governance", target_modules=["hold_policy"])
    check("V10.8 immutable_overrides_claimed_governance",
          cp2.target_layer == "immutable_attempt",
          f"layer={cp2.target_layer}")

    ok, reason, reqs = ScopeChecker().check(cp)
    check("V10.9 governance_requirements_bound",
          ok and reqs.get("requires_human_review") and reqs.get("min_evaluators") >= 4,
          f"ok={ok} reason={reason} reqs={reqs}")


def test_storage_records_schema_version():
    print("\n=== V10: Versioned atomic persistence ===")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "log.json")
        st = Storage(path)
        st.log_iteration({"iteration": 0, "final_decision": "HOLD"})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    check("V10.10 storage_writes_schema_version",
          data[0].get("schema_version") == SCHEMA_VERSION,
          f"record={data[0]}")
    check("V10.11 storage_writes_run_id_and_timestamp",
          bool(data[0].get("run_id")) and bool(data[0].get("created_at")))


def test_runner_records_dgm_contract():
    print("\n=== V10: Runner emits DGM contract records ===")
    import contextlib
    import io

    import runner

    with tempfile.TemporaryDirectory() as tmpdir:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            records = runner.main(
                iterations=3,
                storage_path=os.path.join(tmpdir, "run.json"),
                memory_path=os.path.join(tmpdir, "mem.json"),
                simulation_mode=True,
                return_records=True,
            )
    has_dgm = all("dgm" in r for r in records)
    check("V10.12 every_record_has_dgm_contract", has_dgm)
    immutable_rejects = [r for r in records if r.get("dgm", {}).get("proposal", {}).get("target_layer") == "immutable_attempt"]
    check("V10.13_runner_rejects_hold_policy_before_governance",
          bool(immutable_rejects) and immutable_rejects[0].get("gate_reason") == "dgm_pre:immutable_core_violation",
          f"records={records}")


if __name__ == "__main__":
    test_hold_policy_runtime_mutation_is_immutable_attempt()
    test_target_layer_is_derived_not_trusted()
    test_storage_records_schema_version()
    test_runner_records_dgm_contract()

    print()
    print("=" * 64)
    print(f"V10/V10.1 CONTRACT TESTS: {len(PASSES)} passed, {len(FAILS)} failed")
    print("=" * 64)
    if FAILS:
        for name, detail in FAILS:
            print(f"  FAIL: {name}  {detail}")
        sys.exit(1)
    print("Alle V10-Contract-Tests bestanden.")
