# LRSI v10.1 Threshold Register

This document makes explicit that the current thresholds are **normative prototype assumptions**, not calibrated production guarantees.

## Current status

The project contains many threshold constants in modules such as `config.py`, `gate.py`, `deception_surface.py`, `synthetic_sincerity.py`, `pareto_admissibility.py`, `sham_resonance.py`, and `carrier_erosion.py`.

V10.1 does **not** claim empirical calibration. It adds a register so that future versions can attach evidence to each threshold rather than allowing constants to become invisible doctrine.

## Required evidence for production calibration

For each threshold, a future calibration record should include:

- threshold name and module
- current value
- protected invariant
- expected false-positive and false-negative cost
- dataset or scenario set used for calibration
- adversarial examples tested
- reviewer signature or approval record
- rollback plan if the threshold is changed

## Initial high-priority thresholds

| Threshold | Current role | Calibration status |
|---|---|---|
| `MAX_DRIFT` | Blocks excessive behavioral drift | Prototype / uncalibrated |
| `DREL_BLOCKER_THRESHOLD` | Blocks high deception-surface risk | Prototype / uncalibrated |
| `A3_SYNTH_SINCERITY_BLOCK` | Blocks synthetic-sincerity risk | Prototype / uncalibrated |
| `SHAM_RESONANCE_BLOCK` | Blocks false resonance classification | Prototype / uncalibrated |
| `EROSION_BLOCK` | Blocks carrier/substitution erosion | Prototype / uncalibrated |

## v10.1 rule

A threshold change remains a governance-layer change unless explicitly proven otherwise. It must therefore enter the DGM contract pipeline rather than bypassing review.
