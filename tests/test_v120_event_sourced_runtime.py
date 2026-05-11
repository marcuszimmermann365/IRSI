import json

from audit_sinks import LocalWORMDirectorySink
from eventsourcing import (
    AppendOnlyEventStore,
    RuntimeEvent,
    project_events,
    replay_decisions,
    verify_event_chain,
)
from evidence import EvidenceGenerator, verify_evidence_bundle_signature
from review_interface import TwoFactorReviewGate
from runner import main
from signing import Ed25519SigningAdapter
from storage import Storage
from version import SCHEMA_VERSION


class DummyCtx:
    iteration = 7
    final_decision = "HOLD"
    ext_decision = "HOLD"
    dgm_proposal = None
    prompt_meta = {"original_prompt": "a", "new_prompt": "b", "mutation": {"type": "test"}}
    policy_meta = {"description": "test", "section": "strategy_policy", "changed_sections": ["strategy_policy"]}
    per_role = {"critic": {"decision": "YELLOW", "reason": "review"}}
    drel_diag = {"relation": "diagnostic"}
    ext_diag = {"reason": "hold"}
    drel_status = "YELLOW"
    drel_reason = "test"
    ss_risk = 0.0
    real_agency = 1.0
    o_ext = 1.0
    semantic_drift = {"decision": "GREEN", "distance": 0.0}


def test_runtime_emits_hash_chained_event_stream_and_replays_decision(tmp_path):
    run_log = tmp_path / "run_log.json"
    memory = tmp_path / "memory.json"

    records = main(
        iterations=1,
        storage_path=str(run_log),
        memory_path=str(memory),
        return_records=True,
        verbose=False,
    )

    events_path = tmp_path / "run_log.json.events.jsonl"
    assert events_path.exists()
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    assert len(events) >= records[0]["event_sourcing_v12_0"]["phase_event_count"]
    ok, errors = verify_event_chain(events)
    assert ok, errors

    projection = project_events(events)
    replay = replay_decisions(events)
    assert projection["iterations"]
    assert replay["decisions"][0]["final_decision"] == records[0]["final_decision"]
    assert replay["decisions"][0]["record_hash"] == records[0]["record_hash"]


def test_event_store_worm_sink_refuses_overwrite(tmp_path):
    sink = LocalWORMDirectorySink(str(tmp_path / "worm"))
    store = AppendOnlyEventStore(path=str(tmp_path / "events.jsonl"), external_sink=sink)
    event = RuntimeEvent(event_type="phase.result", phase="unit", payload={"x": 1})
    written = store.append(event)
    assert written["external_write"]["sink"] == "local-worm-directory"

    try:
        sink.write_once(written["event_id"], {"x": 2})
    except FileExistsError:
        pass
    else:  # pragma: no cover
        raise AssertionError("WORM sink allowed overwrite")


def test_storage_event_projection_is_primary_replay_surface(tmp_path):
    storage = Storage(str(tmp_path / "run_log.json"))
    record = {
        "iteration": 0,
        "final_decision": "HOLD",
        "accepted": False,
        "events_v12": [
            RuntimeEvent(
                event_type="phase.result",
                phase="final_gate_phase",
                iteration=0,
                payload={"phase_result": {"decision": "HOLD", "reason": "unit"}},
            ).to_dict()
        ],
    }
    persisted = storage.log_iteration(record)
    assert persisted["record_hash"]
    ok, errors = storage.verify_event_chain()
    assert ok, errors
    replay = storage.replay_decisions()
    assert replay["decisions"][0]["final_decision"] == "HOLD"


def test_storage_backfills_terminal_phase_events_from_phase_audit(tmp_path):
    storage = Storage(str(tmp_path / "terminal_log.json"))
    record = {
        "trace_id": "trace-terminal",
        "iteration": 2,
        "final_decision": "HOLD",
        "accepted": False,
        "phase_audit": [
            {
                "schema_version": SCHEMA_VERSION,
                "audit_event_type": "phase_result",
                "phase": "review_mode",
                "iteration": 2,
                "decision": "CHECKED",
                "reason": "not_review",
                "diagnostics": {},
                "patch_keys": [],
                "terminal": False,
            },
            {
                "schema_version": SCHEMA_VERSION,
                "audit_event_type": "phase_result",
                "phase": "dgm_precheck_phase",
                "iteration": 2,
                "decision": "REJECT",
                "reason": "unit_reject",
                "diagnostics": {},
                "patch_keys": ["record"],
                "terminal": True,
            },
        ],
    }
    persisted = storage.log_iteration(record)
    assert len(persisted["events_v12"]) == 2
    phases = [e["phase"] for e in storage.load_events() if e["event_type"] == "phase.result"]
    assert phases == ["review_mode", "dgm_precheck_phase"]
    replay = storage.replay_decisions()
    assert replay["decisions"][0]["final_decision"] == "HOLD"
    assert replay["decisions"][0]["phase_count"] == 2


def test_project_events_accepts_current_final_gate_phase_name():
    events = [
        RuntimeEvent(
            event_type="phase.result",
            phase="final_gate",
            iteration=0,
            payload={"phase_result": {"decision": "HOLD", "reason": "unit"}},
        ).to_dict()
    ]
    replay = replay_decisions(events)
    assert replay["decisions"][0]["final_decision"] == "HOLD"


def test_evidence_bound_review_rejects_unverifiable_approval_signatures(monkeypatch):
    monkeypatch.setenv("AUDIT_SIGNING_MODE", "hmac")
    monkeypatch.setenv("AUDIT_HMAC_KEY", "unit-secret")
    bundle = EvidenceGenerator().generate(DummyCtx()).to_dict()
    approvals = [
        {
            "reviewer_id": "alice",
            "role": "security_auditor",
            "action": "approve",
            "rationale": "reviewed evidence",
            "signature": "not-a-real-signature",
            "signature_algorithm": "external-test",
            "evidence_case_id": bundle["case_id"],
            "evidence_bundle_hash": bundle["evidence_bundle_hash"],
        },
        {
            "reviewer_id": "bob",
            "role": "system_operator",
            "action": "approve",
            "rationale": "reviewed runtime state",
            "signature": "not-a-real-signature",
            "signature_algorithm": "external-test",
            "evidence_case_id": bundle["case_id"],
            "evidence_bundle_hash": bundle["evidence_bundle_hash"],
        },
    ]
    ok, reasons = TwoFactorReviewGate().validate(approvals, action="approve", evidence_bundle=bundle)
    assert not ok
    assert any(r.startswith("review_approval_signature_invalid") for r in reasons)


def test_production_event_store_requires_ed25519_signing_and_worm(monkeypatch, tmp_path):
    monkeypatch.delenv("AUDIT_SIGNING_MODE", raising=False)
    monkeypatch.delenv("AUDIT_HMAC_KEY", raising=False)
    monkeypatch.delenv("AUDIT_WORM_DIR", raising=False)
    try:
        Storage(str(tmp_path / "prod_missing.json"), production_mode=True)
    except RuntimeError as exc:
        assert "production event store requires" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("production mode accepted unsigned/non-WORM audit config")

    monkeypatch.setenv("AUDIT_SIGNING_MODE", "hmac")
    monkeypatch.setenv("AUDIT_HMAC_KEY", "unit-secret")
    monkeypatch.setenv("AUDIT_WORM_DIR", str(tmp_path / "worm-hmac"))
    try:
        Storage(str(tmp_path / "prod_hmac_rejected.json"), production_mode=True)
    except RuntimeError as exc:
        assert "HMAC is dev-only" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("production mode accepted HMAC audit signing")

    signing_adapter = Ed25519SigningAdapter.generate_for_tests(signer_id="prod-runtime")
    event_store = AppendOnlyEventStore(
        path=str(tmp_path / "prod_ok.events.jsonl"),
        signing_adapter=signing_adapter,
        external_sink=LocalWORMDirectorySink(str(tmp_path / "worm-ed25519")),
        production_mode=True,
    )
    storage = Storage(str(tmp_path / "prod_ok.json"), event_store=event_store, production_mode=True)
    storage.log_iteration({"iteration": 0, "final_decision": "HOLD", "accepted": False})
    ok, errors = storage.verify_event_chain(require_signature=True)
    assert ok, errors


def test_evidence_bundle_is_signed_and_two_factor_review_binds_to_case(monkeypatch):
    monkeypatch.setenv("AUDIT_SIGNING_MODE", "hmac")
    monkeypatch.setenv("AUDIT_HMAC_KEY", "unit-secret")
    bundle = EvidenceGenerator().generate(DummyCtx()).to_dict()
    assert bundle["schema"] == "lrsi.evidence_bundle.v1"
    assert bundle["evidence_bundle_hash"]
    assert bundle["evidence_signature"]
    assert verify_evidence_bundle_signature(bundle)

    approvals = [
        TwoFactorReviewGate.signed_approval(
            "security_auditor",
            reviewer_id="alice",
            case_id=bundle["case_id"],
            evidence_bundle_hash=bundle["evidence_bundle_hash"],
            rationale="reviewed evidence",
        ),
        TwoFactorReviewGate.signed_approval(
            "system_operator",
            reviewer_id="bob",
            case_id=bundle["case_id"],
            evidence_bundle_hash=bundle["evidence_bundle_hash"],
            rationale="reviewed runtime state",
        ),
    ]
    ok, reasons = TwoFactorReviewGate().validate(
        approvals, action="approve", evidence_bundle=bundle
    )
    assert ok, reasons


def test_runtime_version_is_v12():
    assert SCHEMA_VERSION == "12.0"
