# Ninth pass: feedback, verification, and generalization

This pass adds a controlled improvement loop without retraining the model. Submit a corrected result and reason; it remains `pending` until explicitly approved. Approved feedback is advisory context for future investigations and can be exported as evaluator-compatible regression cases.

```bash
feedback submit INC-001 --original original.json --corrected corrected.json --reason "Receipt was not posted"
feedback list --status pending
feedback approve 1
feedback export-regressions reports/feedback-regressions.json
evaluate --case-file reports/feedback-regressions.json
```

The verifier remains authoritative: invalid citations are removed, contradictions are escalated, and all adjustments are recorded in the trajectory alongside elapsed time, model, tokens, outcome, and steps.
