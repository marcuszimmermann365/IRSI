# Signed Evidence Bundle Review

V12.0 binds human review to the case file used for the decision.

## Evidence bundle fields

Evidence bundles now include:

```text
evidence_bundle_hash
evidence_signature
evidence_signature_algorithm
evidence_signer_id
evidence_public_key_b64 optional
```

## Review approvals

`ReviewApproval` contains `evidence_case_id`, `evidence_bundle_hash`, `review_approval_hash`, and signature metadata.  `TwoFactorReviewGate.validate(..., evidence_bundle=bundle)` checks:

1. two cryptographically valid approvals;
2. two distinct reviewers;
3. required roles;
4. signed evidence bundle;
5. matching case id and evidence hash;
6. rejection of simulation-only approvals on evidence-bound review paths.

Use `TwoFactorReviewGate.signed_approval(...)` or `sign_review_approval(...)` to create approvals bound to the canonical review payload.

## Signing modes

Development:

```bash
AUDIT_SIGNING_MODE=hmac AUDIT_HMAC_KEY=dev-secret
```

Production-near:

```bash
AUDIT_SIGNING_MODE=ed25519 AUDIT_ED25519_PRIVATE_KEY=<base64-key>
```
