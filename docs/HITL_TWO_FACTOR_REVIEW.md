# Human-in-the-Loop Two-Factor Review

V11.1 adds `TwoFactorReviewGate` and `ReviewApproval`.

For practical validation, soft RED approvals can require two distinct signed roles, for example:

- `security_auditor`
- `system_operator`

Hard RED, immutable RED and external-integrity RED remain non-overridable toward acceptance.

Simulation helpers exist for tests only. Production deployments must bind reviewer identity to real authentication and signature infrastructure.
