"""
LRSI v10.3–v10.5 — Contract Records
==============================
Typed records for the contract-bound pipeline. V10.3 adds typed DGM
requirements and keeps moving critical runner boundaries toward explicit
contracts and versioned audit records.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from version import SCHEMA_VERSION


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()




@dataclass(frozen=True)
class DGMRequirements:
    """Typed contract emitted by DGM pre-checks.

    The runner still serializes requirements as dictionaries for backward
    compatibility, but critical code can now normalize and validate the fields
    before using them.
    """

    requires_human_review: bool = False
    min_evaluators: int = 0
    bewaehrung_cycles: int = 0
    rollback_window_hours: int = 0
    target_layer: str = "adaptive"

    @classmethod
    def from_dict(cls, data: dict | None) -> "DGMRequirements":
        data = data or {}
        return cls(
            requires_human_review=bool(data.get("requires_human_review", False)),
            min_evaluators=int(data.get("min_evaluators", 0) or 0),
            bewaehrung_cycles=int(data.get("bewaehrung_cycles", 0) or 0),
            rollback_window_hours=int(data.get("rollback_window_hours", 0) or 0),
            target_layer=str(data.get("target_layer", "adaptive")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StageResult:
    """Minimal stage boundary result used by the v10.1 runner seams."""

    stage: str
    decision: str
    reason: str = ""
    diagnostics: dict = field(default_factory=dict)
    requirements: dict = field(default_factory=dict)

    def trace_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"stage": self.stage, "decision": self.decision, "reason": self.reason}
        if self.requirements:
            entry["requirements"] = self.requirements
        if self.diagnostics:
            entry["diagnostics"] = self.diagnostics
        return entry


@dataclass
class PipelineContext:
    iteration: int
    previous_policy: dict
    candidate_policy: dict | None
    effective_policy: dict | None
    parent_metrics: dict
    child_metrics: dict | None
    proposal: Any
    dgm_requirements: dict = field(default_factory=dict)
    decision_trace: list = field(default_factory=list)
    final_decision: str | None = None
    accepted: bool = False
    schema_version: str = SCHEMA_VERSION
    context_id: str = field(default_factory=lambda: f"ctx-{uuid4().hex[:12]}")
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        data = asdict(self)
        proposal = self.proposal
        if hasattr(proposal, "to_dict"):
            data["proposal"] = proposal.to_dict()
        return data
