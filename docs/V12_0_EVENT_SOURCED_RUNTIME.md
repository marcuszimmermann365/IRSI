# V12.0 — Event-Sourced Runtime

V12.0 makes the runtime event stream the primary source for reconstructing decisions.

## Design goals

1. All phases emit events automatically through the `PhaseExecutor` seam.
2. The event stream is append-only and hash-chained.
3. Materialized iteration records remain available, but are treated as views.
4. Replay reconstructs final decisions from events.
5. Evidence bundles can be signed and bound to two-person review approvals.

## Runtime flow

```text
Phase.run(input)
  -> PhaseResult
  -> PhaseExecutor merges explicit patch
  -> PhaseExecutor appends phase.result RuntimeEvent to ctx.phase_events_v12
  -> PersistencePhase builds materialized record
  -> Storage completes/backfills phase.result events from phase_audit for terminal paths
  -> Storage writes phase events to *.events.jsonl
  -> Storage writes materialized audit.iteration_record event
  -> Projection/Replayer reconstructs decisions from events
```

## Compatibility

The existing `run_log.json` remains because many historical contract tests and operator workflows inspect materialized records.  In V12.0 the stronger replay contract is the event stream:

```python
storage.verify_event_chain()
storage.project_events()
storage.replay_decisions()
```

## P0 hardening notes

- Terminal records such as review-mode HOLD and DGM pre-check rejection are no longer allowed to skip phase events: `Storage.log_iteration()` backfills any missing `phase.result` events from `phase_audit` before persisting.
- Replay recognizes both the legacy `final_gate_phase` name and the current `final_gate` phase name.
- Production mode (`production_mode=True` or `LRSI_PRODUCTION_MODE=1`) requires signed event records and a WORM/external sink.

## Non-goals

V12.0 does not claim a certified production deployment.  It provides the runtime seams needed for one: WORM sink interface, event seals, signed evidence bundles and replayable projections.
