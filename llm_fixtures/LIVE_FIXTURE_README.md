# Live-recorded LLM fixture corpus

V10.6 adds the recorder needed to create replayable fixture corpora from real
LLM runs:

```bash
LLM_MODE=live OPENAI_API_KEY=... python scripts/record_live_fixtures.py --out llm_fixtures/live_recorded.json
LLM_MODE=fixture LLM_FIXTURE_PATH=llm_fixtures/live_recorded.json python runner.py
```

No external API credentials were available in the artifact build environment, so
this ZIP does **not** claim to contain newly captured external live responses.
`default.json` remains the deterministic CI fixture; `record_live_fixtures.py`
is the production path for adding genuine recorded fixtures.
