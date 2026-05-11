"""Small typed phase contexts introduced in V10.6.

The legacy IterationContext remains the compatibility carrier, but phase services
now receive narrow projections for critical boundaries.  This reduces accidental
coupling and gives mypy/ruff a smaller surface to harden incrementally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ImmutablePhaseContext:
    """Read-only iteration snapshot for gradual removal of mutable god-context use.

    The runner still passes the legacy ``ctx`` where old adapters need it, but
    new phases can depend on this immutable view instead of taking a mutable
    ``IterationContext`` reference. Values are shallow snapshots: container
    objects keep their existing identity for compatibility, while the key/value
    surface itself is immutable and auditable.
    """

    iteration: int
    trace_id: str | None
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))

    @classmethod
    def from_iteration(cls, ctx: Any, *, keys: tuple[str, ...] | None = None) -> "ImmutablePhaseContext":
        if keys is None:
            keys = tuple(
                name for name in getattr(ctx, "__dataclass_fields__", {})
                if not name.startswith("_")
            )
        values = {name: getattr(ctx, name) for name in keys if hasattr(ctx, name)}
        return cls(
            iteration=getattr(ctx, "iteration"),
            trace_id=getattr(ctx, "trace_id", None),
            values=values,
        )

    def require(self, *keys: str) -> dict[str, Any]:
        missing = [key for key in keys if key not in self.values]
        if missing:
            raise KeyError(f"missing immutable phase context keys: {', '.join(missing)}")
        return {key: self.values[key] for key in keys}


@dataclass(frozen=True)
class RuntimePhaseContext:
    iteration: int
    governance_mode: str
    schema_version: str


@dataclass(frozen=True)
class EvaluationPhaseContext:
    iteration: int
    mode: str | None
    prompt_hashable_id: str


@dataclass(frozen=True)
class AdversarialPhaseContext:
    iteration: int
    council_decision: str
    child_llm_error_rate: float
    child_fixture_miss_rate: float
    trace_length_before: int

    @classmethod
    def from_iteration(cls, ctx: Any) -> "AdversarialPhaseContext":
        return cls(
            iteration=ctx.iteration,
            council_decision=ctx.council_decision,
            child_llm_error_rate=float(ctx.child_metrics.get("llm_error_rate", 0.0)),
            child_fixture_miss_rate=float(ctx.child_metrics.get("fixture_miss_rate", 0.0)),
            trace_length_before=len(ctx.decision_trace),
        )


@dataclass(frozen=True)
class AuditPhaseContext:
    iteration: int
    final_decision: str
    accepted: bool
    event_type: str = "iteration_record"
    expected_required_fields: tuple[str, ...] = field(default=(
        "schema_version",
        "iteration",
        "final_decision",
        "decision_trace",
        "accepted",
    ))

    @classmethod
    def from_iteration(cls, ctx: Any) -> "AuditPhaseContext":
        return cls(
            iteration=ctx.iteration,
            final_decision=ctx.final_decision,
            accepted=ctx.accepted,
        )
