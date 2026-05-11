# Shadow Calibration Guide

Set:

```bash
SHADOW_CALIBRATION_PATH=runtime/shadow_decisions.jsonl
```

The runtime writes shadow observations containing system decisions, human decisions and diagnostics.

Use `ThresholdCalibrationAnalyzer` to compute:

- false-positive count/rate
- false-negative count/rate
- Wilson 95% confidence intervals

Use `ThresholdBacktester` against historical audit records before changing `runtime_config/threshold_registry.json`.

V11.1 provides the mechanism, not a calibrated dataset.
