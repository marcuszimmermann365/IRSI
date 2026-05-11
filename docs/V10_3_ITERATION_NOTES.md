# V10.3 Iteration Notes

## Intent

V10.3 responds to the review instruction: **structure `main()` in any case**.
The iteration therefore avoids adding another safety heuristic and focuses on
execution structure, typed contracts and audit hardening.

## Changes

1. `runner.py` is now a thin entry point delegating to `PipelineRunner`.
2. The preserved V10.2 semantic loop moved to `pipeline/runner_core.py`.
3. `PipelineRunner` exposes lifecycle hooks: prepare, run structured iterations,
   finish.
4. `Storage.__init__()` initializes under `file_lock()`.
5. Persisted audit records include `previous_record_hash` and `record_hash`.
6. `verify_hash_chain()` detects local tampering.
7. `DGMRequirements` normalizes DGM requirement dictionaries.
8. `dgm_bridge.py` no longer modifies `sys.path`.
9. CI includes V10.3 tests and `dgm_bridge.py` in the hardened static surface.
10. Release packaging excludes caches and local runtime artifacts.

## Limits

The inner semantic loop is intentionally preserved for invariant stability. V10.3
is not a full production rewrite. The next structural step is to move the inner
loop from preserved legacy semantics into real phase objects such as:

```text
prepare_iteration()
run_mutation_contract()
run_council()
run_human_review()
run_attractor_checks()
run_adversarial_layers()
run_final_gate()
apply_or_reject_candidate()
persist_record()
```

V10.3 makes the top-level entry safe and testable enough to support that next
extraction without changing behavior and without hiding the remaining work.
