import io
import logging

import pytest

from invariants import (
    InvariantViolation,
    assert_council_red_always_leads_to_stop,
    assert_dgm_precheck_respects_block,
    assert_event_chain_integrity_after_block,
    assert_final_gate_respects_blocked_state,
    assert_hold_mode_blocks_all_mutations,
    assert_mutation_blocked_has_terminal,
    assert_no_mutation_without_preproposal_check,
    assert_preproposal_not_red_and_accepted,
)
from eventsourcing import AppendOnlyEventStore, RuntimeEvent
from pipeline.phase_runtime import PhaseResult
from pipeline.self_modification_phases import (
    PreProposalAdversarialPhase,
    PreProposalAdversarialPhaseInput,
)


class _Comparison:
    def __init__(self, decision="RED", distance=0.91):
        self._decision = decision
        self._distance = distance

    def to_dict(self):
        return {
            "decision": self._decision,
            "distance": self._distance,
            "reason": "unit_test_red_drift",
        }


class _RedSemanticDriftMonitor:
    def compare(self, baseline_prompt, new_prompt):
        return _Comparison("RED", 0.91)


class _GreenPreproposalOrchestrator:
    def attack(self, *, prompt_meta, policy_meta):
        return {
            "max_severity": "green",
            "findings": [],
        }


class _CaptureLogger:
    def __init__(self, *logger_names):
        self.logger_names = logger_names
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setLevel(logging.INFO)
        self.saved = []

    def __enter__(self):
        for name in self.logger_names:
            logger = logging.getLogger(name)
            self.saved.append((logger, list(logger.handlers), logger.level, logger.propagate))
            logger.handlers = [self.handler]
            logger.setLevel(logging.INFO)
            logger.propagate = False
        return self

    def __exit__(self, exc_type, exc, tb):
        for logger, handlers, level, propagate in self.saved:
            logger.handlers = handlers
            logger.setLevel(level)
            logger.propagate = propagate

    def text(self):
        self.handler.flush()
        return self.stream.getvalue()


def test_preproposal_red_sets_terminal_and_mutation_blocked():
    phase = PreProposalAdversarialPhase()
    result = phase.run(
        PreProposalAdversarialPhaseInput(
            prompt_meta={"new_prompt": "unsafe mutation"},
            policy_meta={"new_policy": {"risk": "unit"}},
            semantic_drift_monitor=_RedSemanticDriftMonitor(),
            preproposal_adversarial_orchestrator=_GreenPreproposalOrchestrator(),
        )
    )

    assert isinstance(result, PhaseResult)
    assert result.decision == "RED"
    assert result.terminal is True
    assert result.patch["mutation_blocked"] is True
    assert result.patch["block_reason"] == "semantic_drift_red"
    assert any(
        entry.get("stage") == "preproposal_kill_switch"
        and entry.get("terminal") is True
        and entry.get("mutation_blocked") is True
        for entry in result.trace_entries
    )

    # The central invariant should accept the hardened result.
    assert_mutation_blocked_has_terminal(result)


def test_invariants_reject_negative_examples():
    with pytest.raises(InvariantViolation):
        assert_preproposal_not_red_and_accepted(
            {"decision": "RED", "accepted": True},
            final_decision="ACCEPT",
        )

    with pytest.raises(InvariantViolation):
        assert_mutation_blocked_has_terminal(
            {
                "patch": {"mutation_blocked": True, "block_reason": "unit"},
                "terminal": False,
            }
        )

    with pytest.raises(InvariantViolation):
        assert_dgm_precheck_respects_block(
            {"mutation_blocked": True},
            {
                "decision": "PASS",
                "terminal": False,
                "patch": {"dgm_allowed": True},
            },
        )


def test_no_mutation_without_preproposal_check_negative_and_positive():
    with pytest.raises(InvariantViolation):
        assert_no_mutation_without_preproposal_check(
            {
                "prompt_meta": {"new_prompt": "mutated prompt"},
                "policy_meta": {"new_policy": {"review": "weakened"}},
                "phase_audit": [
                    {"phase": "mutation_phase", "audit_event_type": "phase_result"},
                ],
            }
        )

    assert_no_mutation_without_preproposal_check(
        {
            "prompt_meta": {"new_prompt": "mutated prompt"},
            "policy_meta": {"new_policy": {"review": "unchanged"}},
            "phase_audit": [
                {"phase": "mutation_phase", "audit_event_type": "phase_result"},
                {"phase": "preproposal_adversarial_phase", "audit_event_type": "phase_result"},
            ],
        }
    )


def test_final_gate_respects_blocked_state_negative_edge_case():
    blocked_state = {"mutation_blocked": True, "block_reason": "semantic_drift_red"}

    with pytest.raises(InvariantViolation):
        assert_final_gate_respects_blocked_state(
            blocked_state,
            {"final_decision": "ACCEPT", "accepted": True},
        )

    # HOLD/REJECT semantics remain valid for blocked states.
    assert_final_gate_respects_blocked_state(blocked_state, {"final_decision": "REJECT", "accepted": False})


def test_event_chain_integrity_after_block_detects_valid_and_tampered_chain(tmp_path):
    store = AppendOnlyEventStore(path=str(tmp_path / "events.jsonl"))
    first = store.append(
        RuntimeEvent(
            event_type="phase.result",
            phase="preproposal_adversarial_phase",
            iteration=0,
            payload={
                "phase_result": {
                    "phase": "preproposal_adversarial_phase",
                    "decision": "RED",
                    "reason": "semantic_drift_red",
                    "terminal": True,
                    "mutation_blocked": True,
                },
                "patch": {"mutation_blocked": True, "block_reason": "semantic_drift_red"},
                "decision": "RED",
                "reason": "semantic_drift_red",
                "terminal": True,
            },
        )
    )
    second = store.append(
        RuntimeEvent(
            event_type="audit.iteration_record",
            phase="persistence_phase",
            iteration=0,
            payload={"record": {"iteration": 0, "final_decision": "REJECT", "mutation_blocked": True}},
        )
    )

    assert_event_chain_integrity_after_block([first, second], block_iteration=0)

    tampered = [dict(first), dict(second)]
    tampered[0]["payload"] = dict(tampered[0]["payload"])
    tampered[0]["payload"]["decision"] = "GO"
    with pytest.raises(InvariantViolation):
        assert_event_chain_integrity_after_block(tampered, block_iteration=0)


def test_hold_mode_blocks_all_mutations_negative_and_positive():
    with pytest.raises(InvariantViolation):
        assert_hold_mode_blocks_all_mutations(
            {
                "mode": "hold",
                "final_decision": "HOLD",
                "accepted": True,
                "memory_events": [],
            }
        )

    with pytest.raises(InvariantViolation):
        assert_hold_mode_blocks_all_mutations(
            {
                "final_decision": "HOLD",
                "accepted": False,
                "memory_events": [{"consolidated": {"id": "mem-1"}}],
            }
        )

    assert_hold_mode_blocks_all_mutations(
        {
            "mode": "hold",
            "final_decision": "HOLD",
            "accepted": False,
            "memory_events": [],
        }
    )


def test_council_red_always_leads_to_stop_negative_and_positive():
    with pytest.raises(InvariantViolation):
        assert_council_red_always_leads_to_stop("RED", {"decision": "GO"})

    with pytest.raises(InvariantViolation):
        assert_council_red_always_leads_to_stop("RED", {"final_decision": "HOLD"})

    assert_council_red_always_leads_to_stop("RED", {"decision": "STOP"})
    assert_council_red_always_leads_to_stop("GREEN", {"decision": "GO"})


def test_multiple_invariants_catch_red_then_accept_bypass_attempt():
    red_result = {
        "decision": "RED",
        "terminal": True,
        "patch": {"mutation_blocked": True, "block_reason": "semantic_drift_red"},
    }

    assert_mutation_blocked_has_terminal(red_result)

    with pytest.raises(InvariantViolation):
        assert_preproposal_not_red_and_accepted(red_result, final_decision="ACCEPT", accepted=True)

    with pytest.raises(InvariantViolation):
        assert_final_gate_respects_blocked_state(red_result, {"decision": "GO", "accepted": True})

    with pytest.raises(InvariantViolation):
        assert_dgm_precheck_respects_block(
            red_result,
            {"decision": "PASS", "terminal": False, "patch": {"dgm_allowed": True}},
        )


def test_invariant_violation_logs_structured_context():
    with _CaptureLogger("lrsi.security.invariants") as captured_logs:
        with pytest.raises(InvariantViolation):
            assert_final_gate_respects_blocked_state(
                {"mutation_blocked": True, "block_reason": "unit"},
                {"decision": "GO", "accepted": True},
            )

    messages = captured_logs.text()
    assert "invariant_violation" in messages
    assert "final_gate_must_respect_blocked_state" in messages


def test_critical_block_logging_from_event_store_and_storage(tmp_path):
    from storage import Storage

    with _CaptureLogger("lrsi.security.eventsourcing", "lrsi.security.storage") as captured_logs:
        storage = Storage(str(tmp_path / "run_log.json"))
        record = {
            "iteration": 0,
            "trace_id": "trace-log-test",
            "mode": "integration",
            "parent_metrics": {},
            "child_metrics": None,
            "gate_decision": "REJECT",
            "gate_reason": "preproposal:semantic_drift_red",
            "accepted": False,
            "previous_policy": {"review": "required"},
            "candidate_policy": {"review": "skipped"},
            "effective_policy": {"review": "required"},
            "final_decision": "REJECT",
            "mutation_blocked": True,
            "block_reason": "semantic_drift_red",
            "prompt_meta": {"new_prompt": "unsafe"},
            "policy_meta": {"new_policy": {"review": "skipped"}},
            "preproposal_adversarial": {"max_severity": "red"},
            "phase_audit": [
                {
                    "schema_version": "12.1.0",
                    "audit_event_type": "phase_result",
                    "phase": "mutation_phase",
                    "iteration": 0,
                    "decision": "MUTATED",
                    "reason": "unit",
                    "diagnostics": {},
                    "patch_keys": ["prompt_meta", "policy_meta"],
                    "terminal": False,
                    "trace_id": "trace-log-test",
                },
                {
                    "schema_version": "12.1.0",
                    "audit_event_type": "phase_result",
                    "phase": "preproposal_adversarial_phase",
                    "iteration": 0,
                    "decision": "RED",
                    "reason": "semantic_drift_red",
                    "diagnostics": {"mutation_blocked": True},
                    "patch_keys": ["mutation_blocked", "block_reason"],
                    "terminal": True,
                    "trace_id": "trace-log-test",
                },
            ],
        }

        storage.log_iteration(record)

    messages = captured_logs.text()
    assert "critical_event_committed" in messages
    assert "critical_decision_persisted" in messages
    assert "blocked_mutation_event_chain_verified" in messages
