# M53b Canonical Validation Report

> Generated on 2026-03-22 from the canonical exported-data runner: `python -m chronicler.validate`.
>
> `M53a` remains the frozen depth-tuning baseline. This report captures the final passing `M53b` outcome on `feat/m53-depth-tuning`.

## Run Profiles

- **Determinism smoke (`agents=off`)**
  - Batch: `output/m53/canonical/determinism_off/batch_42`
  - Profile: duplicate-seed smoke, 100 turns, `PYTHONHASHSEED=0`
- **Determinism smoke (`agents=hybrid`)**
  - Batch: `output/m53/canonical/determinism_hybrid/batch_42`
  - Profile: duplicate-seed smoke, 100 turns, `PYTHONHASHSEED=0`
- **Passing full gate**
  - Batch: `output/m53/codex_m53_secession_threshold25_full/batch_1`
  - Seeds: `1-200` (200 seeds)
  - Turns: `500`
  - Tuning: `tuning/codex_m53_secession_threshold25.yaml`
  - Inputs: exported bundles, `agent_events.arrow`, validation sidecars, `validation_summary.json`
  - Persisted report: `output/m53/codex_m53_secession_threshold25_full/batch_1/validate_report.json`

## Winning Profile

```yaml
politics:
  secession_stability_threshold: 25
  secession_surveillance_threshold: 12
  twilight_decline_turns: 40
  twilight_absorption_decline_turns: 120
  twilight_pop_drain: 1
  twilight_culture_drain: 1
action:
  war_decisive_ratio: 1.45
multiplier:
  aggression_bias: 0.95
```

## Determinism

| Profile | Result | Notes |
|---------|--------|-------|
| `agents=off` duplicate-seed smoke | **PASS** | `1` duplicate-seed pair checked, bundles match after metadata scrubbing |
| `agents=hybrid` duplicate-seed smoke | **PASS** | `1` duplicate-seed pair checked, bundles match after metadata scrubbing |
| Full gate validate report | **SKIP** | `1-200` batch contains no duplicate-seed pairs, so determinism is informational only on this run |

The dedicated exported-data determinism checks remain green. The full gate batch is judged on the blocking behavioral oracles.

## Full Gate Result (200 Seeds, 500 Turns)

| Oracle | Result | Key Metric |
|--------|--------|------------|
| 1. Community | **PASS** | `200/200` qualifying seeds vs required `150/200` |
| 2. Needs Diversity | **PASS** | `199/200` expected-sign seeds, `822` matched pairs, median effect `1.0063` |
| 3. Era Inflection | **PASS** | `200/200` inflection seeds, `0` silent-collapse seeds |
| 4. Cohort Distinctiveness | **PASS** | `200/200` expected-direction seeds, median effect `1.5021` |
| 5. Artifact Lifecycle | **PASS** | creation `1.8723/civ/100t`, diversity OK, loss/destruction `0.2705` |
| 6. Six Arcs | **PASS** | `6/6` families, `199` seeds with `3+` types, no dominance violation |
| Regression Summary | **PASS** | satisfaction `0.4577 +/- 0.1131`, migration `0.06465`, rebellion `0.06281`, Gini-in-range `0.9554`, occupation mix OK |

## Notes

- The 2026-03-21 canonical failure was real and is preserved in git history; this report supersedes it with the final 2026-03-22 rerun on the current branch state.
- The fixes that mattered were structural parity and lifecycle corrections, not weaker gates: hybrid passive stability recovery now survives agent mode, stale wars against dead civs are pruned, assimilation fallback completes in hybrid mode, and artifact / arc accounting edge cases were corrected without loosening assertions.
- Artifact results are comfortably in range on the final run: `7489` total artifacts, `2026` lost-or-destroyed artifacts, `81` Mule artifacts.

## Final Outcome

`M53a` is complete and frozen, and `M53b` now **passes** on the canonical runner.

That means:

- the official validator path exists and works
- the official M53 gates have been executed on exported data
- all blocking M53 oracles pass on the final canonical rerun
- `M53` is concluded and **does** unlock the scale track
- `M54a` and the rest of the scale track may proceed from this baseline
