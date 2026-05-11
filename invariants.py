"""
Central safety invariants for the LRSI runtime.

These guards are intentionally small and dependency-light so they can be
called from phase code, storage, tests, benchmark harnesses, and future
review tools. Violations are logged as structured security events and then
raised as InvariantViolation exceptions.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from security_errors import LRSISecurityError


SECURITY_LEVEL = 35
AUDIT_LEVEL = 25
logging.addLevelName(SECURITY_LEVEL, "SECURITY")
logging.addLevelName(AUDIT_LEVEL, "AUDIT")

LOGGER = logging.getLogger("lrsi.security.invariants")
LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False


class InvariantViolation(LRSISecurityError):
    """Raised when a central LRSI safety invariant is violated."""

    def __init__(self, code: str, message: str | None = None, *, context: Mapping[str, Any] | None = None):
        super().__init__(code, message or code, context=context)


_ACCEPT_DECISIONS = {"ACCEPT", "ACCEPTED", "GO", "PASS", "PERSISTED"}
_SAFE_STOP_DECISIONS = {"STOP", "REJECT", "REJECTED", "RED", "ROLLBACK"}
_SAFE_NON_ACCEPT_DECISIONS = _SAFE_STOP_DECISIONS | {"HOLD", "REVIEW", "YELLOW", "BLOCKED"}
_MUTATION_KEYS = {
    "prompt_meta",
    "policy_meta",
    "prompt_mutation",
    "policy_mutation",
    "candidate_policy",
    "selfmod_mutation_v11_5",
}
_PREPROPOSAL_PHASE = "preproposal_adversarial_phase"


def _safe_context(value: Any, *, max_text: int = 4000) -> Any:
    """Return a logging-safe, bounded JSON-like representation."""

    if value is None or isinstance(value, (str, int, float, bool)):
        text = value
        if isinstance(text, str) and len(text) > max_text:
            return text[:max_text] + "...<truncated>"
        return text
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            skey = str(key)
            if skey.lower() in {"api_key", "token", "secret", "password", "private_key"}:
                safe[skey] = "<redacted>"
            else:
                safe[skey] = _safe_context(item, max_text=max_text)
        return safe
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        rendered = [_safe_context(item, max_text=max_text) for item in items[:25]]
        if len(items) > 25:
            rendered.append(f"...<{len(items)-25} more>")
        return rendered
    if hasattr(value, "to_dict"):
        try:
            return _safe_context(value.to_dict(), max_text=max_text)
        except Exception:
            pass
    return {"__non_json_type__": type(value).__name__, "repr": repr(value)[:max_text]}


def _log_security_event(event: str, *, level: int = logging.INFO, **context: Any) -> None:
    payload = {
        "security_event": event,
        "component": "invariants",
        "context": _safe_context(context),
    }
    LOGGER.log(level, json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


def _raise_violation(code: str, message: str, **context: Any) -> None:
    _log_security_event(
        "invariant_violation",
        level=SECURITY_LEVEL,
        invariant=code,
        message=message,
        **context,
    )
    raise InvariantViolation(code, message, context=context)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _patch(obj: Any) -> Mapping[str, Any]:
    patch = _get(obj, "patch", {})
    return patch if isinstance(patch, Mapping) else {}


def _diagnostics(obj: Any) -> Mapping[str, Any]:
    diagnostics = _get(obj, "diagnostics", {})
    return diagnostics if isinstance(diagnostics, Mapping) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "blocked"}
    return bool(value)


def _phase_audit(obj: Any) -> list[dict[str, Any]]:
    audit = _get(obj, "phase_audit", [])
    if isinstance(audit, list):
        return [entry for entry in audit if isinstance(entry, Mapping)]
    return []


def _phase_names(obj: Any) -> set[str]:
    return {str(entry.get("phase")) for entry in _phase_audit(obj) if entry.get("phase")}


def _is_mutation_present(state: Any) -> bool:
    if any(_get(state, key) not in (None, {}, [], "") for key in _MUTATION_KEYS):
        return True
    return "mutation_phase" in _phase_names(state)


def _has_preproposal_check(state: Any) -> bool:
    return (
        _get(state, "selfmod_preproposal_v11_5") not in (None, {}, [], "")
        or _get(state, "preproposal_adversarial") not in (None, {}, [], "")
        or _PREPROPOSAL_PHASE in _phase_names(state)
    )


def _is_blocked(state: Any) -> bool:
    patch = _patch(state)
    return (
        _truthy(patch.get("mutation_blocked"))
        or _truthy(_get(state, "mutation_blocked", False))
        or _truthy(_diagnostics(state).get("mutation_blocked", False))
    )


def _block_reason(state: Any) -> str:
    return str(
        _patch(state).get("block_reason")
        or _get(state, "block_reason", "")
        or _diagnostics(state).get("block_reason", "")
        or ""
    )


def _decision_from(result: Any, *keys: str) -> str:
    for key in keys:
        value = _get(result, key)
        if value not in (None, ""):
            return _upper(value)
    diagnostics = _diagnostics(result)
    for key in keys:
        value = diagnostics.get(key)
        if value not in (None, ""):
            return _upper(value)
    return ""


def _is_red_preproposal(preproposal_result: Any) -> bool:
    patch = _patch(preproposal_result)
    diagnostics = _diagnostics(preproposal_result)
    decision = _upper(
        _get(preproposal_result, "decision")
        or diagnostics.get("decision")
        or _get(preproposal_result, "max_severity")
        or diagnostics.get("max_severity")
    )
    max_severity = _upper(
        _get(preproposal_result, "max_severity")
        or diagnostics.get("max_severity")
        or _get(_get(preproposal_result, "preproposal_adversarial", {}), "max_severity")
        or _get(diagnostics.get("preproposal_adversarial", {}), "max_severity")
    )
    return (
        decision == "RED"
        or max_severity == "RED"
        or _truthy(patch.get("mutation_blocked"))
        or _truthy(_get(preproposal_result, "mutation_blocked", False))
    )


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash_event_payload(event: Mapping[str, Any]) -> str:
    payload = dict(event)
    payload.pop("event_hash", None)
    payload.pop("event_signature", None)
    payload.pop("event_signature_algorithm", None)
    payload.pop("event_signer_id", None)
    payload.pop("event_public_key_b64", None)
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _event_payload(event: Any) -> Mapping[str, Any]:
    payload = _get(event, "payload", {})
    return payload if isinstance(payload, Mapping) else {}


def _phase_result_payload(event: Any) -> Mapping[str, Any]:
    payload = _event_payload(event)
    phase_result = payload.get("phase_result")
    return phase_result if isinstance(phase_result, Mapping) else {}


def _event_is_blocked(event: Any) -> bool:
    payload = _event_payload(event)
    phase_result = _phase_result_payload(event)
    patch = payload.get("patch") if isinstance(payload.get("patch"), Mapping) else {}
    return (
        _truthy(payload.get("mutation_blocked"))
        or _truthy(patch.get("mutation_blocked"))
        or _truthy(phase_result.get("mutation_blocked"))
        or (
            str(_get(event, "phase", phase_result.get("phase", ""))) == _PREPROPOSAL_PHASE
            and _upper(phase_result.get("decision") or payload.get("decision")) == "RED"
            and _truthy(phase_result.get("terminal") or payload.get("terminal"))
        )
    )


# Existing Sprint 1 invariants -------------------------------------------------

def assert_preproposal_not_red_and_accepted(
    preproposal_result: Any,
    final_decision: Any = None,
    *,
    accepted: bool | None = None,
) -> None:
    """RED pre-proposal diagnostics must never coexist with acceptance."""

    if not _is_red_preproposal(preproposal_result):
        return

    final = _upper(final_decision or _get(preproposal_result, "final_decision"))
    accepted_flag = (
        bool(accepted)
        if accepted is not None
        else bool(_get(preproposal_result, "accepted", False))
    )
    if accepted_flag or final in _ACCEPT_DECISIONS:
        _raise_violation(
            "preproposal_red_must_not_be_accepted",
            "RED pre-proposal state cannot coexist with acceptance",
            final_decision=final or "UNKNOWN",
            accepted=accepted_flag,
            preproposal_result=preproposal_result,
        )


def assert_mutation_blocked_has_terminal(result: Any) -> None:
    """A mutation_blocked result must be terminal."""

    blocked = _is_blocked(result)
    if not blocked:
        return

    if not bool(_get(result, "terminal", False)):
        _raise_violation(
            "mutation_blocked_requires_terminal",
            "mutation_blocked=True must set terminal=True",
            result=result,
        )


def assert_dgm_precheck_respects_block(block_state: Any, dgm_precheck_result: Any | None = None) -> None:
    """DGM pre-check must not pass a mutation that was already blocked."""

    if not _is_blocked(block_state):
        return
    if dgm_precheck_result is None:
        return

    patch = _patch(dgm_precheck_result)
    diagnostics = _diagnostics(dgm_precheck_result)
    allowed = bool(
        _get(dgm_precheck_result, "allowed", False)
        or patch.get("dgm_allowed", False)
        or diagnostics.get("allowed", False)
    )
    decision = _upper(_get(dgm_precheck_result, "decision", diagnostics.get("decision")))
    terminal = bool(_get(dgm_precheck_result, "terminal", False))

    if allowed or decision in _ACCEPT_DECISIONS or not terminal:
        _raise_violation(
            "dgm_precheck_must_respect_preproposal_block",
            "blocked mutations must not pass DGM pre-check and must remain terminal",
            block_state=block_state,
            dgm_precheck_result=dgm_precheck_result,
        )


# Sprint 2 invariants ----------------------------------------------------------

def assert_no_mutation_without_preproposal_check(state: Any) -> None:
    """A mutation-bearing state must include a pre-proposal adversarial check."""

    if _is_mutation_present(state) and not _has_preproposal_check(state):
        _raise_violation(
            "no_mutation_without_preproposal_check",
            "mutation state is missing pre-proposal adversarial coverage",
            phase_audit=_phase_audit(state),
            mutation_keys=[key for key in _MUTATION_KEYS if _get(state, key) not in (None, {}, [], "")],
            state_summary=state,
        )


def assert_final_gate_respects_blocked_state(block_state: Any, final_gate_result: Any | None = None) -> None:
    """A blocked mutation must not be converted to GO/ACCEPT by the final gate."""

    if not _is_blocked(block_state):
        return
    if final_gate_result is None:
        return

    final = (
        _decision_from(final_gate_result, "final_decision", "decision", "ext_decision", "gate_decision")
        or _upper(_patch(final_gate_result).get("ext_decision"))
    )
    accepted = bool(_get(final_gate_result, "accepted", False) or _patch(final_gate_result).get("accepted", False))
    if accepted or final in _ACCEPT_DECISIONS:
        _raise_violation(
            "final_gate_must_respect_blocked_state",
            "blocked mutation cannot be accepted by final gate",
            block_state=block_state,
            final_gate_result=final_gate_result,
            final_decision=final or "UNKNOWN",
            accepted=accepted,
        )


def assert_event_chain_integrity_after_block(
    events: Iterable[Mapping[str, Any]],
    *,
    block_iteration: int | None = None,
) -> None:
    """If a block event exists, the committed event chain must verify."""

    event_list = [dict(event) for event in events]
    blocked_events = [
        event
        for event in event_list
        if _event_is_blocked(event)
        and (block_iteration is None or event.get("iteration") == block_iteration)
    ]
    if not blocked_events:
        _raise_violation(
            "blocked_state_requires_event_coverage",
            "no committed blocked phase event was found for a blocked state",
            block_iteration=block_iteration,
            event_count=len(event_list),
        )

    previous = "0" * 64
    errors: list[str] = []
    for index, event in enumerate(event_list):
        if event.get("previous_event_hash") != previous:
            errors.append(f"event[{index}].previous_event_hash mismatch")
        expected_hash = _hash_event_payload(event)
        if event.get("event_hash") != expected_hash:
            errors.append(f"event[{index}].event_hash mismatch")
        previous = event.get("event_hash", previous)

    if errors:
        _raise_violation(
            "event_chain_integrity_after_block",
            "event chain verification failed after a blocked mutation",
            errors=errors,
            block_iteration=block_iteration,
            blocked_event_count=len(blocked_events),
        )


def assert_hold_mode_blocks_all_mutations(state: Any) -> None:
    """HOLD states may retain diagnostics, but must not apply mutations."""

    mode = _upper(_get(state, "mode") or _get(state, "governance_mode"))
    final = _decision_from(state, "final_decision", "gate_decision", "decision")
    hold_state = mode == "HOLD" or final == "HOLD"
    if not hold_state:
        return

    accepted = bool(_get(state, "accepted", False))
    memory_events = _get(state, "memory_events", []) or []
    consolidated_memory = [
        event for event in memory_events
        if isinstance(event, Mapping) and event.get("consolidated")
    ]
    if accepted or final in {"GO", "ACCEPT", "ACCEPTED"} or consolidated_memory:
        _raise_violation(
            "hold_mode_blocks_all_mutations",
            "HOLD state cannot apply candidate mutation or consolidate memory",
            mode=mode,
            final_decision=final,
            accepted=accepted,
            consolidated_memory_count=len(consolidated_memory),
            state=state,
        )


def assert_council_red_always_leads_to_stop(council_decision: Any, final_gate_result: Any | None = None) -> None:
    """Council RED is a hard veto and must lead to STOP/REJECT/ROLLBACK semantics."""

    if _upper(council_decision) != "RED":
        return
    if final_gate_result is None:
        return

    final = _decision_from(final_gate_result, "final_decision", "decision", "ext_decision", "gate_decision")
    if final not in _SAFE_STOP_DECISIONS:
        _raise_violation(
            "council_red_always_leads_to_stop",
            "council RED must not be softened into GO/HOLD/ACCEPT",
            council_decision=council_decision,
            final_decision=final or "UNKNOWN",
            final_gate_result=final_gate_result,
        )



def assert_terminal_security_event_is_non_accepting(event: Any) -> None:
    """Terminal phase events must not carry accepting decisions.

    A terminal event represents an interruption boundary.  It may STOP,
    REJECT, ROLLBACK, HOLD, or REVIEW, but it must never encode GO/ACCEPT.
    """

    payload = _event_payload(event)
    phase_result = _phase_result_payload(event)
    terminal = bool(
        _get(event, "terminal", False)
        or payload.get("terminal")
        or phase_result.get("terminal")
    )
    if not terminal:
        return

    decision = _upper(
        _get(event, "decision")
        or payload.get("decision")
        or phase_result.get("decision")
    )
    if decision in _ACCEPT_DECISIONS:
        _raise_violation(
            "terminal_security_event_must_not_accept",
            "terminal security event cannot carry GO/ACCEPT semantics",
            event_data=event,
            decision=decision,
        )


def assert_blocked_record_effective_policy_unchanged(record: Any) -> None:
    """A blocked mutation must not change the effective policy."""

    if not _is_blocked(record):
        return
    previous_policy = _get(record, "previous_policy")
    effective_policy = _get(record, "effective_policy")
    if previous_policy is None or effective_policy is None:
        return
    if previous_policy != effective_policy:
        _raise_violation(
            "blocked_record_effective_policy_must_remain_previous",
            "blocked mutation changed effective_policy despite blocked state",
            previous_policy=previous_policy,
            effective_policy=effective_policy,
            record=record,
        )


def assert_event_refs_match_phase_audit(record: Any) -> None:
    """Materialized event references must cover every phase_audit phase."""

    phase_names = [
        str(entry.get("phase"))
        for entry in _phase_audit(record)
        if entry.get("audit_event_type") in {None, "phase_result"} and entry.get("phase")
    ]
    event_refs = _get(record, "event_refs_v12", []) or _get(record, "events_v12", []) or []
    if not phase_names or not event_refs:
        return
    ref_phases = {
        str(ref.get("phase"))
        for ref in event_refs
        if isinstance(ref, Mapping) and ref.get("event_type") == "phase.result" and ref.get("phase")
    }
    missing = [phase for phase in phase_names if phase not in ref_phases]
    if missing:
        _raise_violation(
            "event_refs_must_cover_phase_audit",
            "materialized event references do not cover all phase_audit phases",
            missing_phases=missing,
            phase_audit_phases=phase_names,
            event_ref_phases=sorted(ref_phases),
        )
