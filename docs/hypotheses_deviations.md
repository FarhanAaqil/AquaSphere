# Deviations from the frozen hypotheses

`docs/hypotheses.yaml` was frozen under the tag `hypotheses-v1-2026-10-29`, before any tuned
model touched the 2024-2025 test period. Any change to a hypothesis, threshold, metric, protocol
or confirmatory family after that tag is a deviation. Record each one here, with the date, what
changed, why, and whether the test period had already been read (see
`docs/results/test_access.log`).

| Date | Hypothesis | Change | Reason | Test period read before the change? |
|---|---|---|---|---|
| 2026-10-30 | H1a-H4 (family) | Clarification, no threshold changed: the p-value fed to the Holm correction is the share of 2000 float-block bootstrap replicates in which the hypothesis's own falsification criterion holds (H1a: reduction below 15%; H1b: skill ratio below 0.85; H2: either reduction below its threshold; H3: overall coverage outside 87-93%; H4: gap below 20%). A hypothesis is supported when its Holm-adjusted p is below 0.05 and its point estimate meets the threshold. | The frozen file fixes alpha and the Holm family but not how each p-value is computed. | No (`docs/results/test_access.log` did not exist when this was written) |
| 2026-10-30 | H2 | The pre-trained arm is the masked + temporal pretext and the comparison is Tier C vs Tier B from scratch (same architecture), using the encoders pre-trained on 2015-2022 in Phase 4. | H2 names "pre-trained encoders" without fixing the pretext; the Phase 4 validation run chose it before the test period was read. | No |
| 2026-10-30 | H4 | The random split pools the training and test partitions and holds out a random 20% of profiles; the blocked split trains on 2015-2022 and scores 2024-2025. | H4 says "rerun in the final evaluation so the test period decides" without naming the pool. | No |

Writing this table before the run is the point: none of these choices could be steered by test results.
