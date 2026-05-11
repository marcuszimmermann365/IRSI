# V11.4 — Safety Diagnostics Migration

## Goal

V11.4 migrates the most important safety diagnostics from permissive shared-context mutation into the event-based phase runtime introduced in V11.2 and expanded in V11.3.

The migration target was:

```text
AttractorPhase
AdversarialPhase with Subresults
DREL / A3 / A4 / Sham / Carrier / Complexity as nested typed outputs
```

## Design constraints

V11.4 intentionally avoids introducing new safety heuristics. It preserves the V11.3 decision semantics and changes how diagnostics are structured, merged and audited.

Each migrated diagnostic phase now follows the same pattern:

```text
ContextRegistry -> explicit PhaseInput -> immutable nested Output -> PhaseResult.patch -> automatic phase_audit
```

## Migrated phases

### AttractorPhase

New contracts:

- `AttractorPhaseInput`
- `AttractorDiagnosticsOutput`

The phase now owns:

- current attractor state
- Σ / L / O / D values
- component diagnostics
- gating anchor source
- candidate diagnostic comparison
- trace entries for attractor evaluation

The final record includes `attractor_diagnostics_v11_4`.

### AdversarialPhase

New contracts:

- `AdversarialPhaseInput`
- `AdversarialDiagnosticsOutput`

Nested typed suboutputs:

- `DRELDiagnosticOutput`
- `A3DiagnosticOutput`
- `AgencyDiagnosticOutput`
- `A4DiagnosticOutput`
- `ParetoDiagnosticOutput`
- `ShamResonanceOutput`
- `CarrierErosionOutput`
- `ComplexityAdmissibilityOutput`
- `AuxiliaryIndicatorsOutput`

The final record includes `adversarial_diagnostics_v11_4`.

## Audit seam

The `PhaseExecutor` still derives audit entries from `PhaseResult`. Business logic does not hand-write its own audit entries. The final `phase_audit` now includes:

```text
attractor_phase
adversarial_phase
```

Those entries are inside the final persisted record and therefore protected by the existing hash-chain.

## Compatibility

Legacy direct-call surfaces remain where existing tests or helper methods still use them. Normal runtime execution uses the new declarative phases.

## Validation

```text
python -m compileall -q .
python -m pytest -q -rs
python stress_tests_v114_safety_diagnostics.py
```

## Remaining migration waves

The next planned wave is V11.5: Self-Modification Boundary Migration.

Target candidates:

- `MutationPhase`
- `PreProposalAdversarialPhase`
- `DGMPrecheckPhase`
- `DGMPostcheckPhase`
