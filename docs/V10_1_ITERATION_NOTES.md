# LRSI v10.1 Iteration Notes

V10.1 is an operability and maintainability iteration on top of V10.0.

## Implemented

- Added `version.py` as a single version/schema source of truth.
- Updated schema-bearing runtime records to `10.1`.
- Added explicit stage seams in `pipeline/stages.py`:
  - `GovernanceStage`
  - `MutationStage`
  - `DGMPrecheckStage`
  - `CouncilStage`
- Added record factories in `pipeline/records.py` for review and DGM pre-reject paths.
- Refactored `runner.py` to use these stage seams while preserving V10 behavior.
- Added file-locking around JSON persistence writes.
- Added explicit LLM modes:
  - `mock`
  - `fixture`
  - `live`
- Added default fixture file under `llm_fixtures/default.json`.
- Added `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/ci.yml`, and pytest wrappers.
- Added documentation for thresholds and human review contracts.

## Not yet claimed

- Full production-grade human review UI.
- Empirical threshold calibration.
- Full rewrite of every historical stress test into native pytest functions.
- Full decomposition of all 1000+ lines of runner semantics into independent stages.

## Design stance

V10.1 deliberately extracts only contract-critical seams first. This avoids rewriting the full runner in one risky move and preserves the established 597-test invariant surface.
