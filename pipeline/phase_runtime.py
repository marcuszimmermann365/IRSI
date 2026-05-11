"""
LRSI V11.2 — Event-based declarative phase runtime
====================================================

This module introduces the first production-facing runtime seam for moving the
pipeline away from a mutable "god context" toward explicit phase contracts:

* ``BasePhase`` declares required registry keys and a typed ``run`` boundary.
* ``ContextRegistry`` resolves dependencies by key and merges immutable results.
* ``PhaseResult`` is the single result/audit carrier for phase outcomes.
* ``PhaseExecutor`` invokes phases, applies explicit patches, and records phase
  audit events without requiring business logic to hand-roll audit entries.

V11.2 intentionally keeps a compatibility adapter for legacy phase methods so
that historical safety invariants remain executable while individual phases are
migrated to typed inputs. ``CouncilPhase`` is the first fully typed migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Callable, ClassVar, Mapping, Protocol, runtime_checkable

from eventsourcing import RuntimeEvent
from version import SCHEMA_VERSION


@dataclass(frozen=True)
class PhaseResult:
    """Immutable output envelope for every declarative phase.

    ``patch`` is the only sanctioned way for a phase to request changes to an
    iteration context. The runner/registry performs the merge explicitly.
    ``audit_entry`` is derived mechanically from this object, preserving the
    business/audit seam.
    """

    phase: str
    decision: str
    reason: str = ""
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    patch: Mapping[str, Any] = field(default_factory=dict)
    trace_entries: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    terminal: bool = False
    audit_already_in_patch: bool = False
    schema_version: str = SCHEMA_VERSION

    def audit_entry(self, *, iteration: int | None = None) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "schema_version": self.schema_version,
            "audit_event_type": "phase_result",
            "phase": self.phase,
            "decision": self.decision,
            "reason": self.reason,
            "diagnostics": dict(self.diagnostics),
            "patch_keys": sorted(self.patch.keys()),
            "terminal": bool(self.terminal),
        }
        if iteration is not None:
            entry["iteration"] = iteration
        if self.trace_entries:
            entry["trace_entries"] = [dict(e) for e in self.trace_entries]
        return entry

    def to_dict(self) -> dict[str, Any]:
        return self.audit_entry()


@runtime_checkable
class BasePhase(Protocol):
    """Protocol for V11.2 declarative pipeline phases."""

    name: str
    input_type: ClassVar[type]
    required_keys: ClassVar[tuple[str, ...]]

    def build_input(self, registry: "ContextRegistry") -> Any:
        """Build the typed phase input from the registry."""
        ...

    def run(self, phase_input: Any) -> PhaseResult:
        """Execute phase logic and return an immutable ``PhaseResult``."""
        ...


@dataclass(frozen=True)
class ContextRegistry:
    """Immutable key-value registry for type-safe phase dependency lookup."""

    values: Mapping[str, Any]

    def require(self, keys: tuple[str, ...] | list[str]) -> dict[str, Any]:
        missing = [key for key in keys if key not in self.values]
        if missing:
            raise KeyError(f"missing phase dependencies: {', '.join(missing)}")
        return {key: self.values[key] for key in keys}

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def with_values(self, **updates: Any) -> "ContextRegistry":
        merged = dict(self.values)
        merged.update(updates)
        return ContextRegistry(merged)

    def merge_result(self, result: PhaseResult) -> "ContextRegistry":
        merged = dict(self.values)
        for key, value in dict(result.patch).items():
            if (
                isinstance(value, tuple)
                and len(value) == 2
                and value[0] == "__append__"
            ):
                current = list(merged.get(key, []) or [])
                current.extend(list(value[1] or []))
                merged[key] = current
            else:
                merged[key] = value
        return ContextRegistry(merged)

    @classmethod
    def from_context(cls, ctx: Any, **dependencies: Any) -> "ContextRegistry":
        values: dict[str, Any] = dict(dependencies)
        # expose dataclass/object fields under their attribute names
        if is_dataclass(ctx):
            for f in fields(ctx):
                values.setdefault(f.name, getattr(ctx, f.name))
        for name in dir(ctx):
            if name.startswith("_"):
                continue
            unreadable = False
            try:
                value = getattr(ctx, name)
            except Exception:
                unreadable = True
                value = None
            if unreadable or callable(value):
                continue
            values.setdefault(name, value)
        values.setdefault("ctx", ctx)
        return cls(values)


def _apply_patch_to_context(ctx: Any, patch: Mapping[str, Any]) -> None:
    for key, value in patch.items():
        # V11.6: small immutable-result merge helper. A phase can request an
        # append-only list merge without mutating the context directly by
        # returning {"field": ("__append__", [items...])}.
        if (
            isinstance(value, tuple)
            and len(value) == 2
            and value[0] == "__append__"
        ):
            current = list(getattr(ctx, key, []) or [])
            current.extend(list(value[1] or []))
            setattr(ctx, key, current)
            continue
        setattr(ctx, key, value)


def _append_phase_audit(ctx: Any, result: PhaseResult) -> None:
    events = list(getattr(ctx, "phase_audit", []) or [])
    entry = result.audit_entry(iteration=getattr(ctx, "iteration", None))
    trace_id = getattr(ctx, "trace_id", None)
    if trace_id and "trace_id" not in entry:
        entry["trace_id"] = trace_id
    events.append(entry)
    setattr(ctx, "phase_audit", events)

    # V12.0: every PhaseResult also emits an event.  The event is not written
    # directly by business logic; persistence/audit infrastructure decides where
    # and how it is committed.  This keeps the audit seam automatic.
    phase_events = list(getattr(ctx, "phase_events_v12", []) or [])
    runtime_event = RuntimeEvent.from_phase_result(
        result=result,
        iteration=getattr(ctx, "iteration", None),
        trace_id=trace_id,
        stream_id=f"iteration-{getattr(ctx, 'iteration', 'unknown')}",
    ).to_dict()
    phase_events.append(runtime_event)
    setattr(ctx, "phase_events_v12", phase_events)


@dataclass
class PhaseExecutor:
    """Executes phases and centralizes result merge + phase audit."""

    def execute(
        self,
        phase: BasePhase,
        registry: ContextRegistry,
        *,
        ctx: Any | None = None,
    ) -> tuple[ContextRegistry, PhaseResult]:
        phase_input = phase.build_input(registry)
        result = phase.run(phase_input)
        if ctx is not None:
            _apply_patch_to_context(ctx, result.patch)
            for trace in result.trace_entries:
                if hasattr(ctx, "decision_trace"):
                    ctx.decision_trace.append(dict(trace))
            if not result.audit_already_in_patch:
                _append_phase_audit(ctx, result)
        return registry.merge_result(result), result


@dataclass(frozen=True)
class MethodPhaseInput:
    ctx: Any
    method: Callable[[Any], Any]


class MethodPhaseAdapter:
    """Compatibility adapter for legacy phases during gradual migration.

    It lets the runner already use a declarative phase list while individual
    phases are migrated to explicit input dataclasses. New code should prefer
    fully typed phase classes such as ``CouncilPhase``.
    """

    input_type: ClassVar[type] = MethodPhaseInput

    def __init__(
        self,
        *,
        name: str,
        method: Callable[[Any], Any],
        decision: str = "DONE",
        terminal_on: Callable[[Any], bool] | None = None,
        reason_fn: Callable[[Any], str] | None = None,
    ):
        self.name = name
        self.required_keys = ("ctx",)
        self._method = method
        self._decision = decision
        self._terminal_on = terminal_on
        self._reason_fn = reason_fn

    def build_input(self, registry: ContextRegistry) -> MethodPhaseInput:
        values = registry.require(self.required_keys)
        return MethodPhaseInput(ctx=values["ctx"], method=self._method)

    def run(self, phase_input: MethodPhaseInput) -> PhaseResult:
        outcome = phase_input.method(phase_input.ctx)
        terminal = bool(self._terminal_on(outcome)) if self._terminal_on else False
        reason = self._reason_fn(outcome) if self._reason_fn else "legacy_adapter"
        return PhaseResult(
            phase=self.name,
            decision=self._decision,
            reason=reason,
            diagnostics={"adapter": "legacy_method", "outcome": outcome},
            terminal=terminal,
        )
