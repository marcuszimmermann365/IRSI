# Contributing to LRSI Runtime Core

**Thank you for considering contributing to LRSI!**

We are building a serious research platform for AI safety, interruptibility, auditability, and replayable runtime decisions. Every contribution that respects the core safety principles is welcome.

## Quick Start (5 minutes)

```bash
git clone https://github.com/marcuszimmermann365/IRSI.git
cd IRSI
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q --tb=no
```

On Windows PowerShell:

```powershell
git clone https://github.com/marcuszimmermann365/IRSI.git
cd IRSI
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q --tb=no
```

## Good First Issues

We actively label issues that are suitable for new contributors.

| Label | What it means | Examples |
|---|---|---|
| `good first issue` | Small, well-scoped, low risk | Docstrings, type hints, tests, diagrams |
| `documentation` | Improve clarity or add examples | README, ARCHITECTURE.md, docstrings |
| `refactor` | Improve code structure without changing behavior | Split large dataclasses, better naming |
| `testing` | Add or improve tests | Property-based tests, edge cases |
| `help wanted` | We especially need help here | Visual diagrams, onboarding improvements |

Current good first issue candidates:

1. Add type hints to `invariants.py`.
2. Create Mermaid diagrams for the phase flow.
3. Improve docstrings in `pipeline/runner_core.py`.
4. Write additional property-based tests for the self-modification boundary.
5. Extract smaller context objects from `IterationContext`.

See also `docs/good-first-issues.md`.

## Development Workflow

1. Create a new branch:

   ```bash
   git checkout -b feature/your-improvement
   ```

2. Make your changes. Keep them focused and small.

3. Run the required checks:

   ```bash
   python -m compileall -q .
   python -m pytest -q -rs
   python scripts/check_phase_event_coverage.py --run-sample --iterations 3
   ```

4. For security-relevant files also run:

   ```bash
   python -m pytest tests/test_v122_property_based_security.py -q
   python -m pytest tests/test_v130_integration_runtime.py -q
   ```

5. Open a Pull Request with a clear description.

## Security-Sensitive Areas

Changes to the following files require extra care and review:

- `invariants.py`
- `security_errors.py`
- `eventsourcing.py`
- `storage.py`
- `pipeline/self_modification_phases.py`
- `pipeline/phase_runtime.py`
- `pipeline/phase_flow.py`

Rule: if your change touches any of these files, mention it clearly in the PR and consider adding or updating invariants and tests.

## Rules for New Phases

A new decision-relevant phase should include:

- typed input contract;
- typed output, usually `PhaseResult` or similar;
- bounded diagnostics;
- event emission;
- replay relevance;
- tests;
- relevant invariant coverage.

## Communication and Tone

- We value clarity over cleverness.
- Keep public claims restrained: this is a research runtime, not a certified safety product.
- Be respectful and constructive in reviews.
- Prefer small, reviewable pull requests over large rewrites.
- When in doubt, preserve backward compatibility and add tests first.

## Questions?

Feel free to open an issue with the label `question` or start a discussion once discussions are enabled. We are happy to help you get started.

Thank you for helping make AI systems more interruptible and auditable.
