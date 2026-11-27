# Quality evidence — <QAS-n, attribute> (M3 §2)

| Item | Value |
|---|---|
| Scenario (source · stimulus · artifact · environment · response · response measure) | copy from M2 §1.4 |
| ASR / tactics exercised | e.g. ASR-1 · T7, T8, T11, T13 |
| Result file(s) | `evidence/<qas>/results/<file>.json` |
| Environment | machine, CPUs/RAM, OS, Docker version, Runner Worker replicas, relevant `.env` values, git commit |

## Method
What was injected or measured, how often, for how long, with which command. Why this method fits the
response measure.

## Results
Table of the numbers (rates, percentiles, counts, times) next to the target.

| Measure | Target | Measured | Met? |
|---|---|---|---|
| | | | |

## Interpretation
Why the architecture produced this result (name the components and tactics). If NOT MET: the cause, whether
it is architectural or environmental, and the change or ADR it leads to. Limits of the experiment (sample
size, single machine, mock LLM, …). Do not generalise beyond what was measured (C-16).
