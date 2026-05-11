# Replay Checks

Replay checks should verify that each benchmark can be reconstructed from the
canonical event stream without relying on `run_log.json`, live LLM calls, mutable
local memory, or wall-clock state.

Minimum replay checks:

1. verify event chain;
2. reconstruct final decision;
3. compare replay decision with runtime decision;
4. fail if event tampering is detected;
5. fail if a materialized view changes replay outcome.
