"""LRSI V11.1 — Two-person signed review interface."""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from eventsourcing import canonical_json
from signing import SigningAdapter, adapter_from_env, verify_signature_payload

_SIGNATURE_FIELDS = {
    "signature",
    "signature_algorithm",
    "reviewer_public_key_b64",
    "review_approval_hash",
}


@dataclass(frozen=True)
class ReviewApproval:
    reviewer_id: str
    role: str
    action: str
    rationale: str
    signature: str
    signature_algorithm: str
    evidence_case_id: str | None = None
    evidence_bundle_hash: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    review_approval_hash: str | None = None
    reviewer_public_key_b64: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def review_approval_unsigned_payload(approval: dict | ReviewApproval) -> dict[str, Any]:
    """Return the canonical payload that a reviewer signs.

    The signed payload binds reviewer identity, role, action, rationale, evidence
    case id/hash and timestamp.  Signature/hash metadata is deliberately excluded
    so verification is deterministic.
    """
    data = approval.to_dict() if hasattr(approval, "to_dict") else dict(approval)
    for key in _SIGNATURE_FIELDS:
        data.pop(key, None)
    return data


def review_approval_digest(approval: dict | ReviewApproval) -> str:
    return hashlib.sha256(
        canonical_json(review_approval_unsigned_payload(approval)).encode("utf-8")
    ).hexdigest()


def sign_review_approval(
    *,
    reviewer_id: str,
    role: str,
    action: str = "approve",
    rationale: str = "reviewed evidence and runtime state",
    evidence_case_id: str | None = None,
    evidence_bundle_hash: str | None = None,
    signing_adapter: SigningAdapter | None = None,
) -> ReviewApproval:
    """Create a cryptographically signed review approval using env signing by default."""
    signer = signing_adapter or adapter_from_env()
    if signer is None:
        raise RuntimeError("signed review approval requires AUDIT_SIGNING_MODE and a signing key")
    draft = ReviewApproval(
        reviewer_id=reviewer_id,
        role=role,
        action=action,
        rationale=rationale,
        signature="",
        signature_algorithm="",
        evidence_case_id=evidence_case_id,
        evidence_bundle_hash=evidence_bundle_hash,
    )
    digest = review_approval_digest(draft)
    meta = signer.public_metadata()
    return ReviewApproval(
        reviewer_id=reviewer_id,
        role=role,
        action=action,
        rationale=rationale,
        signature=signer.sign(digest.encode("utf-8")),
        signature_algorithm=meta.get("audit_signature_algorithm", signer.algorithm),
        evidence_case_id=evidence_case_id,
        evidence_bundle_hash=evidence_bundle_hash,
        created_at=draft.created_at,
        review_approval_hash=digest,
        reviewer_public_key_b64=meta.get("audit_public_key_b64"),
    )


def verify_review_approval_signature(approval: dict | ReviewApproval) -> bool:
    data = approval.to_dict() if hasattr(approval, "to_dict") else dict(approval)
    algorithm = str(data.get("signature_algorithm") or "")
    if algorithm == "simulation-only":
        # Simulation approvals are accepted only on legacy/dev paths that do not
        # pass an evidence bundle into the review gate.  Evidence-bound reviews
        # are filtered by ``TwoFactorReviewGate.validate`` before roles count.
        return bool(data.get("signature"))
    if not (data.get("signature") and algorithm):
        return False
    expected_digest = review_approval_digest(data)
    if data.get("review_approval_hash") and data.get("review_approval_hash") != expected_digest:
        return False
    mapped = {
        "audit_signature": data.get("signature"),
        "audit_signature_algorithm": algorithm,
        "audit_signer_id": data.get("reviewer_id"),
        "audit_public_key_b64": data.get("reviewer_public_key_b64"),
    }
    return verify_signature_payload(expected_digest, mapped)


class TwoFactorReviewGate:
    """Require two distinct signed roles for soft-RED approval.

    In production mode the review gate rejects shared-secret HMAC approvals and
    requires distinct Ed25519 reviewer public keys.  HMAC approvals remain
    available only for local/dev compatibility because they do not prove
    reviewer independence.
    """

    def __init__(self, required_roles: set[str] | None = None, *, production_mode: bool | None = None):
        self.required_roles = required_roles or {"security_auditor", "system_operator"}
        self.production_mode = (
            os.getenv("LRSI_PRODUCTION_MODE", "").lower().strip() in {"1", "true", "yes", "on"}
            if production_mode is None else bool(production_mode)
        )

    def validate(self, approvals: list[dict | ReviewApproval], *, action: str = "approve", evidence_bundle: dict | None = None) -> tuple[bool, list[str]]:
        normalized = [a.to_dict() if hasattr(a, "to_dict") else dict(a) for a in approvals or []]
        reasons: list[str] = []
        matching = [a for a in normalized if a.get("action") == action]
        evidence_bound = evidence_bundle is not None
        valid_matching: list[dict[str, Any]] = []
        for approval in matching:
            is_simulation = approval.get("signature_algorithm") == "simulation-only"
            valid = verify_review_approval_signature(approval)
            if evidence_bound and is_simulation:
                valid = False
            if valid:
                valid_matching.append(approval)
            else:
                reasons.append(f"review_approval_signature_invalid:{approval.get('reviewer_id', 'unknown')}")
        roles = {a.get("role") for a in valid_matching}
        reviewer_ids = {a.get("reviewer_id") for a in valid_matching if a.get("reviewer_id")}
        if self.production_mode:
            public_keys = {
                a.get("reviewer_public_key_b64") for a in valid_matching if a.get("reviewer_public_key_b64")
            }
            non_ed25519 = [
                a.get("reviewer_id", "unknown")
                for a in valid_matching
                if not str(a.get("signature_algorithm") or "").startswith("Ed25519")
            ]
            if non_ed25519:
                reasons.append(f"production_review_requires_ed25519:{sorted(non_ed25519)}")
            if len(public_keys) < 2:
                reasons.append("production_review_requires_distinct_reviewer_public_keys")
        if len(valid_matching) < 2:
            reasons.append("two_factor_review_requires_two_valid_signed_approvals")
        if len(reviewer_ids) < 2:
            reasons.append("two_factor_review_requires_distinct_reviewers")
        missing_roles = self.required_roles - roles
        if missing_roles:
            reasons.append(f"two_factor_review_missing_roles:{sorted(missing_roles)}")
        if evidence_bundle is not None:
            case_id = evidence_bundle.get("case_id")
            evidence_hash = evidence_bundle.get("evidence_bundle_hash")
            if not case_id or not evidence_hash or not evidence_bundle.get("evidence_signature"):
                reasons.append("signed_evidence_bundle_required")
            else:
                try:
                    from evidence import verify_evidence_bundle_signature
                    if not verify_evidence_bundle_signature(evidence_bundle):
                        reasons.append("signed_evidence_bundle_invalid")
                except Exception:
                    reasons.append("signed_evidence_bundle_invalid")
            for approval in valid_matching:
                if approval.get("evidence_case_id") != case_id:
                    reasons.append("review_approval_case_id_mismatch")
                approval_hash = approval.get("evidence_bundle_hash")
                if approval_hash != evidence_hash:
                    reasons.append("review_approval_evidence_hash_mismatch")
        return not reasons, reasons

    @staticmethod
    def simulated_approval(role: str, *, reviewer_id: str | None = None, case_id: str | None = None, evidence_bundle_hash: str | None = None) -> ReviewApproval:
        rid = reviewer_id or f"{role}-{uuid4().hex[:8]}"
        return ReviewApproval(
            reviewer_id=rid,
            role=role,
            action="approve",
            rationale="simulated signed approval for validation",
            signature=f"sim-signature-{rid}",
            signature_algorithm="simulation-only",
            evidence_case_id=case_id,
            evidence_bundle_hash=evidence_bundle_hash,
        )

    @staticmethod
    def signed_approval(role: str, *, reviewer_id: str | None = None, case_id: str | None = None, evidence_bundle_hash: str | None = None, rationale: str = "reviewed evidence and runtime state") -> ReviewApproval:
        rid = reviewer_id or f"{role}-{uuid4().hex[:8]}"
        return sign_review_approval(
            reviewer_id=rid,
            role=role,
            rationale=rationale,
            evidence_case_id=case_id,
            evidence_bundle_hash=evidence_bundle_hash,
        )
