# Human Review Runtime Specification

## Review mode invariant

When governance mode is `review`, no mutation is evaluated or accepted. The runtime persists a HOLD audit record with:

```text
mode = review
final_decision = HOLD
accepted = False
```

This path is covered by `tests/test_v110_runtime_contracts.py`.

## Override boundary

Human approval may only move soft cases toward acceptance. These classes remain non-overridable toward acceptance:

```text
hard_red
immutable_red
external_integrity_red
```

Humans may still reject or force hold because these actions reduce risk.

## Production adapter requirement

`HumanOverrideLayer(simulation_mode=False)` refuses to start without a real `policy_fn`. The adapter should provide:

1. reviewer identity
2. role/scope authorization
3. evidence bundle hash
4. rationale
5. decision timestamp
6. signature or externally verifiable approval token

V11.0 supplies the runtime boundary; deployment must supply identity infrastructure.
