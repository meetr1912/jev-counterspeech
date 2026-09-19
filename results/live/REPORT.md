# Jev Counterspeech — Calibration Report

Mode: **live** · model: **—** · examples: **10** · seed: **7**

Generated: **2026-09-19T02:14:48+00:00**

## Headline calibration (hateful / noul)

| Metric | Jev | Always-0.5 |
| --- | ---: | ---: |
| Brier | 0.2401 | 0.2500 |
| Log loss | 0.6462 | 0.6931 |
| ECE | 0.3540 | 0.1000 |

Events scored: **10** · labels 0: **6** · 1: **4**.

## Per-question calibration

| question | count | Brier | ECE | Log loss | mean predicted | base rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hateful | 10 | 0.2401 | 0.3540 | 0.6462 | 0.578 | 0.400 |
| targets_protected_group | 10 | 0.3131 | 0.4130 | 0.8705 | 0.639 | 0.300 |
| has_slur | 10 | 0.1594 | 0.1860 | 0.4861 | 0.378 | 0.400 |

## Categorical calibration (choice questions)

| question | count | multiclass Brier | cross-entropy | accuracy |
| --- | ---: | ---: | ---: | ---: |
| category | 10 | 0.1920 | 0.6903 | 0.800 |
| handling | 10 | 0.7682 | 9.8606 | 0.100 |

## Severity

- Severity MAE: **0.3510** (scale 1–5)
- Severity Brier (normalized /5): **0.0125**

## Reliability table (hateful)

| bin | mean predicted | empirical | count | gap |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.010 | 0.000 | 1 | +0.010 |
| 1 | 0.120 | 0.000 | 1 | +0.120 |
| 2 | 0.280 | 1.000 | 1 | -0.720 |
| 4 | 0.410 | 0.000 | 1 | +0.410 |
| 6 | 0.680 | 0.000 | 1 | +0.680 |
| 7 | 0.700 | 0.000 | 1 | +0.700 |
| 8 | 0.870 | 0.500 | 2 | +0.370 |
| 9 | 0.920 | 1.000 | 2 | -0.080 |

## ASCII calibration curve

```
Calibration curve (predicted p -> empirical rate; '#'=empirical, 'o'=perfect)
  predicted   empirical   count   curve
      0.010       0.000       1   o---------------------------------------
      0.120       0.000       1   #---------------------------------------
      0.280       1.000       1   ---------------------------------------#
      0.410       0.000       1   #---------------------------------------
      0.680       0.000       1   #---------------------------------------
      0.700       0.000       1   #---------------------------------------
      0.870       0.500       2   --------------------#-------------------
      0.920       1.000       2   ---------------------------------------#
```

> **Responsible use:** Calibration is measured on labeled examples. Brier/ECE describe how well Jev's stated uncertainty matches observed outcomes; they are not an engagement or popularity metric and must not be optimized as one. Every action remains behind a human-review gate.

## Pipeline & gate

| action | count |
| --- | ---: |
| draft | 0 |
| human_review | 5 |
| ignore | 2 |
| report | 3 |
| refused (not drafted) | 10 |
| drafted_items | 0 |

Total reviewed items: **10** · gate drafts: **0** · refused: **10** · drafted: **0**.

## Sample reviewed items

| id | category | handling | gate action | #candidates | best candidate |
| --- | --- | --- | --- | ---: | --- |
| synthetic-0000 | slur | report | human_review | 0 |  |
| synthetic-0001 | none | ignore | ignore | 0 |  |
| synthetic-0002 | othering | report | human_review | 0 |  |
| synthetic-0003 | dehumanization | report | report | 0 |  |
| synthetic-0004 | slur | report | report | 0 |  |
| synthetic-0005 | othering | ignore | human_review | 0 |  |
| synthetic-0006 | othering | report | human_review | 0 |  |
| synthetic-0007 | slur | report | report | 0 |  |
| synthetic-0008 | othering | report | human_review | 0 |  |
| synthetic-0009 | none | ignore | ignore | 0 |  |

## Responsible-use guarantees

- Nothing is posted to any network; generated replies only ever land in a local outbox.
- A human reviews every draft before anything is sent; the gate can narrow review but never bypass it.
- The live judge sees only the post text and an opaque id; labels are used solely for offline measurement.
- High-stakes categories are never auto-drafted.
- Brier/ECE are reported with the always-0.5 baseline so miscalibration is visible, not hidden.
