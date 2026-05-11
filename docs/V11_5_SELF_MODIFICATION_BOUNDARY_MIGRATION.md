# LRSI V11.5 — Self-Modification Boundary Migration

V11.5 migrates the self-modification boundary onto the event-based phase runtime introduced in V11.2 and expanded in V11.3/V11.4.

The release does **not** add a new safety heuristic. It makes the existing self-modification path explicit, typed and audit-visible.

## Migrated phases

| Phase | Purpose | Result surface |
|---|---|---|
| `MutationPhase` | creates candidate prompt/policy mutation | `MutationBoundaryOutput` |
| `PreProposalAdversarialPhase` | runs semantic-drift and pre-DGM adversarial checks | `PreProposalAdversarialOutput` |
| `DGMPrecheckPhase` | wraps mutation in `ChangeProposal` and gates governance entry | `DGMPrecheckOutputV115` |
| `DGMPostcheckPhase` | provides the explicit post-diagnostics DGM/Pareto audit seam | `DGMPostcheckOutputV115` |

## Audit behavior

Normal iterations now include the following phase-audit entries:

```text
mutation_phase
preproposal_adversarial_phase
dgm_precheck_phase
dgm_postcheck_phase
```

Terminal DGM pre-rejections, such as immutable-core violations, also preserve the self-modification phase audit up to the rejection point.

Final records include a new hash-protected block:

```json
"self_modification_boundary_v11_5": {
  "mutation": {},
  "preproposal": {},
  "dgm_precheck": {},
  "dgm_postcheck": {}
}
```

## Design note

`DGMPostcheckPhase` is treated as the authoritative V11.5 self-modification audit seam before the final gate. V11.4 adversarial diagnostics remain compatible and continue to expose nested Pareto diagnostics for historical record compatibility.

## Validation

```bash
python -m compileall -q .
python -m pytest -q -rs
python stress_tests_v115_selfmod_boundary.py
make check
```
