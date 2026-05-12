import json
import subprocess

from pipeline.phase_services import AdversarialPhaseResult
from pipeline.runner_core import PipelineExecution
from runner import main
from storage import Storage, verify_hash_chain
from version import SCHEMA_VERSION


def test_schema_version_v110():
    assert SCHEMA_VERSION in {"11.0", "11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "12.0", "12.1.0", "12.2.0", "13.0.0", "13.2.0", "13.3.0"}


def test_review_mode_persists_without_crash(tmp_path):
    execution = PipelineExecution(
        iterations=0,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    execution.governance.mode = "review"

    execution.run_iteration(0)

    assert execution.all_records
    record = execution.all_records[0]
    assert record["mode"] == "review"
    assert record["final_decision"] == "HOLD"
    assert "record_hash" in record
    ok, errors = verify_hash_chain(execution.all_records)
    assert ok, errors


def test_verify_hash_chain_fails_closed_on_missing_hash_fields():
    ok, errors = verify_hash_chain([{"iteration": 1, "accepted": True}])
    assert not ok
    assert any("previous_record_hash missing" in err for err in errors)
    assert any("record_hash missing" in err for err in errors)


def test_verify_hash_chain_has_explicit_legacy_mode():
    ok, errors = verify_hash_chain(
        [{"iteration": 1, "accepted": True}],
        allow_legacy_unhashed=True,
    )
    assert ok, errors == []


def test_audit_tampering_and_missing_hashes_are_detected(tmp_path):
    storage = Storage(str(tmp_path / "run_log.json"))
    storage.log_iteration({"iteration": 0, "final_decision": "HOLD"})
    storage.log_iteration({"iteration": 1, "final_decision": "HOLD"})
    records = json.loads((tmp_path / "run_log.json").read_text(encoding="utf-8"))

    records[0]["final_decision"] = "GO"
    ok, errors = verify_hash_chain(records)
    assert not ok
    assert any("record_hash mismatch" in err for err in errors)

    del records[1]["record_hash"]
    ok, errors = verify_hash_chain(records)
    assert not ok
    assert any("record_hash missing" in err for err in errors)


def test_returned_records_are_strictly_hash_verifiable(tmp_path):
    records = main(
        iterations=2,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    ok, errors = verify_hash_chain(records)
    assert ok, errors


def test_adversarial_phase_returns_result_and_runner_applies_it(tmp_path):
    execution = PipelineExecution(
        iterations=0,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    ctx = execution.prepare_iteration(0)
    assert execution.run_mutation_contract(ctx)
    execution.run_council(ctx)
    execution.run_hold_logic(ctx)
    execution.run_human_review(ctx)
    execution.run_erosion_and_human_coupling(ctx)
    execution.run_attractor_checks(ctx)

    before_trace = list(ctx.decision_trace)
    result = execution.adversarial_phase.run(
        ctx=ctx,
        stages={"a3": execution.a3_stage, "a4": execution.a4_stage, "drel": execution.drel_stage},
        services={
            "external_commits": execution.external_commits,
            "agency_verifier": execution.agency_verifier,
            "dgm_bridge": execution.dgm_bridge,
            "prev_attractor_state": execution.prev_attractor_state,
        },
        history=execution.all_records,
    )
    assert isinstance(result, AdversarialPhaseResult)
    assert ctx.decision_trace == before_trace  # service did not mutate shared ctx implicitly
    result.apply_to(ctx)
    assert ctx.drel_status == result.drel_status
    assert len(ctx.decision_trace) > len(before_trace)


def test_optional_hmac_audit_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_HMAC_KEY", "test-secret")
    storage = Storage(str(tmp_path / "signed_log.json"))
    storage.log_iteration({"iteration": 0, "final_decision": "HOLD"})
    records = json.loads((tmp_path / "signed_log.json").read_text(encoding="utf-8"))
    assert records[0]["audit_signature_algorithm"] == "HMAC-SHA256(record_hash)"
    ok, errors = verify_hash_chain(records, require_signature=True, signature_key="test-secret")
    assert ok, errors
    ok, errors = verify_hash_chain(records, require_signature=True, signature_key="wrong")
    assert not ok
    assert any("audit_signature invalid" in err for err in errors)


def test_make_check_is_available():
    result = subprocess.run(
        ["make", "-n", "check"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0
    assert "compileall" in result.stdout
    assert "pytest" in result.stdout
