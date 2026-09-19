# Jev Counterspeech — Calibration Report

Mode: **offline** · model: **—** · examples: **120** · seed: **7**

Stub: **calibrated**

Generated: **2026-09-19T02:09:07+00:00**

## Headline calibration (hateful / noul)

| Metric | Jev | Always-0.5 |
| --- | ---: | ---: |
| Brier | 0.0909 | 0.2500 |
| Log loss | 0.3136 | 0.6931 |
| ECE | 0.0748 | 0.0833 |

Events scored: **120** · labels 0: **50** · 1: **70**.

## Per-question calibration

| question | count | Brier | ECE | Log loss | mean predicted | base rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hateful | 120 | 0.0909 | 0.0748 | 0.3136 | 0.611 | 0.583 |
| targets_protected_group | 120 | 0.1100 | 0.0842 | 0.3543 | 0.486 | 0.467 |
| has_slur | 120 | 0.0495 | 0.0707 | 0.1819 | 0.258 | 0.283 |

## Categorical calibration (choice questions)

| question | count | multiclass Brier | cross-entropy | accuracy |
| --- | ---: | ---: | ---: | ---: |
| category | 120 | 0.0229 | 0.1641 | 1.000 |
| handling | 120 | 0.1081 | 0.3824 | 1.000 |

## Severity

- Severity MAE: **0.3610** (scale 1–5)
- Severity Brier (normalized /5): **0.0075**

## Reliability table (hateful)

| bin | mean predicted | empirical | count | gap |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.057 | 0.000 | 18 | +0.057 |
| 1 | 0.155 | 0.000 | 16 | +0.155 |
| 4 | 0.455 | 0.000 | 5 | +0.455 |
| 5 | 0.566 | 0.667 | 6 | -0.100 |
| 6 | 0.625 | 1.000 | 3 | -0.375 |
| 7 | 0.757 | 0.800 | 15 | -0.043 |
| 8 | 0.856 | 0.871 | 31 | -0.015 |
| 9 | 0.937 | 0.923 | 26 | +0.013 |

## ASCII calibration curve

```
Calibration curve (predicted p -> empirical rate; '#'=empirical, 'o'=perfect)
  predicted   empirical   count   curve
      0.057       0.000      18   #---------------------------------------
      0.155       0.000      16   #---------------------------------------
      0.455       0.000       5   #---------------------------------------
      0.566       0.667       6   --------------------------#-------------
      0.625       1.000       3   ---------------------------------------#
      0.757       0.800      15   -------------------------------#--------
      0.856       0.871      31   ----------------------------------#-----
      0.937       0.923      26   ------------------------------------#---
```

> **Responsible use:** Calibration is measured on labeled examples. Brier/ECE describe how well Jev's stated uncertainty matches observed outcomes; they are not an engagement or popularity metric and must not be optimized as one. Every action remains behind a human-review gate.

## Pipeline & gate

| action | count |
| --- | ---: |
| draft | 28 |
| human_review | 65 |
| ignore | 19 |
| report | 8 |
| refused (not drafted) | 92 |
| drafted_items | 28 |

Total reviewed items: **120** · gate drafts: **28** · refused: **92** · drafted: **28**.

## Sample reviewed items

| id | category | handling | gate action | #candidates | best candidate |
| --- | --- | --- | --- | ---: | --- |
| synthetic-0000 | slur | reply | human_review | 0 |  |
| synthetic-0001 | none | ignore | human_review | 0 |  |
| synthetic-0002 | stereotype | reply | human_review | 0 |  |
| synthetic-0003 | dehumanization | human_review | human_review | 0 |  |
| synthetic-0004 | slur | reply | human_review | 0 |  |
| synthetic-0005 | othering | reply | human_review | 0 |  |
| synthetic-0006 | othering | reply | human_review | 0 |  |
| synthetic-0007 | slur | human_review | human_review | 0 |  |
| synthetic-0008 | none | ignore | human_review | 0 |  |
| synthetic-0009 | none | human_review | human_review | 0 |  |

## Responsible-use guarantees

- Nothing is posted to any network; generated replies only ever land in a local outbox.
- A human reviews every draft before anything is sent; the gate can narrow review but never bypass it.
- The live judge sees only the post text and an opaque id; labels are used solely for offline measurement.
- High-stakes categories are never auto-drafted.
- Brier/ECE are reported with the always-0.5 baseline so miscalibration is visible, not hidden.
