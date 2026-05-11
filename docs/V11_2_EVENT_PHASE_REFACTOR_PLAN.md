# V11.2 Event-Based Phase Refactor Plan

## Goal

V11.2 introduces the runtime seam needed to move LRSI from an imperative, method-driven runner toward a declarative, event-based, phase-oriented architecture.

The immediate target is not to rewrite every phase at once. The target is to create a safe migration path:

1. define a stable phase interface,
2. provide type-safe dependency resolution,
3. force immutable phase outputs,
4. run the iteration through a declarative phase list,
5. generate phase audit entries automatically.

The existing hash-chain audit remains the integrity boundary for persisted iteration records.

---

## 1. Phase Interface

Implemented in `pipeline/phase_runtime.py`:

```python
class BasePhase(Protocol):
    name: str
    input_type: ClassVar[type]
    required_keys: ClassVar[tuple[str, ...]]

    def build_input(self, registry: ContextRegistry) -> Any:
        ...

    def run(self, phase_input: Any) -> PhaseResult:
        ...
```

A phase must now declare the keys it needs and construct its own typed input object from the registry.

---

## 2. Type-Safe Dependency Injection

`ContextRegistry` is an immutable key-value registry. The runner exposes current runtime values through it:

```python
registry = ContextRegistry.from_context(
    ctx,
    governance_mode=self.governance.current_mode(),
    baseline_metrics=self.baseline_metrics,
    agent=self.agent,
    council=self.council,
    dgm_requirements=ctx.dgm_reqs,
)
```

Each phase calls:

```python
values = registry.require(self.required_keys)
return MyPhaseInput(**values)
```

This makes missing dependencies fail early and explicitly.

---

## 3. Immutability

All declarative phase results are carried by `PhaseResult`:

```python
@dataclass(frozen=True)
class PhaseResult:
    phase: str
    decision: str
    reason: str = ""
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    patch: Mapping[str, Any] = field(default_factory=dict)
    trace_entries: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    terminal: bool = False
```

A phase no longer directly mutates `IterationContext`. It returns a patch. The runner/`PhaseExecutor` merges this patch explicitly.

During the migration window, old phases are connected through `MethodPhaseAdapter`. These adapters are compatibility shims only; new phase work should use typed inputs and immutable results.

---

## 4. Declarative Pipeline

`PipelineExecution.run_iteration()` now iterates a phase list:

```python
ctx = self.prepare_iteration(iteration)
registry = self._phase_registry(ctx)
for phase in self._build_iteration_phases():
    registry, result = self.phase_executor.execute(phase, registry, ctx=ctx)
    registry = self._phase_registry(ctx).merge_result(result)
    if result.terminal:
        return
```

The current V11.2 phase list is:

```text
review_mode
mutation_contract
council_phase
hold_logic
human_review
erosion_and_human_coupling
attractor_checks
adversarial_layers
final_gate
apply_or_reject_candidate
persist_iteration_record
```

---

## 5. Audit Seam

Every `PhaseResult` can generate its own phase audit event mechanically:

```python
result.audit_entry(iteration=ctx.iteration)
```

`PhaseExecutor` appends that event to `ctx.phase_audit` centrally. The phase business logic does not manually create audit entries.

The final iteration record includes:

```json
"phase_audit": [
  {
    "audit_event_type": "phase_result",
    "phase": "council_phase",
    "decision": "YELLOW",
    "patch_keys": ["council_decision", "gate_diag", "verdicts"]
  }
]
```

Because `phase_audit` is embedded before the record is persisted, the existing `record_hash` and `previous_record_hash` chain protect these phase-level events.

---

## CouncilPhase Example

### Before: Imperative with many kwargs

Older runner code called `CouncilPhase.run(...)` with a long list of keyword arguments and then manually copied fields back into `ctx`.

### After: Declarative input + immutable patch

`CouncilPhaseInput`:

```python
@dataclass(frozen=True)
class CouncilPhaseInput:
    iteration: int
    parent_metrics: dict[str, Any]
    child_metrics: dict[str, Any]
    baseline_metrics: dict[str, Any]
    governance_mode: str
    adjusted_thresholds: dict[str, Any]
    agent: Any
    candidate: Any
    role_verifier: Any
    role_policy: Any
    role_critic: Any
    role_truth: Any
    counter_checker: Any
    truth_layer: Any
    council_stage: Any
    council: Any
    dgm_requirements: dict[str, Any]
```

`CouncilPhase` declares:

```python
required_keys = (
    "iteration", "parent_metrics", "child_metrics", "baseline_metrics",
    "governance_mode", "adjusted_thresholds", "agent", "candidate",
    "role_verifier", "role_policy", "role_critic", "role_truth",
    "counter_checker", "truth_layer", "council_stage", "council",
    "dgm_requirements",
)
```

The phase returns a `PhaseResult` with explicit patch keys:

```python
PhaseResult(
    phase="council_phase",
    decision=result.council_decision,
    reason="|".join(result.council_reasons),
    diagnostics={...},
    patch={
        "verdicts": result.verdicts,
        "gate_d": result.gate_decision,
        "gate_diag": result.gate_diagnostics,
        "council_decision": result.council_decision,
        "council_reasons": result.council_reasons,
        ...
    },
    trace_entries=(result.trace_entry,),
)
```

The runner does not know CouncilPhase internals. It only merges the patch and appends the generated phase audit event.

---

## Migration Roadmap

### V11.2 completed

- Base phase protocol
- Context registry
- Phase result envelope
- Phase executor
- Declarative iteration loop
- CouncilPhase migrated to typed input
- Phase audit embedded in hashed records

### Next migrations

1. Convert `MutationContractPhase` from adapter to typed input/result.
2. Convert `FinalGatePhase` to typed input/result.
3. Convert `AdversarialPhase` to return `PhaseResult` directly instead of an intermediate compatibility result.
4. Split `IterationContext` into smaller immutable phase contexts.
5. Persist optional per-phase audit events to an external event store in addition to embedding them in iteration records.
