from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from audit_sinks import AuditSealService, LocalWORMDirectorySink
from security_errors import LRSISecurityError
from eventsourcing import (
    AppendOnlyEventStore,
    RuntimeEvent,
    event_reference,
    json_byte_size,
    json_safe,
    payload_sha256,
    production_mode_enabled,
    project_events,
    replay_decisions,
    validate_event_store_production_config,
)
from invariants import (
    assert_council_red_always_leads_to_stop,
    assert_event_chain_integrity_after_block,
    assert_final_gate_respects_blocked_state,
    assert_hold_mode_blocks_all_mutations,
    assert_no_mutation_without_preproposal_check,
    assert_blocked_record_effective_policy_unchanged,
    assert_event_refs_match_phase_audit,
)
from signing import adapter_from_env, verify_signature_payload
from version import SCHEMA_VERSION

GENESIS_HASH = "0" * 64


SECURITY_LEVEL = 35
AUDIT_LEVEL = 25
logging.addLevelName(SECURITY_LEVEL, "SECURITY")
logging.addLevelName(AUDIT_LEVEL, "AUDIT")

SECURITY_LOGGER = logging.getLogger("lrsi.security.storage")
SECURITY_LOGGER.addHandler(logging.NullHandler())
SECURITY_LOGGER.propagate = False


def _structured_security_log(event_name: str, *, level: int = logging.INFO, **context) -> None:
    payload = {
        "security_event": event_name,
        "component": "storage",
        "context": json_safe(context),
    }
    SECURITY_LOGGER.log(level, json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


def _record_security_context(record: dict) -> dict:
    return {
        "iteration": record.get("iteration"),
        "trace_id": record.get("trace_id"),
        "mode": record.get("mode"),
        "gate_decision": record.get("gate_decision"),
        "gate_reason": record.get("gate_reason"),
        "final_decision": record.get("final_decision"),
        "accepted": record.get("accepted"),
        "mutation_blocked": record.get("mutation_blocked"),
        "block_reason": record.get("block_reason"),
        "record_hash": record.get("record_hash"),
        "previous_record_hash": record.get("previous_record_hash"),
        "phase_audit_count": len(record.get("phase_audit", []) or []),
        "event_ref_count": len(record.get("event_refs_v12", []) or []),
        "schema_version": record.get("schema_version"),
        "run_id": record.get("run_id"),
    }


def _record_is_critical(record: dict) -> bool:
    decision = str(record.get("final_decision") or record.get("gate_decision") or "").upper()
    return (
        bool(record.get("mutation_blocked"))
        or bool(record.get("block_reason"))
        or decision in {"RED", "STOP", "HOLD", "REJECT", "ROLLBACK"}
        or str(record.get("gate_reason", "")).startswith("preproposal:")
    )


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def file_lock(path):
    """Best-effort inter-process lock for local prototype persistence."""
    lock_path = f"{path}.lock"
    directory = os.path.dirname(os.path.abspath(lock_path)) or "."
    os.makedirs(directory, exist_ok=True)
    lock_fh = open(lock_path, "a+", encoding="utf-8")
    try:
        try:
            import fcntl  # POSIX only
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
        lock_fh.close()


def atomic_write_json(path, data):
    """Write JSON atomically via same-directory temporary file."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = os.path.join(directory, f".{os.path.basename(path)}.{uuid.uuid4().hex}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp_path, path)


def canonical_json(data) -> str:
    """Stable JSON serialization used for audit hash chaining."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def record_hash(record: dict) -> str:
    """Compute a stable SHA-256 hash over a record-like dictionary."""
    payload = dict(record)
    payload.pop("record_hash", None)
    payload.pop("audit_signature", None)
    payload.pop("audit_signature_algorithm", None)
    payload.pop("audit_signer_id", None)
    payload.pop("audit_public_key_b64", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def audit_signature(record_hash_value: str, *, key: str) -> str:
    """Legacy HMAC helper retained for compatibility with V11.0 tests."""
    import hmac as _hmac

    return _hmac.new(
        key.encode("utf-8"),
        record_hash_value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_audit_signature(record: dict, *, key: str | None = None) -> bool:
    """Verify either legacy HMAC or V11.1 Ed25519 audit signatures."""
    if not record.get("record_hash"):
        return False
    return verify_signature_payload(record["record_hash"], record, key=key)


def _enrich_record(record: dict, *, run_id: str, previous_hash: str) -> dict:
    enriched = json_safe(dict(record))
    enriched.setdefault("schema_version", SCHEMA_VERSION)
    enriched.setdefault("run_id", run_id)
    enriched.setdefault("created_at", utc_now_iso())
    enriched.setdefault("audit_event_type", "iteration_record")
    enriched["previous_record_hash"] = previous_hash
    enriched["record_hash"] = record_hash(enriched)
    signing_adapter = adapter_from_env()
    if signing_adapter:
        enriched.update(signing_adapter.public_metadata())
        enriched["audit_signature"] = signing_adapter.sign(
            enriched["record_hash"].encode("utf-8")
        )
    return enriched


def verify_hash_chain(
    records: list[dict],
    *,
    allow_legacy_unhashed: bool = False,
    require_signature: bool = False,
    signature_key: str | None = None,
) -> tuple[bool, list[str]]:
    """Verify append-order hash chain over a list of audit records.

    V11.0 is strict by default: every audit record must contain both
    ``previous_record_hash`` and ``record_hash``.  Earlier prototype records can
    still be inspected with ``allow_legacy_unhashed=True``, but production-like
    verification must fail closed on missing hash fields.  If
    ``require_signature`` is true, each record must also carry a valid HMAC
    signature.  ``signature_key`` defaults to ``AUDIT_HMAC_KEY``.
    """
    errors: list[str] = []
    previous = GENESIS_HASH
    for idx, rec in enumerate(records):
        has_record_hash = "record_hash" in rec
        has_previous_hash = "previous_record_hash" in rec
        if not has_record_hash or not has_previous_hash:
            if allow_legacy_unhashed:
                previous = rec.get("record_hash", previous)
                continue
            if not has_previous_hash:
                errors.append(f"record[{idx}].previous_record_hash missing")
            if not has_record_hash:
                errors.append(f"record[{idx}].record_hash missing")
            continue
        expected_prev = rec.get("previous_record_hash")
        if expected_prev != previous:
            errors.append(f"record[{idx}].previous_record_hash mismatch")
        expected_hash = record_hash(rec)
        if rec.get("record_hash") != expected_hash:
            errors.append(f"record[{idx}].record_hash mismatch")
        if require_signature:
            key = signature_key or os.getenv("AUDIT_HMAC_KEY")
            if not rec.get("audit_signature"):
                errors.append(f"record[{idx}].audit_signature missing")
            elif not verify_audit_signature(rec, key=key):
                errors.append(f"record[{idx}].audit_signature invalid")
        previous = rec.get("record_hash", previous)
    return not errors, errors


class AuditBackend(Protocol):
    """Minimal append/load contract for audit persistence backends."""

    path: str
    run_id: str

    def append(self, record: dict) -> dict: ...

    def load(self) -> list[dict]: ...


@dataclass
class JSONAuditBackend:
    """Development backend: materialized JSON list with atomic rewrite.

    This is the default because it preserves legacy test readability.  It is not
    a production audit store; use AppendOnlyAuditBackend or an external sink for
    stronger audit semantics.
    """

    path: str = "run_log.json"
    run_id: str = ""

    def __post_init__(self):
        if not self.run_id:
            self.run_id = f"run-{uuid.uuid4().hex[:12]}"
        with file_lock(self.path):
            if not os.path.exists(self.path):
                atomic_write_json(self.path, [])

    def load(self) -> list[dict]:
        with file_lock(self.path):
            return self._load_unlocked()

    def _load_unlocked(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Storage log must be a list, got {type(data).__name__}")
        return data

    def append(self, record: dict) -> dict:
        with file_lock(self.path):
            data = self._load_unlocked()
            previous_hash = data[-1].get("record_hash", GENESIS_HASH) if data else GENESIS_HASH
            enriched = _enrich_record(record, run_id=self.run_id, previous_hash=previous_hash)
            data.append(enriched)
            atomic_write_json(self.path, data)
            return enriched


@dataclass
class AppendOnlyAuditBackend:
    """Append-only JSONL backend for stronger local audit semantics.

    Each call writes exactly one JSON line.  A companion materialized JSON path
    can be used by legacy tooling, but the authoritative target is the JSONL
    append log.  This is still local and unsigned; production should bind it to
    reviewer identity/signatures and an independent sink.
    """

    path: str = "run_log.jsonl"
    run_id: str = ""
    materialized_json_path: str | None = None

    def __post_init__(self):
        if not self.run_id:
            self.run_id = f"run-{uuid.uuid4().hex[:12]}"
        with file_lock(self.path):
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.path).touch(exist_ok=True)
            if self.materialized_json_path and not os.path.exists(self.materialized_json_path):
                atomic_write_json(self.materialized_json_path, [])

    def load(self) -> list[dict]:
        with file_lock(self.path):
            return self._load_unlocked()

    def _load_unlocked(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def append(self, record: dict) -> dict:
        with file_lock(self.path):
            data = self._load_unlocked()
            previous_hash = data[-1].get("record_hash", GENESIS_HASH) if data else GENESIS_HASH
            enriched = _enrich_record(record, run_id=self.run_id, previous_hash=previous_hash)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(canonical_json(enriched) + "\n")
            if self.materialized_json_path:
                materialized = data + [enriched]
                atomic_write_json(self.materialized_json_path, materialized)
            return enriched


class Storage:
    """Compatibility facade over pluggable audit backends.

    V12.0 adds an append-only event store beside the materialized iteration
    record log.  ``run_log.json`` remains a compatibility view, but the
    ``*.events.jsonl`` stream is the primary replay substrate.
    """

    def __init__(self, path="run_log.json", *, backend: AuditBackend | None = None,
                 backend_mode: str | None = None, event_store=None,
                 event_store_path: str | None = None, production_mode: bool | None = None):
        mode = str(backend_mode or os.getenv("AUDIT_BACKEND", "json") or "json").lower().strip()
        if backend is not None:
            self.backend = backend
        elif mode in {"append", "append-only", "append_only", "jsonl"}:
            jsonl_path = path if str(path).endswith(".jsonl") else f"{path}.jsonl"
            self.backend = AppendOnlyAuditBackend(
                path=jsonl_path,
                materialized_json_path=path if not str(path).endswith(".jsonl") else None,
            )
        elif mode in {"json", "dev"}:
            self.backend = JSONAuditBackend(path=path)
        else:
            raise ValueError("AUDIT_BACKEND must be one of: json, append-only")
        self.path = self.backend.path if str(self.backend.path).endswith(".jsonl") else path
        self.run_id = self.backend.run_id
        worm_dir = os.getenv("AUDIT_WORM_DIR")
        external_sink = LocalWORMDirectorySink(worm_dir) if worm_dir else None
        prod_enabled = production_mode_enabled(production_mode)
        if event_store is not None:
            if prod_enabled:
                if not production_mode_enabled(getattr(event_store, "production_mode", False)):
                    raise LRSISecurityError(
                        "production_storage_requires_production_event_store",
                        "production storage requires injected event_store.production_mode=True",
                        context={"event_store_type": type(event_store).__name__},
                    )
                validate_event_store_production_config(
                    signing_adapter=getattr(event_store, "signing_adapter", None),
                    external_sink=getattr(event_store, "external_sink", None),
                )
                ok, errors = event_store.verify(require_signature=True)
                if not ok:
                    raise LRSISecurityError(
                        "production_injected_event_store_verification_failed",
                        "production injected event store failed verification",
                        context={"errors": errors},
                    )
            self.event_store = event_store
        else:
            self.event_store = AppendOnlyEventStore(
                path=event_store_path or f"{path}.events.jsonl",
                stream_id=self.run_id,
                external_sink=external_sink,
                production_mode=production_mode,
            )

    @staticmethod
    def _phase_event_key(event: dict) -> tuple:
        payload = event.get("payload", {}) or {}
        phase_result = payload.get("phase_result", {}) or {}
        return (
            event.get("iteration") if event.get("iteration") is not None else phase_result.get("iteration"),
            event.get("phase") or phase_result.get("phase"),
            phase_result.get("decision") or payload.get("decision"),
            phase_result.get("reason") or payload.get("reason"),
        )

    @staticmethod
    def _record_event_summary(record: dict) -> dict:
        """Return a small replay-safe summary for audit.iteration_record events.

        The materialized record remains hash-chained in the legacy backend.  The
        canonical V12 event stream only needs a bounded summary plus the full
        record hash, otherwise the event stream recursively embeds the materialized
        view and grows super-linearly.
        """
        evidence_bundle = record.get("evidence_bundle") if isinstance(record.get("evidence_bundle"), dict) else {}
        summary = {
            "schema_version": record.get("schema_version", SCHEMA_VERSION),
            "audit_event_type": "iteration_record_summary",
            "run_id": record.get("run_id"),
            "iteration": record.get("iteration"),
            "trace_id": record.get("trace_id"),
            "created_at": record.get("created_at"),
            "final_decision": record.get("final_decision"),
            "accepted": record.get("accepted"),
            "record_hash": record.get("record_hash"),
            "previous_record_hash": record.get("previous_record_hash"),
            "phase_audit_count": len(record.get("phase_audit", []) or []),
            "event_refs_v12": list(record.get("event_refs_v12", []) or []),
            "evidence_bundle": {
                "evidence_bundle_hash": evidence_bundle.get("evidence_bundle_hash"),
                "case_id": evidence_bundle.get("case_id"),
            },
            "materialized_record_ref": {
                "sha256": payload_sha256(record),
                "bytes": json_byte_size(record),
            },
        }
        return {k: v for k, v in summary.items() if v is not None}

    def _complete_phase_events_from_audit(self, record: dict) -> list[dict]:
        """Return V12 phase events, backfilling any phase_audit-only entries.

        Terminal paths historically persisted records before the PhaseExecutor
        could append ``ctx.phase_events_v12``.  V12 makes the event stream the
        canonical substrate, so persistence must fail closed by reconstructing
        missing ``phase.result`` events from hash-protected ``phase_audit``
        entries before writing either the event stream or materialized record.
        """
        events = [dict(e) for e in list(record.get("events_v12", []) or [])]
        seen = {self._phase_event_key(e) for e in events if (e.get("event_type") == "phase.result")}
        iteration = record.get("iteration")
        trace_id = record.get("trace_id")
        for audit_entry in list(record.get("phase_audit", []) or []):
            if not isinstance(audit_entry, dict) or audit_entry.get("audit_event_type") != "phase_result":
                continue
            phase = audit_entry.get("phase")
            key = (
                audit_entry.get("iteration", iteration),
                phase,
                audit_entry.get("decision"),
                audit_entry.get("reason"),
            )
            if key in seen:
                continue
            event = RuntimeEvent(
                event_type="phase.result",
                phase=phase,
                iteration=audit_entry.get("iteration", iteration),
                trace_id=audit_entry.get("trace_id", trace_id),
                stream_id=f"iteration-{audit_entry.get('iteration', iteration)}",
                payload={
                    "phase_result": json_safe(audit_entry),
                    "patch": {},
                    "decision": json_safe(audit_entry.get("decision")),
                    "reason": json_safe(audit_entry.get("reason", "")),
                    "terminal": bool(audit_entry.get("terminal", False)),
                },
            ).to_dict()
            events.append(event)
            seen.add(key)
        return events

    def log_iteration(self, record):
        # Persist phase events before the materialized iteration record so the
        # event stream can replay how the decision was reached.  P0 hardening:
        # backfill events from phase_audit so terminal/review paths cannot skip
        # the canonical event stream.
        #
        # P1 hardening: do not persist provisional pre-append events in the
        # materialized record.  Append returns the canonical sequence/hash; the
        # record stores only compact references to those committed events.
        record = dict(record)
        _structured_security_log(
            "iteration_persist_started",
            record_context=_record_security_context(record),
        )
        # Sprint 2/4: fail closed on central safety-invariant violations before
        # materialized records or audit events are committed.  Central handling
        # logs the record context once in storage in addition to the invariant
        # namespace log emitted by the invariant itself.
        try:
            assert_no_mutation_without_preproposal_check(record)
            assert_final_gate_respects_blocked_state(record, record)
            assert_hold_mode_blocks_all_mutations(record)
            assert_council_red_always_leads_to_stop(record.get("council_decision"), record)
            assert_blocked_record_effective_policy_unchanged(record)
        except LRSISecurityError as exc:
            _structured_security_log(
                "security_invariant_precommit_failed",
                level=SECURITY_LEVEL,
                security_code=getattr(exc, "code", type(exc).__name__),
                error=str(exc),
                record_context=_record_security_context(record),
                invariant_context=getattr(exc, "context", {}),
            )
            raise

        completed_events = self._complete_phase_events_from_audit(record)
        committed_events = [self.event_store.append(raw_event) for raw_event in completed_events]
        event_refs = [event_reference(event) for event in committed_events]
        record["event_refs_v12"] = event_refs
        # Backward-compatible field name, intentionally compact reference-shaped.
        record["events_v12"] = event_refs
        try:
            assert_event_refs_match_phase_audit(record)
        except LRSISecurityError as exc:
            _structured_security_log(
                "security_event_ref_invariant_failed",
                level=SECURITY_LEVEL,
                security_code=getattr(exc, "code", type(exc).__name__),
                error=str(exc),
                record_context=_record_security_context(record),
                invariant_context=getattr(exc, "context", {}),
            )
            raise
        persisted = self.backend.append(record)
        audit_event = self.event_store.append(RuntimeEvent(
            event_type="audit.iteration_record",
            phase="persistence_phase",
            iteration=persisted.get("iteration"),
            trace_id=persisted.get("trace_id"),
            stream_id=self.run_id,
            payload={"record": self._record_event_summary(persisted)},
        ))
        _structured_security_log(
            "iteration_persisted",
            record_context=_record_security_context(persisted),
            committed_event_count=len(committed_events),
            audit_event_ref=event_reference(audit_event),
        )
        if _record_is_critical(persisted):
            rc = _record_security_context(persisted)
            _structured_security_log(
                "critical_decision_persisted",
                level=SECURITY_LEVEL,
                trace_id=rc.get("trace_id"),
                iteration=rc.get("iteration"),
                decision=rc.get("final_decision"),
                gate_decision=rc.get("gate_decision"),
                gate_reason=rc.get("gate_reason"),
                record_hash=rc.get("record_hash"),
                previous_record_hash=rc.get("previous_record_hash"),
                record_context=rc,
                event_refs=event_refs,
            )
        if persisted.get("mutation_blocked"):
            events = self.event_store.load()
            assert_event_chain_integrity_after_block(
                events,
                block_iteration=persisted.get("iteration"),
            )
            rc = _record_security_context(persisted)
            _structured_security_log(
                "blocked_mutation_event_chain_verified",
                level=SECURITY_LEVEL,
                trace_id=rc.get("trace_id"),
                iteration=rc.get("iteration"),
                decision=rc.get("final_decision"),
                block_reason=rc.get("block_reason"),
                record_hash=rc.get("record_hash"),
                record_context=rc,
                event_count=len(events),
            )
        return persisted

    def load(self) -> list[dict]:
        return self.backend.load()

    def load_events(self) -> list[dict]:
        return self.event_store.load()

    def verify_event_chain(self, *, require_signature: bool = False) -> tuple[bool, list[str]]:
        return self.event_store.verify(require_signature=require_signature)

    def project_events(self) -> dict:
        return project_events(self.load_events())

    def replay_decisions(self) -> dict:
        return replay_decisions(self.load_events())

    def seal_sequence(self, *, external_sink=None, signing_adapter=None, sequence_id: str | None = None) -> dict:
        """Create a Merkle seal over the current audit sequence.

        The seal can be written to any ``ExternalAuditSink`` implementation.
        This is the V11.1 bridge from local hash chaining toward WORM/external
        audit infrastructure.
        """
        service = AuditSealService(
            signing_adapter=signing_adapter or adapter_from_env(),
            external_sink=external_sink,
        )
        materialized_seal = service.seal(self.load(), sequence_id=sequence_id).to_dict()
        event_seal = self.event_store.seal_sequence(
            sequence_id=(sequence_id or materialized_seal["sequence_id"]) + "-events",
            external_sink=external_sink,
        )
        materialized_seal["event_stream_seal"] = event_seal
        return materialized_seal
