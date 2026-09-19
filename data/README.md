# Data provenance and responsible use

This directory documents the data behind `jev_counterspeech.data`. The short
version: **everything shipped in this repository is synthetic, was written for
this project, and is released under CC0-1.0.** It contains no real slurs and no
real named person or group.

## What is shipped

`jev_counterspeech/data.py` generates a deterministic corpus of synthetic posts
with `synthetic_examples(seed=7, n=120)`. Every generated `Example` carries:

- `source="synthetic"`,
- `license="CC0-1.0"`,
- text built from templates written here, using only the bracketed placeholder
  `[SLUR]` and invented community names (for example "the Northland community",
  "the Riverfolk", "Group A", "the coastal diaspora").

The corpus spans all six `CATEGORIES` and adds a distinct individual-targeted
harassment class (hateful, not aimed at a protected group) so the drafting gate
has non-group cases it must refuse. Roughly 13 low-confidence examples sit in a
`p_hateful` band of `0.42-0.62` for calibration testing. Output is fully
determined by `(seed, n)`: it uses `random.Random(seed)` only, and performs no
network or filesystem access.

## Why no third-party dataset text is redistributed

Two concerns motivate shipping synthetic-only:

1. **Licensing.** Popular hate-speech corpora are released under their own
   terms, which frequently do not permit free redistribution of the underlying
   post text, and often forbid commercial use or require separate agreements.
   Republishing their rows here would relicense text we do not own.
2. **Republishing toxic content.** Faithfully redistributing slurs and targeted
   harassment amplifies exactly the material this project is meant to counter,
   and it can re-victimize the people those posts target.

Datasets a user may choose to opt into **locally, under their own licenses**,
include:

- **CONAN** — *CONAN: COunter NArratives through Nichesourcing, a Multilingual
  Dataset of Responses to Fight Online Hate Speech* (Fanton et al., ACL 2019,
  anthology **P19-1271**).
- **HateXplain** — *HateXplain: A Benchmark Dataset for Explainable Hate Speech
  Detection* (Mathew et al., AAAI 2021).

This repository intentionally ships **synthetic-only** and does not vendor,
download, or relicense either dataset. If you use them, obtain them from their
official sources and comply with their terms.

## Opting into a local sample

`PUBLIC_SAMPLES` is the extension point. It is an empty tuple by default:

```python
from jev_counterspeech.data import PUBLIC_SAMPLES, load_examples

# A user-supplied local sample replaces the empty tuple with their own Examples.
examples = load_examples(seed=7, include_public=True)
```

Any sample placed there is **your responsibility**: it must be clearly
attributed to its source, used within its license, and sanitized as needed for
your setting. Do not commit third-party toxic text to this public MIT/CC0 demo.

## Responsible use

This corpus is for offline evaluation, calibration, and tests of a
human-in-the-loop counterspeech assistant. It is not a benchmark for
surveillance or for training models to generate abuse, and it must not be used
to identify or profile real people or groups. All labels and probabilities are
synthetic ground truth; real deployment data will differ. Keep a human in the
loop, and never post anything automatically.
