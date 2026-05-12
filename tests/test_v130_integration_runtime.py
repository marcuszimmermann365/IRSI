import json

import pytest

from evidence import EvidenceGenerator, verify_evidence_bundle_signature
from eventsourcing import AppendOnlyEventStore, RuntimeEvent, verify_event_chain
from invariants import (
    InvariantViolation,
    assert_dgm_precheck_respects_block,
    assert_final_gate_respects_blocked_state,
    assert_hold_mode_blocks_all_mutations,
    assert_mutation_blocked_has_terminal,
)
from pipeline.phase_runtime import PhaseResult
from pipeline.self_modification_phases import (
    PreProposalAdversarialPhase,
    PreProposalAdversarialPhaseInput,
)
from review_interface import TwoFactorReviewGate, sign_review_approval
from runner import main
from storage import Storage


class _Comparison:
    def __init__(self, decision="RED", distance=0.91):
        self.decision = decision
        self.distance = distance

    def to_dict(self):
        return {
            "decision": self.decision,
            "distance": self.distance,
            "reason": f"integration_{self.decision.lower()}",
        }


class _RedSemanticDriftMonitor:
    def compare(self, baseline_prompt, new_prompt):
        return _Comparison("RED", 0.93)


class _GreenPreproposalOrchestrator:
    def attack(self, *, prompt_meta, policy_meta):
        return {"max_severity": "green", "findings": []}


class _EvidenceCtx:
    iteration = 11
    final_decision = "HOLD"
    ext_decision = "HOLD"
    dgm_proposal = None
    prompt_meta = {
        "original_prompt": "base prompt",
        "new_prompt": "candidate prompt",
        "mutation": {"type": "integration"},
    }
    policy_meta = {
        "description": "integration policy change",
        "section": "review_policy",
        "changed_sections": ["review_policy"],
    }
    per_role = {"critic": {"decision": "YELLOW", "reason": "needs review"}}
    drel_diag = {"relation": "integration"}
    ext_diag = {"reason": "hold"}
    drel_status = "YELLOW"
    drel_reason = "integration hold"
    ss_risk = 0.0
    real_agency = 1.0
    o_ext = 1.0
    semantic_drift = {"decision": "YELLOW", "distance": 0.3}


def _phase_names(record):
    return [entry.get("phase") for entry in record.get("phase_audit", [])]


def test_integration_full_iteration_pipeline_reaches_selfmod_and_final_gate(tmp_path):
    run_log = tmp_path / "run_log.json"
    memory = tmp_path / "memory.json"

    records = main(
        iterations=1,
        storage_path=str(run_log),
        memory_path=str(memory),
        return_records=True,
        verbose=False,
    )

    assert len(records) == 1
    record = records[0]
    phases = _phase_names(record)

    assert "mutation_phase" in phases
    assert "preproposal_adversarial_phase" in phases
    assert "dgm_precheck_phase" in phases
    assert "final_gate" in phases
    assert record["final_decision"] in {"GO", "HOLD", "STOP", "REJECT", "ROLLBACK"}

    events = [json.loads(line) for line in (tmp_path / "run_log.json.events.jsonl").read_text().splitlines() if line]
    ok, errors = verify_event_chain(events)
    assert ok, errors
    event_phases = {event.get("phase") for event in events if event.get("event_type") == "phase.result"}
    assert {"mutation_phase", "preproposal_adversarial_phase", "dgm_precheck_phase", "final_gate"} <= event_phases


def test_integration_red_preproposal_creates_terminal_block_and_rejects_downstream_acceptance():
    phase = PreProposalAdversarialPhase()
    result = phase.run(
        PreProposalAdversarialPhaseInput(
            prompt_meta={"new_prompt": "unsafe self-modification"},
            policy_meta={"new_policy": {"review": "skipped"}},
            semantic_drift_monitor=_RedSemanticDriftMonitor(),
            preproposal_adversarial_orchestrator=_GreenPreproposalOrchestrator(),
        )
    )

    assert isinstance(result, PhaseResult)
    assert result.decision == "RED"
    assert result.terminal is True
    assert result.patch["mutation_blocked"] is True
    assert result.patch["block_reason"] == "semantic_drift_red"

    assert_mutation_blocked_has_terminal(result)

    with pytest.raises(InvariantViolation):
        assert_dgm_precheck_respects_block(
            result,
            {"decision": "PASS", "terminal": False, "patch": {"dgm_allowed": True}},
        )

    with pytest.raises(InvariantViolation):
        assert_final_gate_respects_blocked_state(
            result,
            {"decision": "GO", "accepted": True},
        )


def test_integration_event_chain_creation_verification_and_tamper_detection(tmp_path):
    store = AppendOnlyEventStore(path=str(tmp_path / "events.jsonl"))

    first = store.append(
        RuntimeEvent(
            event_type="phase.result",
            phase="mutation_phase",
            iteration=0,
            payload={"phase_result": {"decision": "MUTATED", "reason": "integration"}},
        )
    )
    second = store.append(
        RuntimeEvent(
            event_type="phase.result",
            phase="final_gate",
            iteration=0,
            payload={"phase_result": {"decision": "HOLD", "reason": "integration"}},
        )
    )

    ok, errors = store.verify()
    assert ok, errors
    assert second["sequence"] == first["sequence"] + 1
    assert second["previous_event_hash"] == first["event_hash"]

    events = store.load()
    tampered = [dict(event) for event in events]
    tampered[1]["previous_event_hash"] = "f" * 64
    ok, errors = verify_event_chain(tampered)
    assert not ok
    assert errors


def test_integration_storage_materialized_record_and_event_store_replay(tmp_path):
    storage = Storage(str(tmp_path / "run_log.json"))
    record = {
        "trace_id": "integration-storage",
        "iteration": 0,
        "mode": "integration",
        "final_decision": "HOLD",
        "gate_decision": "YELLOW",
        "gate_reason": "integration_hold",
        "accepted": False,
        "phase_audit": [
            {
                "schema_version": "13.0.0",
                "audit_event_type": "phase_result",
                "phase": "mutation_phase",
                "iteration": 0,
                "decision": "MUTATED",
                "reason": "integration",
                "diagnostics": {},
                "patch_keys": ["prompt_meta", "policy_meta"],
                "terminal": False,
                "trace_id": "integration-storage",
            },
            {
                "schema_version": "13.0.0",
                "audit_event_type": "phase_result",
                "phase": "preproposal_adversarial_phase",
                "iteration": 0,
                "decision": "GREEN",
                "reason": "preproposal_clear",
                "diagnostics": {},
                "patch_keys": [],
                "terminal": False,
                "trace_id": "integration-storage",
            },
            {
                "schema_version": "13.0.0",
                "audit_event_type": "phase_result",
                "phase": "final_gate",
                "iteration": 0,
                "decision": "HOLD",
                "reason": "integration_hold",
                "diagnostics": {},
                "patch_keys": [],
                "terminal": False,
                "trace_id": "integration-storage",
            },
        ],
    }

    persisted = storage.log_iteration(record)

    assert persisted["record_hash"]
    assert persisted["event_refs_v12"]
    assert {ref["phase"] for ref in persisted["event_refs_v12"] if ref["event_type"] == "phase.result"} >= {
        "mutation_phase",
        "preproposal_adversarial_phase",
        "final_gate",
    }

    ok, errors = storage.verify_event_chain()
    assert ok, errors

    replay = storage.replay_decisions()
    assert replay["decisions"][0]["final_decision"] == "HOLD"
    assert replay["decisions"][0]["record_hash"] == persisted["record_hash"]


def test_integration_signed_evidence_bundle_verifies_and_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("AUDIT_SIGNING_MODE", "hmac")
    monkeypatch.setenv("AUDIT_HMAC_KEY", "integration-secret")
    monkeypatch.setenv("AUDIT_SIGNER_ID", "integration-runtime")

    bundle = EvidenceGenerator().generate(_EvidenceCtx()).to_dict()

    assert bundle["evidence_bundle_hash"]
    assert bundle["evidence_signature"]
    assert bundle["evidence_signature_algorithm"].startswith("HMAC")
    assert verify_evidence_bundle_signature(bundle)

    tampered = dict(bundle)
    tampered["evidence_signature"] = "not-the-real-signature"
    assert not verify_evidence_bundle_signature(tampered)


def test_integration_evidence_bound_two_person_review_with_signed_approvals(monkeypatch):
    monkeypatch.setenv("AUDIT_SIGNING_MODE", "hmac")
    monkeypatch.setenv("AUDIT_HMAC_KEY", "integration-review-secret")
    monkeypatch.setenv("AUDIT_SIGNER_ID", "integration-reviewer")

    bundle = EvidenceGenerator().generate(_EvidenceCtx()).to_dict()
    approvals = [
        sign_review_approval(
            reviewer_id="alice",
            role="security_auditor",
            rationale="integration review one",
            evidence_case_id=bundle["case_id"],
            evidence_bundle_hash=bundle["evidence_bundle_hash"],
        ).to_dict(),
        sign_review_approval(
            reviewer_id="bob",
            role="system_operator",
            rationale="integration review two",
            evidence_case_id=bundle["case_id"],
            evidence_bundle_hash=bundle["evidence_bundle_hash"],
        ).to_dict(),
    ]

    ok, reasons = TwoFactorReviewGate().validate(approvals, evidence_bundle=bundle)
    assert ok, reasons

    one_person_ok, one_person_reasons = TwoFactorReviewGate().validate(approvals[:1], evidence_bundle=bundle)
    assert not one_person_ok
    assert one_person_reasons


def test_integration_hold_mode_keeps_candidate_unapplied(tmp_path):
    records = main(
        iterations=1,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory.json"),
        return_records=True,
        verbose=False,
    )

    record = records[0]
    if record["final_decision"] == "HOLD":
        assert record["accepted"] is False
        assert record["effective_policy"] == record["previous_policy"]
        assert_hold_mode_blocks_all_mutations(record)
    else:
        assert record["final_decision"] in {"GO", "STOP", "REJECT", "ROLLBACK"}


def test_integration_blocked_storage_record_is_persisted_with_terminal_event_and_valid_chain(tmp_path):
    storage = Storage(str(tmp_path / "blocked_log.json"))
    record = {
        "trace_id": "integration-red-block",
        "iteration": 2,
        "mode": "integration",
        "final_decision": "REJECT",
        "gate_decision": "REJECT",
        "gate_reason": "preproposal:semantic_drift_red",
        "accepted": False,
        "previous_policy": {"review": "required"},
        "candidate_policy": {"review": "skipped"},
        "effective_policy": {"review": "required"},
        "mutation_blocked": True,
        "block_reason": "semantic_drift_red",
        "prompt_meta": {"new_prompt": "unsafe self-modification"},
        "policy_meta": {"new_policy": {"review": "skipped"}},
        "preproposal_adversarial": {"max_severity": "red"},
        "phase_audit": [
            {
                "schema_version": "13.0.0",
                "audit_event_type": "phase_result",
                "phase": "mutation_phase",
                "iteration": 2,
                "decision": "MUTATED",
                "reason": "integration",
                "diagnostics": {},
                "patch_keys": ["prompt_meta", "policy_meta"],
                "terminal": False,
                "trace_id": "integration-red-block",
            },
            {
                "schema_version": "13.0.0",
                "audit_event_type": "phase_result",
                "phase": "preproposal_adversarial_phase",
                "iteration": 2,
                "decision": "RED",
                "reason": "semantic_drift_red",
                "diagnostics": {"mutation_blocked": True},
                "patch_keys": ["mutation_blocked", "block_reason"],
                "terminal": True,
                "trace_id": "integration-red-block",
            },
        ],
    }

    persisted = storage.log_iteration(record)

    assert persisted["mutation_blocked"] is True
    assert persisted["final_decision"] == "REJECT"
    assert persisted["effective_policy"] == persisted["previous_policy"]
    assert any(ref["phase"] == "preproposal_adversarial_phase" for ref in persisted["event_refs_v12"])

    ok, errors = storage.verify_event_chain()
    assert ok, errors
