# Sample reports

This directory is exempted from `.gitignore` so a couple of real evaluation
reports can be committed as evidence for the Measured Improvement and
Reproducibility deliverables.

Before submitting, run the evaluation locally and copy in at least the final
report, and ideally one earlier report it can be compared against:

```bash
evaluate --runs 1
cp reports/evaluation_*.json reports/samples/
```

If you have an earlier report from a prior pass, copy it in too so
`--compare-to` output (and the numbers in the README's Improvement
Changelog) can be checked against real files rather than taken on faith.
