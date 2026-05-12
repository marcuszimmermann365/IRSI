```
# LRSI – AI Alignment Security Framework


```
```
**v13.1.0** | Production-near | Security Hardened

LRSI is an **event-sourced security framework** designed for AI systems that can modify themselves. It ensures that dangerous or unwanted self-modifications are **detected, blocked, and fully auditable**.

> **Core Question:** How does a system recognize that it **must not continue** — and how can it prove it?

---

## 🚀 Quickstart

```bash
git clone https://github.com/marcuszimmermann365/IRSI.git
cd IRSI
pip install -e ".[dev]"
python runner.py --iterations 3

```
This generates the main audit artifacts:  
* run_log.json  
* run_log.json.events.jsonl ← **canonical audit stream**  
  
## ✨ Key Features (v13.1)  
* **Hard kill-switches** for dangerous self-modifications  
* **11 central security invariants** enforced programmatically  
* **Event-sourced audit trail** with hash-chaining and replay  
* **14 Property-Based Security Tests** using Hypothesis  
* **Unified security exception hierarchy** (LRSISecurityError)  
* **Structured security logging**  
* **Signed evidence bundles** (Ed25519 + HMAC)  
* **WORM-compatible audit storage**  
  
## 🛡️ Security Model  
LRSI follows a **fail-closed** security model:  
* A RED result in PreProposalAdversarialPhase immediately stops the mutation (terminal=True).  
* Blocked mutations cannot pass DGM pre-check or the final gate.  
* All critical decisions are recorded in an immutable, hash-chained event stream.  
See:  
* ++INVARIANTS.md++  
* ++SECURITY_MODEL.md++  
* ++SECURITY_CHANGES_v13.0.md++  
  
## 📦 Installation  
```
pip install -e .

```
For development:  
```
pip install -e ".[dev]"

```
  
## 🧪 Testing  
```
# Run all tests
python -m pytest -q

# Run only property-based tests
python -m pytest tests/test_v122_property_based_security.py -q

# Check phase-event coverage
python scripts/check_phase_event_coverage.py --run-sample --iterations 3

```
  
## 📚 Documentation  

| Document          | Description                               |
| ----------------- | ----------------------------------------- |
| ARCHITECTURE.md   | System architecture & pipeline            |
| SECURITY_MODEL.md | Security concept & fail-closed principles |
| INVARIANTS.md     | All 11 security invariants                |
| OPERATIONS.md     | How to run, log, and operate the system   |
| CHANGELOG.md      | Full release history                      |
| CONTRIBUTING.md   | How to contribute                         |
  
## ⚠️ Important Limitations  
LRSI is a **research and security framework**, **not** a complete AI safety solution.  
* It is **not** certified for production use.  
* It does **not** secure model weights or solve training-time alignment.  
* Real production deployment requires additional infrastructure (key management, WORM storage, reviewer identity).  
  
## 📄 License  
Apache License 2.0 — see ++LICENSE++.  
  
**LRSI – Making dangerous self-modification visible, blockable, and auditable**  
