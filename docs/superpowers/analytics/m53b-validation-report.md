# M53b Canonical Validation Report

> Generated on 2026-03-21 from the canonical exported-data runner: `python -m chronicler.validate`.
>
> M53a tuning is complete and frozen. This report captures the official M53b outcome.

## Run Profiles

- **Determinism smoke (`agents=off`)**
  - Batch: `output/m53/canonical/determinism_off/batch_42`
  - Profile: duplicate-seed smoke, 100 turns, `PYTHONHASHSEED=0`
- **Determinism smoke (`agents=hybrid`)**
  - Batch: `output/m53/canonical/determinism_hybrid/batch_42`
  - Profile: duplicate-seed smoke, 100 turns, `PYTHONHASHSEED=0`
- **Oracle subset**
  - Batch: `output/m53/canonical/oracle_subset/batch_42`
  - Seeds: `42-61` (20 seeds)
  - Turns: `200`
  - Inputs: exported bundles, `agent_events.arrow`, raw validation sidecars
- **Full gate**
  - Batch: `output/m53/canonical/full_gate/batch_1`
  - Seeds: `1-200` (200 seeds)
  - Turns: `500`
  - Inputs: exported bundles, `agent_events.arrow`, validation sidecars, `validation_summary.json`

## Determinism

| Profile | Result | Notes |
|---------|--------|-------|
| `agents=off` | **PASS** | `1` duplicate-seed pair checked, bundles match after metadata scrubbing |
| `agents=hybrid` | **PASS** | `1` duplicate-seed pair checked, bundles match after metadata scrubbing |

Determinism is no longer the blocker. The remaining failures are behavioral and structural.

## Oracle Subset Result (20 Seeds, 200 Turns)

| Oracle | Result | Key Metric |
|--------|--------|------------|
| 1. Community | **FAIL** | `12/20` qualifying seeds vs required `15/20` |
| 2. Needs Diversity | **FAIL** | `6/20` expected-sign seeds, `36` matched pairs, median effect `0.0` |
| 3. Era Inflection | **FAIL** | `20/20` inflection seeds, but `6` silent-collapse seeds |
| 4. Cohort Distinctiveness | **FAIL** | `7/12` analyzed seeds with expected direction, median effect `0.2394` |
| 5. Artifact Lifecycle | **PARTIAL** | creation `0.975/civ/100t`, diversity fail, loss/destruction `0.2115` OK |
| 6. Six Arcs | **FAIL** | `3/6` arc families; `riches_to_rags` dominates at `63.4%` |
| Regression Summary | **FAIL** | satisfaction `0.3366 +/- 0.08`, migration `0.3633`, rebellion `0.0390`, Gini-in-range `0.0207`, occupation mix fail |

### Notes

- Community formation is real but too sparse to meet the M53 threshold.
- Needs-diversity pairing now runs on canonical exported data, but the current cohort matching still produces weak or null effects.
- Era detection finds plenty of inflection points, yet the silent-collapse check fails often enough to keep the oracle red.
- Artifact creation is close to the floor, but the type mix is too narrow and only the loss/destruction subcheck passes.
- Arc coverage is incomplete at the 20-seed subset and is heavily skewed toward `riches_to_rags`.

## Full Gate Result (200 Seeds, 500 Turns)

| Oracle | Result | Key Metric |
|--------|--------|------------|
| 1. Community | **FAIL** | `13/200` qualifying seeds vs required `150/200` |
| 2. Needs Diversity | **FAIL** | `10/200` expected-sign seeds, `59` matched pairs, median effect `0.0` |
| 3. Era Inflection | **FAIL** | `200/200` inflection seeds, but `36` silent-collapse seeds |
| 4. Cohort Distinctiveness | **FAIL** | `4/13` analyzed seeds with expected direction, median effect `0.0` |
| 5. Artifact Lifecycle | **FAIL** | creation `0.6248/civ/100t`, diversity fail, loss/destruction `0.3994` fail |
| 6. Six Arcs | **FAIL** | `6/6` arc families, but `stable` dominates at `74.1%` and only `34` seeds show `3+` types |
| Regression Summary | **FAIL** | satisfaction `0.3964 +/- 0.0256`, migration `0.3504`, rebellion `0.0463`, Gini-in-range `0.0014`, occupation mix fail |

### Notes

- The full gate confirms that the subset failures were not just small-sample noise.
- Community emergence remains far below threshold even at the full sample size.
- Artifact outcomes worsen over the longer horizon: creation falls below range and loss/destruction rises above range.
- Arc coverage broadens to all six families, but the distribution is still structurally dominated by `stable`.
- Regression remains red, especially on migration rate, Gini range, and occupation balance.

## Final Outcome

`M53a` is complete and frozen, but `M53b` **fails** on the canonical runner.

That means:

- the official validator path now exists and works
- the official M53 gates have been executed
- `M53` is **concluded**, but it did **not** pass the scale-unlock gate
- `M54a` and the rest of the scale track remain blocked unless a follow-on retune / redesign effort revisits these failures

## Follow-On Work

If the project chooses to revisit this area later, the next work should be a **new post-M53 effort**, not more M53 bookkeeping. Highest-signal failure clusters from the canonical run:

1. community formation and cohort distinctiveness
2. needs-diversity matching / measurable downstream behavior
3. arc distribution skew
4. artifact diversity and lifecycle balance
5. regression drift in migration, inequality, and occupation structure

Implementation details for the canonical runner and artifact contract remain documented in `docs/superpowers/plans/2026-03-21-m53b-validation-pipeline.md`, but M53 itself is no longer waiting on more paperwork.
