"""
LRSI V11.1 — External Audit Sink and Seal Contracts
==================================================

This module does not pretend that local files are production WORM storage.  It
provides a narrow adapter boundary for S3 Object Lock, EventStoreDB, Kafka, or a
dedicated signature service, plus a local WORM-like directory sink for tests and
validation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

_SAFE_EVENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,180}$")


def _safe_sink_event_id(event_id: str) -> str:
    value = str(event_id or "")
    if not _SAFE_EVENT_ID.fullmatch(value):
        raise ValueError("WORM event_id contains unsafe characters or length")
    return value


class ExternalAuditSink(Protocol):
    """Write-once sink contract for external audit/seal events."""

    sink_name: str

    def write_once(self, event_id: str, payload: dict) -> dict: ...


@dataclass
class LocalWORMDirectorySink:
    """Local write-once sink used to validate the externalization contract.

    Files are written under ``root`` and an existing event id is never replaced.
    Production deployments should implement this interface with S3 Object Lock,
    EventStoreDB, Kafka, or another independently governed audit substrate.
    """

    root: str
    sink_name: str = "local-worm-directory"

    def write_once(self, event_id: str, payload: dict) -> dict:
        safe_event_id = _safe_sink_event_id(event_id)
        root = Path(self.root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = (root / f"{safe_event_id}.json").resolve()
        if root not in target.parents:
            raise ValueError("WORM event target escaped root directory")
        data = dict(payload)
        data.setdefault("external_sink", self.sink_name)
        data.setdefault("external_event_id", safe_event_id)
        data.setdefault("external_written_at", datetime.now(timezone.utc).isoformat())
        serialized = json.dumps(data, indent=2, sort_keys=True)
        try:
            with open(target, "x", encoding="utf-8") as f:
                f.write(serialized)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            raise FileExistsError(f"WORM event already exists: {safe_event_id}")
        return {"sink": self.sink_name, "event_id": safe_event_id, "path": str(target)}


def merkle_root(record_hashes: list[str]) -> str:
    """Compute a deterministic SHA-256 Merkle root from ordered record hashes."""
    if not record_hashes:
        return "0" * 64
    level = [bytes.fromhex(h) for h in record_hashes]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()


@dataclass
class AuditSeal:
    sequence_id: str
    merkle_root: str
    record_count: int
    first_record_hash: str | None
    last_record_hash: str | None
    created_at: str
    signer: dict = field(default_factory=dict)
    signature: str | None = None
    external_write: dict | None = None

    def to_dict(self) -> dict:
        return {
            "schema": "lrsi.audit_seal.v1",
            "sequence_id": self.sequence_id,
            "merkle_root": self.merkle_root,
            "record_count": self.record_count,
            "first_record_hash": self.first_record_hash,
            "last_record_hash": self.last_record_hash,
            "created_at": self.created_at,
            "signer": self.signer,
            "signature": self.signature,
            "external_write": self.external_write,
        }


class AuditSealService:
    """Create and optionally externalize signed Merkle seals for audit runs."""

    def __init__(self, *, signing_adapter=None, external_sink: ExternalAuditSink | None = None):
        self.signing_adapter = signing_adapter
        self.external_sink = external_sink

    def seal(self, records: list[dict], *, sequence_id: str | None = None) -> AuditSeal:
        hashes = [r["record_hash"] for r in records if r.get("record_hash")]
        root = merkle_root(hashes)
        seq = sequence_id or f"seal-{uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat()
        signer_meta = self.signing_adapter.public_metadata() if self.signing_adapter else {}
        signature = None
        if self.signing_adapter:
            signature = self.signing_adapter.sign(root.encode("utf-8"))
        seal = AuditSeal(
            sequence_id=seq,
            merkle_root=root,
            record_count=len(hashes),
            first_record_hash=hashes[0] if hashes else None,
            last_record_hash=hashes[-1] if hashes else None,
            created_at=created_at,
            signer=signer_meta,
            signature=signature,
        )
        if self.external_sink:
            seal.external_write = self.external_sink.write_once(seq, seal.to_dict())
        return seal

    @staticmethod
    def verify_seal(records: list[dict], seal: AuditSeal | dict) -> bool:
        seal_dict = seal.to_dict() if isinstance(seal, AuditSeal) else dict(seal)
        hashes = [r["record_hash"] for r in records if r.get("record_hash")]
        return merkle_root(hashes) == seal_dict.get("merkle_root")
