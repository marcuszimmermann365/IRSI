import io
import logging
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from eventsourcing import AppendOnlyEventStore, RuntimeEvent
from invariants import (
    InvariantViolation,
    assert_council_red_always_leads_to_stop,
    assert_dgm_precheck_respects_block,
    assert_event_chain_integrity_after_block,
    assert_final_gate_respects_blocked_state,
    assert_hold_mode_blocks_all_mutations,
    assert_preproposal_not_red_and_accepted,
    assert_blocked_record_effective_policy_unchanged,
    assert_event_refs_match_phase_audit,
    assert_no_mutation_without_preproposal_check,
    assert_terminal_security_event_is_non_accepting,
)
from pipeline.self_modification_phases import (
    PreProposalAdversarialPhase,
    PreProposalAdversarialPhaseInput,
)


_DECISIONS = st.sampled_from(["GREEN", "YELLOW", "RED"])
_FINAL_DECISIONS = st.sampled_from(["GO", "ACCEPT", "HOLD", "STOP", "REJECT", "ROLLBACK"])


class _Comparison:
    def __init__(self, decision: str):
        self.decision = decision

    def to_dict(self):
        return {
            "decision": self.decision,
            "distance": {"GREEN": 0.05, "YELLOW": 0.35, "RED": 0.95}[self.decision],
            "reason": f"property_{self.decision.lower()}",
        }


class _SemanticDriftMonitor:
    def __init__(self, decision: str):
        self.decision = decision

    def compare(self, baseline_prompt, new_prompt):
        return _Comparison(self.decision)


class _PreproposalOrchestrator:
    def __init__(self, severity: str):
        self.severity = severity

    def attack(self, *, prompt_meta, policy_meta):
        finding = {
            "severity": self.severity.lower(),
            "category": "property",
            "message": f"property_{self.severity.lower()}",
        }
        return {
            "max_severity": self.severity.lower(),
            "findings": [] if self.severity == "GREEN" else [finding],
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

@settings(max_examples=30, deadline=None)
@given(tail_decisions=st.lists(_FINAL_DECISIONS, min_size=0, max_size=5))
def test_property_event_chain_integrity_after_block_detects_tampering(tail_decisions):
    with tempfile.TemporaryDirectory() as tmp:
        store = AppendOnlyEventStore(path=f"{tmp}/events.jsonl")
        events = [
            store.append(
                RuntimeEvent(
                    event_type="phase.result",
                    phase="preproposal_adversarial_phase",
                    iteration=0,
                    payload={
                        "phase_result": {
                            "phase": "preproposal_adversarial_phase",
                            "decision": "RED",
                            "reason": "property_red",
                            "terminal": True,
                            "mutation_blocked": True,
                        },
                        "patch": {"mutation_blocked": True, "block_reason": "property_red"},
                        "decision": "RED",
                        "reason": "property_red",
                        "terminal": True,
                    },
                )
            )
        ]

        for index, decision in enumerate(tail_decisions, start=1):
            events.append(
                store.append(
                    RuntimeEvent(
                        event_type="phase.result",
                        phase="final_gate",
                        iteration=0,
                        payload={
                            "phase_result": {
                                "phase": "final_gate",
                                "decision": decision,
                                "reason": f"property_{decision.lower()}",
                                "terminal": decision in {"STOP", "REJECT", "ROLLBACK"},
                            },
                            "decision": decision,
                            "reason": f"property_{decision.lower()}",
                            "terminal": decision in {"STOP", "REJECT", "ROLLBACK"},
                        },
                    )
                )
            )

        assert_event_chain_integrity_after_block(events, block_iteration=0)

        tampered = [dict(event) for event in events]
        # Deterministic tamper: change a chain-critical field rather than a
        # decision value that may already be equal to the replacement.
        tampered[-1]["previous_event_hash"] = "f" * 64
        with pytest.raises(InvariantViolation):
            assert_event_chain_integrity_after_block(tampered, block_iteration=0)


@settings(max_examples=30, deadline=None)
@given(semantic_decision=_DECISIONS, attack_severity=_DECISIONS)
def test_property_preproposal_boundary_blocks_any_red_input(semantic_decision, attack_severity):
    result = PreProposalAdversarialPhase().run(
        PreProposalAdversarialPhaseInput(
            prompt_meta={"new_prompt": f"property-{semantic_decision}-{attack_severity}"},
            policy_meta={"new_policy": {"property": True}},
            semantic_drift_monitor=_SemanticDriftMonitor(semantic_decision),
            preproposal_adversarial_orchestrator=_PreproposalOrchestrator(attack_severity),
        )
    )

    if "RED" in {semantic_decision, attack_severity}:
        assert result.decision == "RED"
        assert result.terminal is True
        assert result.patch["mutation_blocked"] is True
        assert result.patch["block_reason"]
        assert_final_gate_respects_blocked_state(result, {"final_decision": "REJECT", "accepted": False})
        with pytest.raises(InvariantViolation):
            assert_final_gate_respects_blocked_state(result, {"final_decision": "GO", "accepted": True})
    else:
        assert result.decision in {"GREEN", "YELLOW"}
        assert result.terminal is False
        assert result.patch["mutation_blocked"] is False


@settings(max_examples=40, deadline=None)
@given(preproposal_decision=_DECISIONS, final_decision=_FINAL_DECISIONS, accepted=st.booleans())
def test_property_preproposal_red_acceptance_invariant(preproposal_decision, final_decision, accepted):
    state = {
        "decision": preproposal_decision,
        "terminal": preproposal_decision == "RED",
        "patch": {
            "mutation_blocked": preproposal_decision == "RED",
            "block_reason": "property" if preproposal_decision == "RED" else "",
        },
    }
    should_raise = preproposal_decision == "RED" and (accepted or final_decision in {"GO", "ACCEPT"})
    if should_raise:
        with pytest.raises(InvariantViolation):
            assert_preproposal_not_red_and_accepted(
                state,
                final_decision=final_decision,
                accepted=accepted,
            )
    else:
        assert_preproposal_not_red_and_accepted(
            state,
            final_decision=final_decision,
            accepted=accepted,
        )


@settings(max_examples=40, deadline=None)
@given(final_decision=_FINAL_DECISIONS, accepted=st.booleans(), consolidated=st.booleans())
def test_property_hold_mode_blocks_acceptance_and_memory_consolidation(final_decision, accepted, consolidated):
    state = {
        "mode": "hold",
        "final_decision": "HOLD",
        "accepted": accepted,
        "memory_events": [{"consolidated": {"id": "m1"}}] if consolidated else [],
        "requested_final_decision": final_decision,
    }

    if accepted or consolidated:
        with pytest.raises(InvariantViolation):
            assert_hold_mode_blocks_all_mutations(state)
    else:
        assert_hold_mode_blocks_all_mutations(state)


@settings(max_examples=40, deadline=None)
@given(council_decision=_DECISIONS, final_decision=_FINAL_DECISIONS)
def test_property_council_red_never_softens_to_non_stop(council_decision, final_decision):
    final_result = {"final_decision": final_decision}
    should_raise = council_decision == "RED" and final_decision not in {"STOP", "REJECT", "ROLLBACK"}
    if should_raise:
        with pytest.raises(InvariantViolation):
            assert_council_red_always_leads_to_stop(council_decision, final_result)
    else:
        assert_council_red_always_leads_to_stop(council_decision, final_result)


@settings(max_examples=40, deadline=None)
@given(blocked=st.booleans(), dgm_allowed=st.booleans(), dgm_decision=_FINAL_DECISIONS)
def test_property_dgm_precheck_respects_preproposal_block(blocked, dgm_allowed, dgm_decision):
    block_state = {
        "mutation_blocked": blocked,
        "block_reason": "property_block" if blocked else "",
    }
    dgm_result = {
        "decision": dgm_decision,
        "terminal": not dgm_allowed,
        "patch": {"dgm_allowed": dgm_allowed},
    }
    should_raise = blocked and (
        dgm_allowed or dgm_decision in {"GO", "ACCEPT"} or not dgm_result["terminal"]
    )
    if should_raise:
        with pytest.raises(InvariantViolation):
            assert_dgm_precheck_respects_block(block_state, dgm_result)
    else:
        assert_dgm_precheck_respects_block(block_state, dgm_result)



@settings(max_examples=12, deadline=None)
@given(event_count=st.integers(min_value=25, max_value=75))
def test_property_event_chain_integrity_under_load(event_count):
    with tempfile.TemporaryDirectory() as tmp:
        store = AppendOnlyEventStore(path=f"{tmp}/events.jsonl")
        events = []
        for iteration in range(event_count):
            decision = "HOLD" if iteration % 7 == 0 else "GO"
            events.append(
                store.append(
                    RuntimeEvent(
                        event_type="phase.result",
                        phase="final_gate",
                        iteration=iteration,
                        payload={
                            "phase_result": {
                                "phase": "final_gate",
                                "decision": decision,
                                "reason": f"load_{iteration}",
                                "terminal": False,
                            },
                            "decision": decision,
                            "reason": f"load_{iteration}",
                            "terminal": False,
                        },
                    )
                )
            )
        ok, errors = store.verify()
        assert ok, errors
        assert len(events) == event_count
        for index, event in enumerate(events):
            assert event["sequence"] == index


@settings(max_examples=20, deadline=None)
@given(final_decision=_FINAL_DECISIONS, dgm_allowed=st.booleans())
def test_property_multistage_blockade_rejects_dgm_and_final_gate(final_decision, dgm_allowed):
    block = {
        "decision": "RED",
        "terminal": True,
        "patch": {"mutation_blocked": True, "block_reason": "property_multistage"},
    }
    dgm_result = {
        "decision": "PASS" if dgm_allowed else "REJECT",
        "terminal": not dgm_allowed,
        "patch": {"dgm_allowed": dgm_allowed},
    }
    final_result = {"final_decision": final_decision, "accepted": final_decision in {"GO", "ACCEPT"}}

    if dgm_allowed:
        with pytest.raises(InvariantViolation):
            assert_dgm_precheck_respects_block(block, dgm_result)
    else:
        assert_dgm_precheck_respects_block(block, dgm_result)

    if final_decision in {"GO", "ACCEPT"}:
        with pytest.raises(InvariantViolation):
            assert_final_gate_respects_blocked_state(block, final_result)
    else:
        assert_final_gate_respects_blocked_state(block, final_result)


@settings(max_examples=20, deadline=None)
@given(decision=_FINAL_DECISIONS, terminal=st.booleans())
def test_property_terminal_security_event_is_non_accepting(decision, terminal):
    event = {
        "event_type": "phase.result",
        "phase": "final_gate",
        "iteration": 0,
        "payload": {
            "phase_result": {
                "phase": "final_gate",
                "decision": decision,
                "reason": "property_terminal",
                "terminal": terminal,
            },
            "decision": decision,
            "terminal": terminal,
        },
    }
    if terminal and decision in {"GO", "ACCEPT"}:
        with pytest.raises(InvariantViolation):
            assert_terminal_security_event_is_non_accepting(event)
    else:
        assert_terminal_security_event_is_non_accepting(event)


@settings(max_examples=20, deadline=None)
@given(change_effective=st.booleans())
def test_property_blocked_record_effective_policy_unchanged(change_effective):
    record = {
        "mutation_blocked": True,
        "block_reason": "property_policy",
        "previous_policy": {"review": "required", "version": 1},
        "effective_policy": {"review": "skipped", "version": 2} if change_effective else {"review": "required", "version": 1},
    }
    if change_effective:
        with pytest.raises(InvariantViolation):
            assert_blocked_record_effective_policy_unchanged(record)
    else:
        assert_blocked_record_effective_policy_unchanged(record)


@settings(max_examples=20, deadline=None)
@given(missing_phase=st.sampled_from(["mutation_phase", "preproposal_adversarial_phase", "final_gate"]))
def test_property_event_refs_must_cover_phase_audit(missing_phase):
    phases = ["mutation_phase", "preproposal_adversarial_phase", "final_gate"]
    record = {
        "phase_audit": [
            {"audit_event_type": "phase_result", "phase": phase}
            for phase in phases
        ],
        "event_refs_v12": [
            {"event_type": "phase.result", "phase": phase, "event_hash": f"h-{phase}"}
            for phase in phases
            if phase != missing_phase
        ],
    }
    with pytest.raises(InvariantViolation):
        assert_event_refs_match_phase_audit(record)

    record["event_refs_v12"].append(
        {"event_type": "phase.result", "phase": missing_phase, "event_hash": f"h-{missing_phase}"}
    )
    assert_event_refs_match_phase_audit(record)


@settings(max_examples=15, deadline=None)
@given(reason=st.text(min_size=1, max_size=20))
def test_property_logging_integrity_for_critical_security_events(reason):
    with tempfile.TemporaryDirectory() as tmp:
        with _CaptureLogger("lrsi.security.eventsourcing", "lrsi.security.invariants") as captured:
            store = AppendOnlyEventStore(path=f"{tmp}/events.jsonl")
            event = store.append(
                RuntimeEvent(
                    event_type="phase.result",
                    phase="preproposal_adversarial_phase",
                    iteration=3,
                    trace_id="property-trace",
                    payload={
                        "phase_result": {
                            "phase": "preproposal_adversarial_phase",
                            "decision": "RED",
                            "reason": reason,
                            "terminal": True,
                            "mutation_blocked": True,
                        },
                        "patch": {"mutation_blocked": True, "block_reason": reason},
                        "decision": "RED",
                        "reason": reason,
                        "terminal": True,
                    },
                )
            )
            with pytest.raises(InvariantViolation):
                assert_final_gate_respects_blocked_state(
                    {"mutation_blocked": True, "block_reason": reason},
                    {"decision": "GO", "accepted": True},
                )

        messages = captured.text()
        assert "critical_event_committed" in messages
        assert "invariant_violation" in messages
        assert "property-trace" in messages
        assert event["event_hash"] in messages


@settings(max_examples=20, deadline=None)
@given(tamper_kind=st.sampled_from(["payload", "previous_hash", "event_hash"]))
def test_property_event_stream_tamper_attempts_are_detected(tamper_kind):
    with tempfile.TemporaryDirectory() as tmp:
        store = AppendOnlyEventStore(path=f"{tmp}/events.jsonl")
        events = [
            store.append(
                RuntimeEvent(
                    event_type="phase.result",
                    phase="preproposal_adversarial_phase",
                    iteration=0,
                    payload={
                        "phase_result": {
                            "phase": "preproposal_adversarial_phase",
                            "decision": "RED",
                            "reason": "tamper",
                            "terminal": True,
                            "mutation_blocked": True,
                        },
                        "patch": {"mutation_blocked": True, "block_reason": "tamper"},
                        "decision": "RED",
                        "reason": "tamper",
                        "terminal": True,
                    },
                )
            ),
            store.append(
                RuntimeEvent(
                    event_type="audit.iteration_record",
                    phase="persistence_phase",
                    iteration=0,
                    payload={"record": {"final_decision": "REJECT"}},
                )
            ),
        ]
        tampered = [dict(event) for event in events]
        if tamper_kind == "payload":
            tampered[0]["payload"] = dict(tampered[0]["payload"])
            tampered[0]["payload"]["reason"] = "tampered"
        elif tamper_kind == "previous_hash":
            tampered[1]["previous_event_hash"] = "a" * 64
        else:
            tampered[0]["event_hash"] = "b" * 64

        with pytest.raises(InvariantViolation):
            assert_event_chain_integrity_after_block(tampered, block_iteration=0)


@settings(max_examples=20, deadline=None)
@given(include_preproposal=st.booleans(), accept_block=st.booleans(), change_policy=st.booleans())
def test_property_simultaneous_invariant_violations_are_independently_detected(
    include_preproposal, accept_block, change_policy
):
    record = {
        "prompt_meta": {"new_prompt": "property"},
        "policy_meta": {"new_policy": {"review": "skipped"}},
        "phase_audit": [{"audit_event_type": "phase_result", "phase": "mutation_phase"}],
        "mutation_blocked": True,
        "block_reason": "multi",
        "previous_policy": {"review": "required"},
        "effective_policy": {"review": "skipped"} if change_policy else {"review": "required"},
        "final_decision": "GO" if accept_block else "REJECT",
        "accepted": accept_block,
    }
    if include_preproposal:
        record["phase_audit"].append(
            {"audit_event_type": "phase_result", "phase": "preproposal_adversarial_phase"}
        )

    violations = 0
    for check in (
        lambda: assert_no_mutation_without_preproposal_check(record),
        lambda: assert_final_gate_respects_blocked_state(record, record),
        lambda: assert_blocked_record_effective_policy_unchanged(record),
    ):
        try:
            check()
        except InvariantViolation:
            violations += 1

    expected = (0 if include_preproposal else 1) + (1 if accept_block else 0) + (1 if change_policy else 0)
    assert violations == expected
