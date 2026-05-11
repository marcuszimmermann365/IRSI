# LRSI v10.1 Human Review Contract

V10.1 keeps the existing fail-closed `HumanOverrideLayer` and documents the missing production boundary explicitly.

## Prototype behavior

- Simulation mode can auto-confirm review paths for tests.
- Production mode without a real human adapter refuses to proceed.
- DGM governance-layer changes force mandatory human review.

## Production adapter requirements

A future production adapter must provide:

1. authenticated reviewer identity
2. role and authorization scope
3. explicit action: approve, defer, reject, override
4. structured rationale
5. non-editable timestamp
6. signed or tamper-evident audit record
7. hard limits: immutable-core REDs cannot be turned into GREEN by ordinary override
8. review evidence bundle: proposal, metrics, dissent, gate diagnostics, rollback plan

## v10.1 invariant

Human review is not a rubber stamp. If the DGM contract requires review, the runner records `dgm_requires_human_review` as a trigger reason.

## v10.2 override classes

V10.2 adds a typed distinction between reviewable and non-overridable REDs:

```text
soft_red
hard_red
immutable_red
external_integrity_red
```

Only `soft_red` may be moved toward acceptance by a human `APPROVE` action.
`hard_red`, `immutable_red`, and `external_integrity_red` cannot be converted
into GREEN through override. Human `REJECT` and `FORCE_HOLD` remain available
because they reduce risk rather than erase a veto.

This is still not a production human-review interface. It is a stronger
runtime contract for any future CLI or UI.
