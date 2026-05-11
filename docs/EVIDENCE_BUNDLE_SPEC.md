# Evidence Bundle / Case File Specification

When the runtime emits a HOLD/RED/STOP-style decision, V11.1 generates an `evidence_bundle`.

Fields:

- `case_id`
- `change_proposal`
- `prompt_diff`
- `policy_diff`
- `activated_thresholds`
- `drel_dimensions`
- `council_counterarguments`
- `final_gate_diagnostics`
- `reviewer_hint`

Purpose: A human operator should understand within seconds why the system stopped or requested review.

The case file is an operator artifact, not a proof of correctness. It makes diagnostics actionable and reviewable.
