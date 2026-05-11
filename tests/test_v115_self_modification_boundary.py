
import runner
from pipeline.phase_runtime import PhaseResult
from pipeline.self_modification_phases import (
    DGMPostcheckPhase,
    DGMPrecheckPhase,
    MutationPhase,
    PreProposalAdversarialPhase,
)
from storage import verify_hash_chain


def _phase_names(record):
    return [entry.get("phase") for entry in record.get("phase_audit", [])]


def test_v115_self_modification_phases_expose_explicit_contracts():
    phases = [
        MutationPhase(),
        PreProposalAdversarialPhase(),
        DGMPrecheckPhase(),
        DGMPostcheckPhase(),
    ]
    for phase in phases:
        assert phase.name
        assert phase.input_type is not None
        assert isinstance(phase.required_keys, tuple)
        assert phase.required_keys


def test_v115_runner_audits_self_modification_boundary(tmp_path):
    records = runner.main(
        iterations=2,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    assert len(records) == 2
    first = records[0]
    phases = _phase_names(first)
    assert "mutation_phase" in phases
    assert "preproposal_adversarial_phase" in phases
    assert "dgm_precheck_phase" in phases
    assert "dgm_postcheck_phase" in phases
    boundary = first["self_modification_boundary_v11_5"]
    assert set(boundary) == {"mutation", "preproposal", "dgm_precheck", "dgm_postcheck"}
    assert boundary["dgm_precheck"]["allowed"] is True
    assert "proposal" in boundary["dgm_precheck"]
    assert boundary["dgm_postcheck"]["diagnostics"]["proposal_id"] == boundary["dgm_precheck"]["proposal"]["change_id"]
    assert verify_hash_chain(records)[0]


def test_v115_dgm_pre_reject_record_keeps_phase_audit_and_hash_chain(tmp_path):
    records = runner.main(
        iterations=3,
        storage_path=str(tmp_path / "run_log.json"),
        memory_path=str(tmp_path / "memory_store.json"),
        return_records=True,
    )
    reject = records[2]
    assert reject["gate_reason"] in {
        "dgm_pre:immutable_core_violation",
        "preproposal:preproposal_attack_red",
    }
    assert reject["accepted"] is False
    phases = _phase_names(reject)
    assert phases[:3] == [
        "review_mode",
        "mutation_phase",
        "preproposal_adversarial_phase",
    ]
    if reject["gate_reason"].startswith("preproposal:"):
        assert reject["mutation_blocked"] is True
        assert reject["final_decision"] == "REJECT"
        assert phases == [
            "review_mode",
            "mutation_phase",
            "preproposal_adversarial_phase",
        ]
    else:
        assert reject["dgm"]["pre_check"]["allowed"] is False
        assert phases == [
            "review_mode",
            "mutation_phase",
            "preproposal_adversarial_phase",
            "dgm_precheck_phase",
        ]
    assert verify_hash_chain(records)[0]


def test_v115_phase_result_audit_entry_is_generic():
    result = PhaseResult(
        phase="example_selfmod_phase",
        decision="PASS",
        reason="contract_ok",
        diagnostics={"x": 1},
        patch={"foo": "bar"},
    )
    audit = result.audit_entry(iteration=7)
    assert audit["audit_event_type"] == "phase_result"
    assert audit["phase"] == "example_selfmod_phase"
    assert audit["patch_keys"] == ["foo"]
    assert audit["iteration"] == 7
