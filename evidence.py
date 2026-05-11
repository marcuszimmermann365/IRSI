"""LRSI V11.1 — Evidence Bundle / Case File generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from signing import adapter_from_env, verify_signature_payload


@dataclass
class EvidenceBundle:
    case_id: str
    schema: str
    iteration: int
    final_decision: str
    change_proposal: dict[str, Any]
    prompt_diff: dict[str, Any]
    policy_diff: dict[str, Any]
    activated_thresholds: list[dict[str, Any]]
    drel_dimensions: dict[str, Any]
    council_counterarguments: list[dict[str, Any]]
    final_gate_diagnostics: dict[str, Any]
    reviewer_hint: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_bundle_hash: str | None = None
    evidence_signature: str | None = None
    evidence_signature_algorithm: str | None = None
    evidence_signer_id: str | None = None
    evidence_public_key_b64: str | None = None

    def _unsigned_payload(self) -> dict:
        data = asdict(self)
        for key in (
            "evidence_bundle_hash",
            "evidence_signature",
            "evidence_signature_algorithm",
            "evidence_signer_id",
            "evidence_public_key_b64",
        ):
            data.pop(key, None)
        return data

    @staticmethod
    def _canonical(data: dict) -> str:
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def sign(self):
        payload = self._unsigned_payload()
        digest = hashlib.sha256(self._canonical(payload).encode("utf-8")).hexdigest()
        self.evidence_bundle_hash = digest
        signer = adapter_from_env()
        if signer:
            meta = signer.public_metadata()
            self.evidence_signature_algorithm = meta.get("audit_signature_algorithm")
            self.evidence_signer_id = meta.get("audit_signer_id")
            self.evidence_public_key_b64 = meta.get("audit_public_key_b64")
            self.evidence_signature = signer.sign(digest.encode("utf-8"))
        return self

    def to_dict(self) -> dict:
        if not self.evidence_bundle_hash:
            self.sign()
        return asdict(self)


def verify_evidence_bundle_signature(bundle: dict, *, key: str | None = None) -> bool:
    if not bundle.get("evidence_bundle_hash"):
        return False
    mapped = dict(bundle)
    mapped["audit_signature"] = mapped.get("evidence_signature")
    mapped["audit_signature_algorithm"] = mapped.get("evidence_signature_algorithm")
    mapped["audit_signer_id"] = mapped.get("evidence_signer_id")
    mapped["audit_public_key_b64"] = mapped.get("evidence_public_key_b64")
    return verify_signature_payload(bundle["evidence_bundle_hash"], mapped, key=key)


class EvidenceGenerator:
    """Generate operator-oriented case files for HOLD/RED/STOP decisions."""

    def __init__(self, threshold_registry: dict | None = None):
        self.threshold_registry = threshold_registry or {"thresholds": []}

    def _threshold_map(self) -> dict[str, dict]:
        return {t.get("threshold_id"): t for t in self.threshold_registry.get("thresholds", [])}

    def _activated_thresholds(self, ctx: Any) -> list[dict[str, Any]]:
        registry = self._threshold_map()
        activated: list[dict[str, Any]] = []
        checks = [
            ("DREL_BLOCKER_THRESHOLD", getattr(ctx, "drel_status", None) == "RED", getattr(ctx, "drel_reason", "")),
            ("A3_SYNTH_SINCERITY_BLOCK", getattr(ctx, "ss_risk", 0.0) >= 0.65, getattr(ctx, "ss_risk", 0.0)),
            ("MIN_REAL_AGENCY_FOR_GO", getattr(ctx, "real_agency", 1.0) < 0.40, getattr(ctx, "real_agency", 1.0)),
            ("EXTERNAL_OPENNESS_FLOOR", getattr(ctx, "o_ext", 1.0) < 0.40, getattr(ctx, "o_ext", 1.0)),
            ("SEMANTIC_PROMPT_DRIFT_WARNING", getattr(ctx, "semantic_drift", {}).get("decision") in {"YELLOW", "RED"}, getattr(ctx, "semantic_drift", {}).get("distance")),
        ]
        for threshold_id, active, observed in checks:
            if active:
                item = dict(registry.get(threshold_id, {"threshold_id": threshold_id}))
                item["observed"] = observed
                activated.append(item)
        return activated

    def generate(self, ctx: Any) -> EvidenceBundle:
        proposal = getattr(ctx, "dgm_proposal", None)
        proposal_dict = proposal.to_dict() if proposal is not None and hasattr(proposal, "to_dict") else {}
        prompt_meta = getattr(ctx, "prompt_meta", {}) or {}
        policy_meta = getattr(ctx, "policy_meta", {}) or {}
        per_role = getattr(ctx, "per_role", {}) or {}
        counterarguments = []
        for role, payload in per_role.items():
            if isinstance(payload, dict) and payload.get("decision") in {"YELLOW", "RED"}:
                counterarguments.append({"role": role, **payload})
        bundle = EvidenceBundle(
            case_id=f"case-{uuid4().hex[:12]}",
            schema="lrsi.evidence_bundle.v1",
            iteration=getattr(ctx, "iteration", -1),
            final_decision=getattr(ctx, "final_decision", getattr(ctx, "ext_decision", "UNKNOWN")),
            change_proposal=proposal_dict,
            prompt_diff={
                "original_prompt": prompt_meta.get("original_prompt"),
                "new_prompt": prompt_meta.get("new_prompt"),
                "mutation": prompt_meta.get("mutation"),
                "semantic_drift": getattr(ctx, "semantic_drift", {}),
                "preproposal_adversarial": prompt_meta.get("preproposal_adversarial"),
            },
            policy_diff={
                "description": policy_meta.get("description"),
                "section": policy_meta.get("section"),
                "changed_sections": policy_meta.get("changed_sections", []),
            },
            activated_thresholds=self._activated_thresholds(ctx),
            drel_dimensions=getattr(ctx, "drel_diag", {}) or {},
            council_counterarguments=counterarguments,
            final_gate_diagnostics=getattr(ctx, "ext_diag", {}) or {},
            reviewer_hint=(
                "Review change proposal, activated thresholds, DREL dimensions and council "
                "counterarguments before any human override. Soft RED approval requires two "
                "distinct signed roles in production validation."
            ),
        )
        return bundle.sign()
