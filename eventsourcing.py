"""
LRSI V12.0 — Event-sourced runtime contracts
=============================================

This module introduces the event-sourcing spine for the production-near runtime:

* every phase result can be represented as a typed, hash-chained runtime event;
* an append-only JSONL event store is the primary source for replay/projection;
* projections reconstruct iteration-level decisions from event streams;
* seals can be written to WORM/external sinks through the existing sink contract.

The legacy iteration-record audit remains available as a materialized view for
compatibility.  In V12.0, the event stream is the canonical runtime substrate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, is_dataclass
from dataclasses import fields as dataclass_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from audit_sinks import ExternalAuditSink, merkle_root
from security_errors import LRSISecurityError
from signing import SigningAdapter, adapter_from_env, verify_signature_payload
from version import SCHEMA_VERSION

GENESIS_EVENT_HASH = "0" * 64


DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES = int(os.getenv("LRSI_EVENT_PAYLOAD_BUDGET_BYTES", "65536"))
DEFAULT_PATCH_PAYLOAD_BUDGET_BYTES = int(os.getenv("LRSI_PATCH_PAYLOAD_BUDGET_BYTES", "16384"))


SECURITY_LEVEL = 35
AUDIT_LEVEL = 25
logging.addLevelName(SECURITY_LEVEL, "SECURITY")
logging.addLevelName(AUDIT_LEVEL, "AUDIT")

SECURITY_LOGGER = logging.getLogger("lrsi.security.eventsourcing")
SECURITY_LOGGER.addHandler(logging.NullHandler())
SECURITY_LOGGER.propagate = False


def _structured_security_log(event_name: str, *, level: int = logging.INFO, **context: Any) -> None:
    payload = {
        "security_event": event_name,
        "component": "eventsourcing",
        "context": json_safe(context),
    }
    SECURITY_LOGGER.log(level, json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str))


def _event_decision_context(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    phase_result = payload.get("phase_result") if isinstance(payload.get("phase_result"), dict) else {}
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    decision = (
        payload.get("decision")
        or phase_result.get("decision")
        or record.get("final_decision")
        or event.get("decision")
    )
    reason = (
        payload.get("reason")
        or phase_result.get("reason")
        or record.get("gate_reason")
        or event.get("reason")
    )
    terminal = bool(payload.get("terminal") or phase_result.get("terminal"))
    mutation_blocked = bool(
        payload.get("mutation_blocked")
        or phase_result.get("mutation_blocked")
        or patch.get("mutation_blocked")
        or record.get("mutation_blocked")
    )
    block_reason = payload.get("block_reason") or patch.get("block_reason") or record.get("block_reason")
    return {
        "event_type": event.get("event_type"),
        "phase": event.get("phase"),
        "iteration": event.get("iteration"),
        "trace_id": event.get("trace_id"),
        "sequence": event.get("sequence"),
        "event_id": event.get("event_id"),
        "event_hash": event.get("event_hash"),
        "previous_event_hash": event.get("previous_event_hash"),
        "decision": decision,
        "reason": reason,
        "terminal": terminal,
        "mutation_blocked": mutation_blocked,
        "block_reason": block_reason,
        "payload_bytes": json_byte_size(payload) if payload else 0,
        "schema_version": event.get("schema_version"),
        "stream_id": event.get("stream_id"),
        "signed": bool(event.get("event_signature")),
    }


def _is_critical_event_context(context: dict[str, Any]) -> bool:
    decision = str(context.get("decision") or "").upper()
    return (
        bool(context.get("terminal"))
        or bool(context.get("mutation_blocked"))
        or decision in {"RED", "STOP", "HOLD", "REJECT", "ROLLBACK"}
    )


def json_byte_size(data: Any) -> int:
    """Return the canonical UTF-8 byte size of a JSON-safe payload."""
    return len(canonical_json(json_safe(data)).encode("utf-8"))


def payload_sha256(data: Any) -> str:
    """Hash the canonical JSON representation of a JSON-safe payload."""
    return hashlib.sha256(canonical_json(json_safe(data)).encode("utf-8")).hexdigest()


def payload_reference(data: Any, *, kind: str = "payload", max_bytes: int | None = None) -> dict[str, Any]:
    """Return a small deterministic reference for a large runtime payload.

    V12 event streams are the canonical audit substrate. They must therefore
    remain bounded and replayable instead of embedding whole runtime objects or
    recursive materialized records. The digest preserves integrity binding while
    large evidence can be stored out-of-band by higher layers.
    """
    safe = json_safe(data)
    return {
        "__payload_ref__": True,
        "kind": kind,
        "sha256": payload_sha256(safe),
        "bytes": json_byte_size(safe),
        "budget_bytes": max_bytes if max_bytes is not None else DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES,
    }


def bounded_payload(data: Any, *, kind: str = "payload", max_bytes: int | None = None) -> Any:
    """Return ``data`` if it fits the budget, otherwise a hash reference."""
    budget = max_bytes if max_bytes is not None else DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES
    safe = json_safe(data)
    if json_byte_size(safe) <= budget:
        return safe
    return payload_reference(safe, kind=kind, max_bytes=budget)


def event_reference(event: dict[str, Any]) -> dict[str, Any]:
    """Small canonical reference to a committed event-store item."""
    ref = {
        "event_id": event.get("event_id"),
        "event_hash": event.get("event_hash"),
        "sequence": event.get("sequence"),
        "event_type": event.get("event_type"),
        "phase": event.get("phase"),
        "iteration": event.get("iteration"),
        "trace_id": event.get("trace_id"),
        "stream_id": event.get("stream_id"),
    }
    if isinstance(event.get("external_write"), dict):
        ref["external_write"] = event.get("external_write")
    return {k: v for k, v in ref.items() if v is not None}


class EventStoreCorruptionError(LRSISecurityError):
    """Raised when the JSONL event stream contains non-recoverable corruption."""

    def __init__(self, message: str, *, context: dict[str, Any] | None = None):
        super().__init__("event_store_corruption", message, context=context)


def production_mode_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return bool(explicit)
    return os.getenv("LRSI_PRODUCTION_MODE", "").lower().strip() in {"1", "true", "yes", "on"}


def validate_event_store_production_config(*, signing_adapter: SigningAdapter | None, external_sink: ExternalAuditSink | None) -> None:
    """Fail closed when production mode lacks identity-bound signed + externalized audit events.

    HMAC is intentionally rejected in production mode: it provides local
    integrity but not independent signer identity.  Production audit streams
    must use an asymmetric signing adapter and an external/WORM sink.
    """
    mode = os.getenv("AUDIT_SIGNING_MODE", "").lower().strip()
    if signing_adapter is None:
        if mode not in {"ed25519", "public-key", "public_key"}:
            raise LRSISecurityError(
                "production_requires_public_key_signing_mode",
                "production event store requires AUDIT_SIGNING_MODE=ed25519/public-key; HMAC is dev-only",
                context={"audit_signing_mode": mode or "<unset>"},
            )
        raise LRSISecurityError(
            "production_requires_ed25519_signing_adapter",
            "production event store requires a configured Ed25519 signing adapter",
            context={"signing_adapter_present": bool(adapter)},
        )
    if not str(getattr(signing_adapter, "algorithm", "")).startswith("Ed25519"):
        raise LRSISecurityError(
            "production_requires_ed25519_not_hmac",
            "production event store requires an Ed25519 signing adapter; HMAC is dev-only",
            context={"signing_mode": getattr(signing_adapter, "mode", "unknown")},
        )
    if external_sink is None:
        raise LRSISecurityError(
            "production_requires_external_or_worm_sink",
            "production event store requires AUDIT_WORM_DIR or an external audit sink",
            context={"has_external_sink": bool(external_sink), "audit_worm_dir": os.getenv("AUDIT_WORM_DIR", "")},
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def json_safe(data: Any) -> Any:
    """Return a deterministic JSON-safe copy suitable for event payloads.

    Unknown Python objects must never be persisted through ``str(obj)`` because
    default object representations include process-local memory addresses and
    are neither stable nor replayable.  Known structured objects are converted;
    unknown live objects are represented by a type marker only.
    """
    if data is None or isinstance(data, (str, int, float, bool)):
        return data
    if isinstance(data, dict):
        return {str(k): json_safe(v) for k, v in data.items()}
    if isinstance(data, (list, tuple, set)):
        return [json_safe(v) for v in data]
    if is_dataclass(data) and not isinstance(data, type):
        return {field.name: json_safe(getattr(data, field.name)) for field in dataclass_fields(data)}
    to_dict = getattr(data, "to_dict", None)
    if callable(to_dict):
        try:
            return json_safe(to_dict())
        except Exception as exc:
            return {
                "__non_json_type__": f"{type(data).__module__}.{type(data).__qualname__}",
                "__redacted__": True,
                "__serialization_error__": type(exc).__name__,
            }
    return {
        "__non_json_type__": f"{type(data).__module__}.{type(data).__qualname__}",
        "__redacted__": True,
    }


@contextmanager
def file_lock(path: str):
    lock_path = f"{path}.lock"
    directory = os.path.dirname(os.path.abspath(lock_path)) or "."
    os.makedirs(directory, exist_ok=True)
    lock_fh = open(lock_path, "a+", encoding="utf-8")
    try:
        try:
            import fcntl
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - Windows fallback
            pass
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
        except ImportError:  # pragma: no cover - Windows fallback
            pass
        lock_fh.close()


def _fsync_directory(path: str) -> None:
    """Best-effort directory fsync for atomic rename durability on POSIX."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        dir_fd = os.open(directory, os.O_RDONLY)
    except OSError:  # pragma: no cover - platform/filesystem dependent
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _atomic_write_json_file(path: str, data: dict[str, Any]) -> None:
    """Atomically write a JSON file and fsync both file and directory."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, f".{os.path.basename(path)}.{uuid.uuid4().hex}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(canonical_json(data))
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_directory(path)


def _remove_file_if_exists(path: str) -> None:
    try:
        os.remove(path)
        _fsync_directory(path)
    except FileNotFoundError:
        return


def _append_jsonl_line(path: str, data: dict[str, Any]) -> None:
    """Append one JSONL item and fsync the file before returning."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(canonical_json(data) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _hash_event_payload(event: dict[str, Any]) -> str:
    payload = dict(event)
    for key in (
        "event_hash",
        "event_signature",
        "event_signature_algorithm",
        "event_signer_id",
        "event_public_key_b64",
    ):
        payload.pop(key, None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_event_schema(event: dict[str, Any], *, index: int | None = None) -> list[str]:
    """Return semantic schema errors for one runtime event.

    Hash-chain validation proves that a byte-level event stream was not
    silently changed.  This function checks the other production-critical
    property: each hash-protected item must still be a meaningful runtime
    event with the fields replay/projection depend on.
    """
    prefix = f"event[{index}]" if index is not None else "event"
    errors: list[str] = []
    if not isinstance(event, dict):
        return [f"{prefix} must be an object"]

    event_type = event.get("event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        errors.append(f"{prefix}.event_type missing or invalid")
    payload = event.get("payload")
    if not isinstance(payload, dict):
        errors.append(f"{prefix}.payload missing or invalid")

    stream_id = event.get("stream_id")
    if not isinstance(stream_id, str) or not stream_id.strip():
        errors.append(f"{prefix}.stream_id missing or invalid")

    sequence = event.get("sequence")
    if not isinstance(sequence, int) or sequence < 0:
        errors.append(f"{prefix}.sequence missing or invalid")

    if not _is_sha256_hex(event.get("previous_event_hash")):
        errors.append(f"{prefix}.previous_event_hash missing or invalid")

    event_id = event.get("event_id")
    if not isinstance(event_id, str) or not event_id.strip():
        errors.append(f"{prefix}.event_id missing or invalid")

    if not _is_iso_datetime(event.get("created_at")):
        errors.append(f"{prefix}.created_at missing or invalid")

    schema_version = event.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        errors.append(f"{prefix}.schema_version invalid: {schema_version!r}")

    if "event_hash" in event and not _is_sha256_hex(event.get("event_hash")):
        errors.append(f"{prefix}.event_hash invalid")

    if event_type == "phase.result":
        phase = event.get("phase")
        if not isinstance(phase, str) or not phase.strip():
            errors.append(f"{prefix}.phase missing or invalid for phase.result")

    if event_type == "audit.iteration_record" and isinstance(payload, dict):
        if not isinstance(payload.get("record"), dict):
            errors.append(f"{prefix}.payload.record missing or invalid for audit.iteration_record")

    return errors


@dataclass(frozen=True)
class RuntimeEvent:
    """Hash-chainable event emitted by a phase or audit component."""

    event_type: str
    payload: dict[str, Any]
    phase: str | None = None
    iteration: int | None = None
    trace_id: str | None = None
    stream_id: str = "default"
    sequence: int = 0
    previous_event_hash: str = GENESIS_EVENT_HASH
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex}")
    created_at: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION
    event_hash: str | None = None

    def unsigned_dict(self) -> dict[str, Any]:
        # Avoid dataclasses.asdict() here: it deep-copies nested payloads and
        # would accidentally deepcopy injected live LLM clients contained in
        # compatibility patches.  V12 events intentionally store a JSON-safe
        # representation instead.
        data = {
            "event_type": self.event_type,
            "payload": json_safe(self.payload),
            "phase": self.phase,
            "iteration": self.iteration,
            "trace_id": self.trace_id,
            "stream_id": self.stream_id,
            "sequence": self.sequence,
            "previous_event_hash": self.previous_event_hash,
            "event_id": self.event_id,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }
        if self.event_hash is not None:
            data["event_hash"] = self.event_hash
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self.unsigned_dict()
        data["event_hash"] = self.event_hash or _hash_event_payload(data)
        return data

    @classmethod
    def from_phase_result(
        cls,
        *,
        result: Any,
        iteration: int | None,
        trace_id: str | None,
        stream_id: str = "iteration-stream",
    ) -> "RuntimeEvent":
        audit = result.audit_entry(iteration=iteration)
        if trace_id:
            audit.setdefault("trace_id", trace_id)
        return cls(
            event_type="phase.result",
            phase=getattr(result, "phase", audit.get("phase")),
            iteration=iteration,
            trace_id=trace_id,
            stream_id=stream_id,
            payload={
                "phase_result": bounded_payload(
                    audit,
                    kind="phase_result",
                    max_bytes=DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES // 2,
                ),
                "patch": payload_reference(
                    dict(getattr(result, "patch", {}) or {}),
                    kind="phase_patch",
                    max_bytes=DEFAULT_PATCH_PAYLOAD_BUDGET_BYTES,
                ),
                "patch_keys": sorted(dict(getattr(result, "patch", {}) or {}).keys()),
                "decision": json_safe(getattr(result, "decision", audit.get("decision"))),
                "reason": json_safe(getattr(result, "reason", audit.get("reason", ""))),
                "terminal": bool(getattr(result, "terminal", False)),
            },
        )


@dataclass(frozen=True)
class EventAppendResult:
    event: dict[str, Any]
    external_write: dict[str, Any] | None = None


class EventStore(Protocol):
    path: str

    def append(self, event: RuntimeEvent | dict[str, Any]) -> dict[str, Any]: ...

    def load(self) -> list[dict[str, Any]]: ...

    def verify(self, *, require_signature: bool = False) -> tuple[bool, list[str]]: ...


@dataclass(frozen=True)
class EventStoreCursor:
    """O(1) append cursor persisted next to the JSONL event stream."""

    last_sequence: int = -1
    last_event_hash: str = GENESIS_EVENT_HASH
    event_count: int = 0
    file_size: int = 0


@dataclass
class AppendOnlyEventStore:
    """Append-only JSONL event store with hash chaining and optional signatures.

    P1 hardening replaces the old append-time ``load whole JSONL`` behavior with
    a persisted cursor sidecar.  The full stream is still loaded for explicit
    ``load()/verify()/replay`` calls, but normal appends now derive sequence and
    previous hash from ``<path>.cursor.json`` and update it atomically under the
    same file lock.
    """

    path: str = "audit_events.jsonl"
    stream_id: str = "lrsi-runtime"
    signing_adapter: SigningAdapter | None = None
    external_sink: ExternalAuditSink | None = None
    production_mode: bool | None = None
    _cursor: EventStoreCursor = field(init=False, repr=False)

    def __post_init__(self):
        self.production_mode = production_mode_enabled(self.production_mode)
        self.signing_adapter = self.signing_adapter or adapter_from_env()
        if self.production_mode:
            validate_event_store_production_config(
                signing_adapter=self.signing_adapter,
                external_sink=self.external_sink,
            )
        with file_lock(self.path):
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.path).touch(exist_ok=True)
            if self.production_mode:
                events = self._load_unlocked()
                ok, errors = verify_event_chain(events, require_signature=True)
                if not ok:
                    raise LRSISecurityError(
                        "production_event_store_verification_failed",
                        "production event store failed signature/hash verification",
                        context={"errors": errors},
                    )
                self._cursor = self._cursor_from_events_unlocked(events)
                self._write_cursor_unlocked(self._cursor)
            else:
                self._cursor = self._load_or_rebuild_cursor_unlocked(recover_partial_tail=True)
            self._reconcile_pending_unlocked()

    @property
    def cursor_path(self) -> str:
        return f"{self.path}.cursor.json"

    @property
    def pending_dir(self) -> str:
        return f"{self.path}.pending"

    def _pending_path(self, event_id: str) -> str:
        safe = str(event_id or "").replace(os.sep, "_")
        if os.altsep:
            safe = safe.replace(os.altsep, "_")
        if not safe or safe.startswith("."):
            safe = f"evt-{uuid.uuid4().hex}"
        return os.path.join(self.pending_dir, f"{safe}.json")

    def _file_size_unlocked(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def _cursor_from_events_unlocked(self, events: list[dict[str, Any]]) -> EventStoreCursor:
        if not events:
            return EventStoreCursor(file_size=self._file_size_unlocked())
        last = events[-1]
        return EventStoreCursor(
            last_sequence=int(last.get("sequence", len(events) - 1)),
            last_event_hash=last.get("event_hash", GENESIS_EVENT_HASH),
            event_count=len(events),
            file_size=self._file_size_unlocked(),
        )

    def _load_cursor_unlocked(self) -> EventStoreCursor | None:
        if not os.path.exists(self.cursor_path):
            return None
        try:
            with open(self.cursor_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cursor = EventStoreCursor(
                last_sequence=int(data.get("last_sequence", -1)),
                last_event_hash=str(data.get("last_event_hash", GENESIS_EVENT_HASH)),
                event_count=int(data.get("event_count", 0)),
                file_size=int(data.get("file_size", 0)),
            )
        except Exception:
            return None
        # If another process appended without updating the sidecar or the file was
        # truncated, rebuild once.  Normal append remains O(1).
        if cursor.file_size != self._file_size_unlocked():
            return None
        return cursor

    def _write_cursor_unlocked(self, cursor: EventStoreCursor) -> None:
        _atomic_write_json_file(self.cursor_path, {
            "schema": "lrsi.event_store_cursor.v1",
            "schema_version": SCHEMA_VERSION,
            "path": os.path.abspath(self.path),
            "last_sequence": cursor.last_sequence,
            "last_event_hash": cursor.last_event_hash,
            "event_count": cursor.event_count,
            "file_size": cursor.file_size,
            "updated_at": utc_now_iso(),
        })

    def _load_or_rebuild_cursor_unlocked(self, *, recover_partial_tail: bool = False) -> EventStoreCursor:
        cursor = self._load_cursor_unlocked()
        if cursor is not None:
            return cursor
        cursor = self._cursor_from_events_unlocked(
            self._load_unlocked(recover_partial_tail=recover_partial_tail)
        )
        self._write_cursor_unlocked(cursor)
        return cursor

    def _load_unlocked(self, *, recover_partial_tail: bool = False) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        events: list[dict[str, Any]] = []
        with open(self.path, "rb") as f:
            raw_lines = f.readlines()
        offset = 0
        for line_no, raw in enumerate(raw_lines, start=1):
            line_start = offset
            offset += len(raw)
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                is_trailing_partial = line_no == len(raw_lines) and not raw.endswith(b"\n")
                if recover_partial_tail and is_trailing_partial:
                    with open(self.path, "rb+") as repair_f:
                        repair_f.truncate(line_start)
                    return events
                detail = getattr(exc, "msg", str(exc))
                raise EventStoreCorruptionError(
                    f"corrupt JSONL event at line {line_no}: {detail}"
                ) from exc
        return events

    def load(self) -> list[dict[str, Any]]:
        with file_lock(self.path):
            events = self._load_unlocked()
            self._cursor = self._cursor_from_events_unlocked(events)
            self._write_cursor_unlocked(self._cursor)
            return events

    @staticmethod
    def _verify_single_append(data: dict[str, Any], *, previous_hash: str, sequence: int, require_signature: bool) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if data.get("previous_event_hash") != previous_hash:
            errors.append("appended_event.previous_event_hash mismatch")
        if data.get("sequence") != sequence:
            errors.append("appended_event.sequence mismatch")
        if data.get("event_hash") != _hash_event_payload(data):
            errors.append("appended_event.event_hash mismatch")
        if require_signature:
            mapped = dict(data)
            if "event_signature" in mapped:
                mapped["audit_signature"] = mapped.get("event_signature")
                mapped["audit_signature_algorithm"] = mapped.get("event_signature_algorithm")
                mapped["audit_signer_id"] = mapped.get("event_signer_id")
                mapped["audit_public_key_b64"] = mapped.get("event_public_key_b64")
            if not mapped.get("audit_signature"):
                errors.append("appended_event.event_signature missing")
            elif not verify_signature_payload(data["event_hash"], mapped):
                errors.append("appended_event.event_signature invalid")
        return not errors, errors

    def _write_pending_unlocked(
        self,
        data: dict[str, Any],
        *,
        status: str,
        external_write: dict[str, Any] | None = None,
    ) -> str:
        os.makedirs(self.pending_dir, exist_ok=True)
        path = self._pending_path(str(data.get("event_id")))
        _atomic_write_json_file(path, {
            "schema": "lrsi.event_append_journal.v1",
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "event_id": data.get("event_id"),
            "stream_path": os.path.abspath(self.path),
            "event": data,
            "external_write": external_write,
            "updated_at": utc_now_iso(),
        })
        return path

    def _load_pending_entries_unlocked(self) -> list[tuple[str, dict[str, Any]]]:
        if not os.path.isdir(self.pending_dir):
            return []
        entries: list[tuple[str, dict[str, Any]]] = []
        for path in sorted(Path(self.pending_dir).glob("*.json")):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries.append((str(path), data))
        return entries

    def _event_already_local_unlocked(self, event_id: str) -> bool:
        return any(event.get("event_id") == event_id for event in self._load_unlocked())

    def _append_local_committed_unlocked(self, data: dict[str, Any]) -> EventStoreCursor:
        cursor = self._load_or_rebuild_cursor_unlocked()
        expected_sequence = cursor.last_sequence + 1
        ok, errors = self._verify_single_append(
            data,
            previous_hash=cursor.last_event_hash,
            sequence=expected_sequence,
            require_signature=bool(self.production_mode),
        )
        if not ok:
            raise EventStoreCorruptionError(
                "pending event cannot be committed to current local chain: " + repr(errors)
            )
        schema_errors = validate_event_schema(data)
        if schema_errors:
            raise LRSISecurityError(
                "pending_event_schema_validation_failed",
                "pending event schema validation failed",
                context={"errors": schema_errors, "event_context": _event_decision_context(data)},
            )
        _append_jsonl_line(self.path, data)
        cursor = EventStoreCursor(
            last_sequence=int(data["sequence"]),
            last_event_hash=str(data["event_hash"]),
            event_count=cursor.event_count + 1,
            file_size=self._file_size_unlocked(),
        )
        self._cursor = cursor
        self._write_cursor_unlocked(cursor)
        return cursor

    def _write_external_once_unlocked(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if not self.external_sink:
            return None
        try:
            return self.external_sink.write_once(str(data["event_id"]), data)
        except FileExistsError:
            # A crash can occur after the external write but before the local
            # pending marker is upgraded to ``externalized``.  Because event ids
            # are generated per append and WORM sinks are write-once, an existing
            # id is treated as an already-externalized transaction that still
            # needs local reconciliation.
            return {
                "sink": getattr(self.external_sink, "sink_name", "external-audit-sink"),
                "event_id": data.get("event_id"),
                "status": "already_exists_assumed_externalized",
            }

    def _reconcile_pending_unlocked(self) -> list[dict[str, Any]]:
        reconciled: list[dict[str, Any]] = []
        for path, entry in self._load_pending_entries_unlocked():
            data = entry.get("event")
            if not isinstance(data, dict):
                raise EventStoreCorruptionError(f"pending event journal is malformed: {path}")
            event_id = str(data.get("event_id"))
            if self._event_already_local_unlocked(event_id):
                _remove_file_if_exists(path)
                reconciled.append({"event_id": event_id, "status": "already_local"})
                continue
            external_write = entry.get("external_write")
            status = entry.get("status")
            if status != "externalized" and not self.external_sink:
                reconciled.append({"event_id": event_id, "status": "prepared_without_sink"})
                continue
            if self.external_sink and status != "externalized":
                external_write = self._write_external_once_unlocked(data)
                self._write_pending_unlocked(
                    data, status="externalized", external_write=external_write
                )
            self._append_local_committed_unlocked(data)
            _remove_file_if_exists(path)
            reconciled.append({
                "event_id": event_id,
                "status": "committed",
                "external_write": external_write,
            })
        return reconciled

    def reconcile_pending(self) -> list[dict[str, Any]]:
        """Commit any externally written but locally uncommitted events.

        This is the P1 consistency bridge between a write-once external audit
        sink and the local JSONL stream.  A crash or local I/O failure after
        externalization leaves an event journal under ``<path>.pending``; the
        next startup or explicit call replays that event into the local chain
        before new appends advance the cursor.
        """
        with file_lock(self.path):
            return self._reconcile_pending_unlocked()

    @staticmethod
    def _bounded_event_payload(data: dict[str, Any]) -> dict[str, Any]:
        """Enforce bounded event payloads without breaking replay-critical fields."""
        payload = json_safe(data.get("payload", {}) or {})
        if not isinstance(payload, dict):
            payload = {"value": payload}
        if json_byte_size(payload) <= DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES:
            return payload

        event_type = data.get("event_type")
        if event_type == "phase.result":
            phase_result = payload.get("phase_result", {})
            compact = {
                "__payload_compacted__": True,
                "original_sha256": payload_sha256(payload),
                "original_bytes": json_byte_size(payload),
                "budget_bytes": DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES,
                "phase_result": bounded_payload(
                    phase_result,
                    kind="phase_result",
                    max_bytes=DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES // 2,
                ),
                "patch": payload_reference(
                    payload.get("patch", {}),
                    kind="phase_patch",
                    max_bytes=DEFAULT_PATCH_PAYLOAD_BUDGET_BYTES,
                ),
                "patch_keys": payload.get("patch_keys") or (phase_result.get("patch_keys") if isinstance(phase_result, dict) else []),
                "decision": payload.get("decision") or (phase_result.get("decision") if isinstance(phase_result, dict) else None),
                "reason": payload.get("reason") or (phase_result.get("reason") if isinstance(phase_result, dict) else ""),
                "terminal": bool(payload.get("terminal") or (phase_result.get("terminal") if isinstance(phase_result, dict) else False)),
            }
            return compact

        if event_type == "audit.iteration_record":
            record = payload.get("record", {})
            return {
                "__payload_compacted__": True,
                "original_sha256": payload_sha256(payload),
                "original_bytes": json_byte_size(payload),
                "budget_bytes": DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES,
                "record": bounded_payload(record, kind="iteration_record", max_bytes=DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES // 2),
            }

        return payload_reference(payload, kind=str(event_type or "event_payload"), max_bytes=DEFAULT_EVENT_PAYLOAD_BUDGET_BYTES)

    def append(self, event: RuntimeEvent | dict[str, Any]) -> dict[str, Any]:
        with file_lock(self.path):
            self._reconcile_pending_unlocked()
            cursor = self._load_or_rebuild_cursor_unlocked()
            previous_hash = cursor.last_event_hash
            sequence = cursor.last_sequence + 1
            if isinstance(event, RuntimeEvent):
                data = event.unsigned_dict()
            else:
                data = dict(event)
            data["payload"] = self._bounded_event_payload(data)
            data.setdefault("schema_version", SCHEMA_VERSION)
            data.setdefault("event_id", f"evt-{uuid.uuid4().hex}")
            data.setdefault("created_at", utc_now_iso())
            data.setdefault("stream_id", self.stream_id)
            data["sequence"] = sequence
            data["previous_event_hash"] = previous_hash
            data["event_hash"] = _hash_event_payload(data)
            schema_errors = validate_event_schema(data)
            if schema_errors:
                _structured_security_log(
                    "event_schema_validation_failed",
                    level=logging.ERROR,
                    errors=schema_errors,
                    event_context=_event_decision_context(data),
                )
                raise LRSISecurityError(
                    "event_schema_validation_failed",
                    "event schema validation failed",
                    context={"errors": schema_errors, "event_context": _event_decision_context(data)},
                )
            if self.signing_adapter:
                data.update({
                    key.replace("audit_", "event_"): value
                    for key, value in self.signing_adapter.public_metadata().items()
                })
                data["event_signature"] = self.signing_adapter.sign(data["event_hash"].encode("utf-8"))
            if self.production_mode:
                ok, errors = self._verify_single_append(
                    data, previous_hash=previous_hash, sequence=sequence, require_signature=True
                )
                if not ok:
                    _structured_security_log(
                        "production_event_append_verification_failed",
                        level=logging.ERROR,
                        errors=errors,
                        event_context=_event_decision_context(data),
                    )
                    raise LRSISecurityError(
                        "production_event_append_verification_failed",
                        "production event append failed signature/hash verification",
                        context={"errors": errors, "event_context": _event_decision_context(data)},
                    )
            pending_path = None
            external_write = None
            if self.external_sink:
                pending_path = self._write_pending_unlocked(data, status="prepared")
                external_write = self._write_external_once_unlocked(data)
                pending_path = self._write_pending_unlocked(
                    data, status="externalized", external_write=external_write
                )
            self._append_local_committed_unlocked(data)
            if pending_path:
                _remove_file_if_exists(pending_path)
            event_context = _event_decision_context(data)
            _structured_security_log(
                "event_appended",
                event_context=event_context,
                externalized=bool(external_write),
                production_mode=bool(self.production_mode),
                stream_id=data.get("stream_id"),
                path=self.path,
            )
            if _is_critical_event_context(event_context):
                _structured_security_log(
                    "critical_event_committed",
                    level=SECURITY_LEVEL,
                    trace_id=event_context.get("trace_id"),
                    iteration=event_context.get("iteration"),
                    decision=event_context.get("decision"),
                    phase=event_context.get("phase"),
                    reason=event_context.get("reason"),
                    event_hash=event_context.get("event_hash"),
                    previous_event_hash=event_context.get("previous_event_hash"),
                    event_context=event_context,
                    externalized=bool(external_write),
                    production_mode=bool(self.production_mode),
                )
            if external_write:
                returned = dict(data)
                returned["external_write"] = external_write
                return returned
            return data

    def verify(self, *, require_signature: bool = False) -> tuple[bool, list[str]]:
        return verify_event_chain(self.load(), require_signature=require_signature)

    def seal_sequence(self, *, sequence_id: str | None = None, external_sink: ExternalAuditSink | None = None) -> dict[str, Any]:
        events = self.load()
        event_hashes = [e["event_hash"] for e in events]
        seal: dict[str, Any] = {
            "schema": "lrsi.event_seal.v1",
            "schema_version": SCHEMA_VERSION,
            "sequence_id": sequence_id or f"event-seal-{uuid.uuid4().hex[:12]}",
            "stream_id": self.stream_id,
            "event_count": len(events),
            "first_event_hash": event_hashes[0] if event_hashes else None,
            "last_event_hash": event_hashes[-1] if event_hashes else None,
            "merkle_root": merkle_root(event_hashes),
            "created_at": utc_now_iso(),
        }
        signer = self.signing_adapter or adapter_from_env()
        if signer:
            seal.update({
                key.replace("audit_", "seal_"): value
                for key, value in signer.public_metadata().items()
            })
            seal["seal_signature"] = signer.sign(str(seal["merkle_root"]).encode("utf-8"))
        sink = external_sink or self.external_sink
        if sink:
            seal["external_write"] = sink.write_once(str(seal["sequence_id"]), seal)
        return seal


def verify_event_chain(
    events: Iterable[dict[str, Any]],
    *,
    require_signature: bool = False,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    previous = GENESIS_EVENT_HASH
    for idx, event in enumerate(events):
        schema_errors = validate_event_schema(event, index=idx)
        errors.extend(schema_errors)
        if "event_hash" not in event:
            errors.append(f"event[{idx}].event_hash missing")
            continue
        if "previous_event_hash" not in event:
            errors.append(f"event[{idx}].previous_event_hash missing")
            continue
        if event.get("previous_event_hash") != previous:
            errors.append(f"event[{idx}].previous_event_hash mismatch")
        if event.get("sequence") != idx:
            errors.append(f"event[{idx}].sequence mismatch")
        expected = _hash_event_payload(event)
        if event.get("event_hash") != expected:
            errors.append(f"event[{idx}].event_hash mismatch")
        if require_signature:
            mapped = dict(event)
            if "event_signature" in mapped:
                mapped["audit_signature"] = mapped.get("event_signature")
                mapped["audit_signature_algorithm"] = mapped.get("event_signature_algorithm")
                mapped["audit_signer_id"] = mapped.get("event_signer_id")
                mapped["audit_public_key_b64"] = mapped.get("event_public_key_b64")
            if not mapped.get("audit_signature"):
                errors.append(f"event[{idx}].event_signature missing")
            elif not verify_signature_payload(event["event_hash"], mapped):
                errors.append(f"event[{idx}].event_signature invalid")
        previous = event.get("event_hash", previous)
    return not errors, errors


def phase_result_event_key(event: dict[str, Any]) -> tuple[Any, ...]:
    """Stable comparison key linking phase_audit entries to phase.result events."""
    payload = event.get("payload", {}) or {}
    phase_result = payload.get("phase_result", {}) or {}
    return (
        event.get("iteration") if event.get("iteration") is not None else phase_result.get("iteration"),
        event.get("phase") or phase_result.get("phase"),
        phase_result.get("decision") if phase_result.get("decision") is not None else payload.get("decision"),
        phase_result.get("reason") if phase_result.get("reason") is not None else payload.get("reason"),
        bool(phase_result.get("terminal") if "terminal" in phase_result else payload.get("terminal", False)),
    )


def phase_audit_entry_key(entry: dict[str, Any], *, fallback_iteration: Any = None) -> tuple[Any, ...]:
    return (
        entry.get("iteration", fallback_iteration),
        entry.get("phase"),
        entry.get("decision"),
        entry.get("reason"),
        bool(entry.get("terminal", False)),
    )


def validate_phase_audit_event_coverage(
    records: Iterable[dict[str, Any]],
    events: Iterable[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Verify every materialized phase_audit entry has a phase.result event.

    This is intentionally CI-friendly: it compares the legacy/materialized audit
    view with the canonical V12 event stream and fails when terminal paths or
    review paths keep phase diagnostics only inside ``phase_audit``.
    """
    event_keys = {
        phase_result_event_key(event)
        for event in events
        if event.get("event_type") == "phase.result"
    }
    errors: list[str] = []
    for record_idx, record in enumerate(records):
        iteration = record.get("iteration")
        for audit_idx, entry in enumerate(record.get("phase_audit", []) or []):
            if not isinstance(entry, dict) or entry.get("audit_event_type") != "phase_result":
                continue
            key = phase_audit_entry_key(entry, fallback_iteration=iteration)
            if key not in event_keys:
                errors.append(
                    "record[{record_idx}].phase_audit[{audit_idx}] missing phase.result "
                    "event for iteration={iteration!r}, phase={phase!r}, decision={decision!r}".format(
                        record_idx=record_idx,
                        audit_idx=audit_idx,
                        iteration=key[0],
                        phase=key[1],
                        decision=key[2],
                    )
                )
    return not errors, errors


def project_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Project an event stream into iteration decisions and phase diagnostics."""
    projection: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "iterations": {},
        "phase_results": [],
        "final_records": [],
    }
    for event in events:
        payload = event.get("payload", {}) or {}
        iteration = event.get("iteration")
        if event.get("event_type") == "phase.result":
            phase_result = payload.get("phase_result", {})
            item = {
                "event_hash": event.get("event_hash"),
                "sequence": event.get("sequence"),
                "iteration": iteration,
                "trace_id": event.get("trace_id"),
                "phase": event.get("phase") or phase_result.get("phase"),
                "decision": phase_result.get("decision") or payload.get("decision"),
                "reason": phase_result.get("reason") or payload.get("reason"),
                "terminal": phase_result.get("terminal") or payload.get("terminal"),
                "diagnostics": phase_result.get("diagnostics", {}),
            }
            projection["phase_results"].append(item)
            if iteration is not None:
                bucket = projection["iterations"].setdefault(str(iteration), {"phases": []})
                bucket["phases"].append(item)
                if item["phase"] in {"final_gate", "final_gate_phase"} or item.get("terminal"):
                    bucket["last_decision"] = item["decision"]
                    bucket["last_reason"] = item["reason"]
        elif event.get("event_type") == "audit.iteration_record":
            record = payload.get("record", {})
            projection["final_records"].append(record)
            rec_iteration = record.get("iteration", iteration)
            if rec_iteration is not None:
                bucket = projection["iterations"].setdefault(str(rec_iteration), {"phases": []})
                bucket["final_decision"] = record.get("final_decision")
                bucket["accepted"] = record.get("accepted")
                bucket["record_hash"] = record.get("record_hash")
                bucket["evidence_bundle_hash"] = record.get("evidence_bundle", {}).get("evidence_bundle_hash") if isinstance(record.get("evidence_bundle"), dict) else None
    return projection


def replay_decisions(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    projection = project_events(events)
    decisions = []
    for iteration, data in sorted(projection["iterations"].items(), key=lambda kv: int(kv[0])):
        decisions.append({
            "iteration": int(iteration),
            "final_decision": data.get("final_decision") or data.get("last_decision"),
            "accepted": data.get("accepted", False),
            "phase_count": len(data.get("phases", [])),
            "record_hash": data.get("record_hash"),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "decision_count": len(decisions),
        "decisions": decisions,
    }
