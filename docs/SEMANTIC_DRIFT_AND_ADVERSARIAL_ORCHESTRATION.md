# Semantic Drift and Mini Adversarial Orchestration

## SemanticDriftMonitor

The default monitor uses deterministic local n-gram embeddings. This is intentionally simple and reproducible. Production deployments can inject an embedding provider while keeping the same output contract:

- `distance`
- `similarity`
- `decision`
- `baseline_len`
- `candidate_len`

## MiniAdversarialOrchestrator

Before a mutation is submitted as a DGM `ChangeProposal`, V11.1 runs a small deterministic attack loop and stores `preproposal_adversarial` in the prompt metadata and audit record.

This defines the integration point for PyRIT, Giskard or a dedicated red-team service.
