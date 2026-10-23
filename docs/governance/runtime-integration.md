# Phase 8 governance in the live runtime

This document records how the detached Phase 8 kernels — M63a institutions
(`institutions.py`, G01), M65a elite metrics (`elite_metrics.py`, G02), M66a
legitimacy and political capital (`governance_capital.py`, G03) and M66b ruler
ambitions (`ruler_ambitions.py`, G04) — run inside the real turn loop
(`main.py` → `simulation.run_turn_result`). It also covers the M65b Political
Stress Index, the M67 regime classifiers, and the M63b action-weight bucket that
were added on top. Roadmap references are to
`docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md`.

The detached harness (`governance_kernel_harness.py`), capture, measurement and
sequence lanes are unchanged. They keep their synthetic-fixture-only scope; the
runtime composes the four kernels directly through
`src/chronicler/governance_runtime.py` and does not call `run_kernel_frame`.

## Switch and defaults

| Surface | Value |
| --- | --- |
| CLI | `--governance` / `--no-governance` (`argparse.BooleanOptionalAction`) |
| World field | `WorldState.governance: GovernanceSettings \| None` (presence = on) |
| Default | Off for newly generated worlds; a saved world keeps its own setting |
| Gate runner | `scripts/m53b_run_validation.py --governance` forwards the flag to every run |

`None` governance fields (world, civilization and per-turn `CivSnapshot`) are
omitted from serialized output by a wrap serializer, so feature-off `state.json`,
bundles and snapshots are byte-identical to the pre-governance format, and saves
written before this work load unchanged. With the switch off, no governance code
runs: the Phase 2 and Phase 10 hooks, the action-weight hook and the
succession-risk hook are all guarded by `world.governance is not None`.

## Turn placement

The roadmap's "Execution Ownership & Turn Ordering" table is followed exactly:

| Step | Where | What |
| --- | --- | --- |
| Phase 2 | `apply_automatic_effects`, right after `apply_governing_costs` | `fund_institutions_phase2`: pay institutional enforcement from the treasury and record the M63a funding bookkeeping (`last_base_governing_cost`, `last_institution_enforcement_cost`, `last_institution_funding_ratio`) for turn N |
| Phase 5 | `ActionEngine.compute_weights`, after the faction modifier and before holy-war / raider bonuses | `governance_weight_modifiers`: the governance contributor bucket |
| Phase 7/10 | `succession.compute_crisis_probability` | `governance_crisis_multiplier` |
| Late Phase 10 | end of `phase_consequences`, after the Rust/Python politics pass, `tick_factions` and temple prestige | `tick_governance`: institutions, capital spending, elite metrics, ambitions, legitimacy and capital accrual, PSI, consequences, regime labels |

Everything `tick_governance` produces is effective N+1. The same turn's politics
pass has already run and is never revisited. Politics consumes governance only
through ordinary civilization state: stability, treasury and faction influence.
The Rust politics runtime and the Python oracle therefore see identical inputs,
and no FFI schema change was needed. The roadmap's optional politics-batch
extension fields (`psi`, `ruler_legitimacy`, ...) are unnecessary for v1.

## Per-turn transaction (late Phase 10, per living civ, by civ index)

1. **Accession check.** A new reign starts when `(leader.name, leader.reign_start)`
   differs from the stored ruler key. Reign IDs are `"{civ_idx}:{serial}"`, so
   they are unique and never reused.
2. **Institutions (G01) + capital (G03).** The Phase 2 record becomes an
   `EXTERNAL_AGGREGATE_RECORD` `FundingResult`. If there is no record for this
   turn (new or restored polity), "nothing paid" is synthesized: coverage 0, or
   1 with no demand. A record is never reused across turns.
   * Proposals: each faction above the 0.35 dominance threshold makes at most
     one attempt. It picks one aligned candidate from G01's canonical
     `proposal_candidates`, weighted by civ-state fit (e.g. CONSCRIPTION at war,
     TAX_CODE under fiscal stress, COMMONS_MANAGEMENT on depleted soil). It
     then rolls one proposal draw. Both draws come from stream
     `governance_institution`/1200.
   * Spending priority, a single G03 pool: forced repeals (opposition > 0.40)
     first, then enactments in enum order, then secession suppression. This
     matches the harness's probe-then-spend transaction. Each request is first
     probed for structural eligibility with `resolve_institutions`, and only
     eligible requests are priced. The complete ordered batch is then
     reconciled against `resolve_spending` from the opening state; any mismatch
     raises. Resolution order is `REPEAL_THEN_PROPOSE`, so a forced repeal can
     free a slot for a same-turn enactment. A denied enactment leaves no trace
     on the ledger.
   * Neglect: aggregate coverage < 1 erodes every institution by 0.08, and full
     coverage recovers 0.02 per turn. Below 0.05 legitimacy an institution
     collapses (G01 contract, unchanged).
3. **Elite metrics (G02).** With agents (hybrid, shadow, demographics-only),
   the post-tick `phase10` snapshot rows supply real wealth, occupation, skill
   and satisfaction. Active GreatPersons are overlaid, present-backed by
   `agent_id` when their agent is in the snapshot. Absent-backed GPs carry the
   civ's max wealth and mean satisfaction. With `--agents off`, active
   GreatPersons plus a deterministic cohort of "notable houses"
   (`population × 0.15 × (0.5 + economy/100)`, satisfaction spread around
   `stability/100`) stand in for rows. Kernel conventions: LOWER wealth
   percentile, FLOOR office rounding, AGENTS_FIRST ties.
4. **Ambitions (G04).** At accession, `start_reign` draws 2 objectives (3 for
   civs with ≥ 3 regions) from stream `governance_ambition`/1900. Weights are
   trait-aligned through `TRAIT_FACTION_MAP`: the aligned type 2.5, a secondary
   1.5, the rest 1.0. DIPLOMATIC_TRIUMPH is excluded, as the kernel requires. The
   targets are:
   * CONQUER_REGION: adjacent regions held by hostile or suspicious civs.
   * EXPAND_TERRITORY: adjacent unclaimed regions.
   * BUILD_MONUMENT: owned non-capital regions with no standing works and a
     valid build.
   * ESTABLISH_TRADE: neutral-or-better living civs without a route, by civ
     index.
   * RELIGIOUS_CONVERSION: owned regions where the civ faith share is < 0.4,
     needing ≥ 0.7.
   * PATRON_OF_ARTS: needs culture ≥ 50.
   New objectives are evaluated from the next turn ("defer_new_objectives").
   Each turn's evidence is the civ's own `infrastructure_completed` (region
   parsed from the description) and `cultural_work` events, numbered by a
   monotone per-civ cursor. Routine `invest_culture` does not count for
   patronage.
5. **Legitimacy and capital (G03).** The inputs are:
   * Dynasty prestige: cognomen bonuses of archived predecessors along an
     unbroken chain of `heir` successions, weighted 1/n, at most 5 deep.
   * Aligned-institution support.
   * Victories and defeats from the last 30 turns of the reign: won or lost war
     events, territory lost this turn, and PSI revolts, which count as a
     failed outcome (loss of control).
   * Ruler-faction alignment with the dominant faction (> 0.35).
   * Reign-long keyed ambition contributions (+0.10 / −0.05), never double
     counted as victories.
   At accession the kernel's reset applies (base + dynasty + institutions ±
   succession), and **half** the remaining capital carries over. Capital is
   quantized to 1e-9 and capped at 1.0, so the float saved to JSON round-trips
   exactly to the kernel's exact `Fraction`.
6. **PSI** (below), then **consequences**, then **regime labels**.

When a reign ends, it is archived with a cognomen bonus:
`0.05·completed + 0.02·min(victories, 5) − 0.03·failed`, plus 0.03 at
legitimacy ≥ 0.8, clamped to [0, 0.25]. Bonuses ≥ 0.1 are announced as a
cognomen ("the Conqueror", "the Builder", "the Pious", "the Magnificent",
"the Great", "the Wise").

## Consequences: what governance changes

| Channel | Mechanism |
| --- | --- |
| Treasury | Enforcement demand is paid in Phase 2. It is never pushed into debt: coverage is what the projected treasury can pay. WRITTEN_LAW refunds 20% of the base governing cost; TAX_CODE and TEMPLE_TITHE earn 0.5/region; all scaled by institution legitimacy |
| Stability | `4 × (legitimacy − 0.45)` plus per-institution effects (e.g. MARTIAL_LAW +1, REPUBLICAN_VIRTUE +0.5, CONSCRIPTION/HOLY_INQUISITION −0.5) plus a PSI crisis drain of 1 + min(1, PSI − threshold). Fractions accumulate in a persisted carry. Secession suppression adds +6. Hybrid routes this through the accumulator as `signal` (agent satisfaction shocks next tick); aggregate mode mutates directly |
| Faction power | Entrenchment: each institution adds 0.003 × legitimacy per turn to its aligned faction. There are institution drifts (MARTIAL_LAW −0.004 merchant, MERCHANT_COURTS +0.002 merchant, TEMPLE_TITHE +0.002 clergy), and a PSI crisis adds +0.01 military. The R1 reform-pressure guard applies: a faction above 0.70 for more than 30 turns loses 0.02 per turn. Mutated directly then `normalize_influence`, like `tick_factions` |
| Succession risk | `compute_crisis_probability` × (1.5 − legitimacy) × institution multipliers (MILITARY_ACCLAMATION 1.25, REPUBLICAN_VIRTUE 0.8, DIVINE_RIGHT 0.75) × 1.3 in a PSI crisis. The existing [0.05, 0.40] clamp still applies |
| Secession pressure | PSI crisis drains stability toward the secession threshold, which both Rust and the oracle read. Suppression: below threshold + 4 stability with ≥ 3 regions and outside the grace period, the ruler may spend 0.20 capital for +6 stability (5-turn cooldown) |
| Revolt and civil war | In a PSI crisis each turn has a revolt chance of `0.06 × min(2, PSI/threshold) ×` institution revolt multipliers (MARTIAL_LAW 0.5, FRONTIER_GARRISONS 0.8, ...), capped at 0.3 (stream `governance_revolt`/1300). A revolt costs −3 stability and −3 economy, counts as a failed outcome, and crashes the elite consumption index ×0.8. With ≥ 3 regions and legitimacy < 0.45 it can escalate to a civil war, with probability `0.35 × (1 − legitimacy)`, ×1.5 after a recent legitimacy crisis. A civil war triggers the existing succession crisis, crashes the consumption index ×0.5, and makes the eventual accession contested |
| Action weights | The governance bucket (below) |
| Ecology | COMMONS_MANAGEMENT nudges soil +0.003 × legitimacy per turn toward 0.8 in owned regions (per-region state only; never the global ecology config). Partial M64 |
| Elites | EDUCATION (+50%) and TAX_CODE (+25%) expand elite offices: the roadmap's position-expansion enrichment |

## M63b: the governance weight bucket and the 2.5x cap (REVIEW B-5)

Institution modifiers ship for all 16 types, e.g. PROPERTY_RIGHTS DEVELOP
1.2 / TRADE 1.1 / FUND_INSTABILITY 0.8 and CONSCRIPTION WAR 1.3 / DEVELOP 0.9.
Each enters as `1 + (m − 1) × institution_legitimacy`. Unfulfilled ambitions
add biases: CONQUER WAR 1.15, EXPAND 1.2, BUILD 1.2, TRADE 1.15 / DIPLOMACY
1.1, CONVERSION INVEST_CULTURE 1.1, PATRON INVEST_CULTURE 1.2. A PSI crisis
gives DEVELOP 1.1 / WAR 0.9, and legitimacy < 0.3 gives a diversionary WAR 1.1.

All of these multiply into **one contributor bucket per action, clamped to
[1/1.5, 1.5]**. That is `INSTITUTION_WEIGHT_CEILING` from decision D1,
inserted after the faction modifier and before the holy-war and raider
bonuses, as M63b specifies.

With governance on, the pre-existing contributors are also explicit buckets
(`action_engine._ContributorBuckets`, ceilings in `BUCKET_CEILINGS`):

| Bucket | Ceiling |
| --- | --- |
| trait | 2.0 |
| situational | 2.5 |
| tech focus | 1.5 |
| faction | 1.5 |

Each stage is measured as its per-action after/before ratio, and only ratios
above the ceiling are reduced. For example, the situational EXPAND stack can
reach ×6, and DIPLOMACY ×3 at low stability. The pipeline order is unchanged.
Suppression factors (the WAR damper, "no hostile neighbour" ×0.1) are not
floored.

Leader secondary trait, rival, grudge (its own `K_GRUDGE_CAP`) and tradition
factors, plus holy war, raider, aggression bias, war-weariness, peace dividend
and Mule (its existing 0.1 floor), remain unbucketed as before. The global cap
(`K_WEIGHT_CAP`, default 2.5× base) still clamps every action last, and it is
unchanged. `ActionEngine.last_buckets` exposes the factors for inspection.
With governance off the helper does no arithmetic, so the off-mode
distribution, which the dormancy and performance oracles pin, is
bit-identical.

## Government forms and the selectorate (M63 enrichments)

`classify_government` labels each polity from its standing institutions
(legitimacy ≥ 0.3), dominant faction and succession type. The labels, with
their winning-coalition share W/S (Bueno de Mesquita), are:

* autocracy 0.05
* chiefdom 0.10
* military regime 0.10
* monarchy 0.15
* theocracy 0.20
* bureaucratic monarchy 0.25
* constitutional state 0.40
* merchant republic 0.50

The effects are:

* Narrow coalitions (W/S < 0.15) buy loyalty with private goods: WAR ×1.1 and
  BUILD ×1.05.
* Broad coalitions (W/S ≥ 0.40) favour public goods: DEVELOP ×1.1 and TRADE
  ×1.1.
* Both biases sit inside the governance bucket.
* The medium band is the "institutional transition trap", with
  succession-crisis odds ×1.1.
* Changes of form after a 10-turn tenure emit `government_transition`
  events. This is the Acemoglu/Robinson institutional-evolution enrichment.

## M65b: Political Stress Index

Raw sub-indices follow the roadmap:

* `MMP = (1 / max(median_wealth/mean_wealth, 0.01)) × urbanization × youth(15-30)`
  from the civ's snapshot rows (urban = `settlement_id ≠ 0`). The `--agents off`
  proxy is `relative_wage = clamp(1.1 − 0.5·crowding + 0.3·(economy/100 − 0.5),
  0.2, 1)`, `urbanization = min(0.6, 0.3·crowding)` and youth 0.25, where
  crowding = population / effective capacity.
* `EMP` = G02's `frustrated_aspirants / elite_positions × consumption_index`.
* `SFD = (base + enforcement) / max(treasury, 1) × (1 + enforcement/treasury × (1 − mean institution legitimacy))`
  (decision D5; no institutions → neutral).

Each is divided by a reference scale (MMP 0.10, EMP 2.0, SFD 0.04; each about
the 75th–85th percentile of 6-seed hybrid calibration runs) and capped at 4.
Each is then EMA-smoothed (α = 0.2) and composed as

```
PSI = (0.5 + s_mmp) · (0.5 + s_emp) · (0.5 + s_sfd)      (exponents a = b = c = 1)
```

The 0.5 floor is the runtime's answer to risk R5, the multiplicative
calibration cliff. A missing sub-index halves PSI instead of zeroing it. One
saturated sub-index alone (4.5 · 0.5 · 0.5 = 1.125) cannot cross the crisis
threshold, and a crisis needs at least two elevated sub-indices. Crisis
hysteresis: enter above 2.6, leave below 1.7.

M65a calibration note: the roadmap's `ELITE_POSITIONS_DIVISOR = 100` targets
10⁴–10⁵ agents per civ. Chronicler civs hold 10¹–10³, so every civ sat at the
2-office floor and EMP saturated. The runtime uses 20 (5% offices against a
top-decile-plus-skilled qualifier pool), with ratchet up 0.01, down 0.03 and cap
1.5, so the index rises only when qualifier pressure exceeds about 4. Revolts
and civil wars crash it, giving the roadmap's "slow rise, fast crash" shape.

## M67 regime classifiers

`governance_stress.classify_institutional_regime` locks the conventions the
preregistration left open:

* **Window:** a trailing 100-turn window, clipped at the civ's governance start.
  Under 30 observed turns the label is `nascent`. "Per 100 turns" rates scale
  to the observed span.
* **Changes:** an institution change is any enactment, forced repeal or neglect
  collapse.
* **Tenure:** completed spells ending in the window, plus active spells
  censored at the current turn (a lower bound). Spells may begin before the
  window.
* **Mean active count:** the time-average over the window.
* **Labels**, mutually exclusive, in precedence order:
  * `highly_fluctuating`: mean tenure < 10 and ≥ 4 changes.
  * `complex_cycling`: ≥ 3 changes and ≥ 2 configurations.
  * `frozen_stable`: ≤ 1 change per 100 turns and mean active ≥ 1.
  * `inert`: ≤ 1 change per 100 turns and no standing institutions.
  * `transitional`: everything else.

`classify_cycle_phase` labels the secular cycle as crisis, depression (≤ 30
turns after a crisis), stagflation (PSI ≥ 0.75 × threshold and rising over 10
turns), recovery (≤ 100 turns after a crisis) or integrative.

## Events, narration, viewer, analytics

New event types: `institution_enacted`, `institution_repealed`,
`institution_enforcement_lapse`, `fiscal_crisis`, `ambition_declared`,
`ambition_fulfilled`, `ambition_failed`, `cognomen_awarded`,
`legitimacy_crisis`, `elite_overproduction`, `psi_crisis`, `psi_recovery`,
`revolt`, `civil_war`, `secession_suppressed`, `reform_pressure`,
`institutional_regime_shift` and `government_transition`. All of them have human-readable descriptions.

* **Event chains:** governance tags recorded in a 40-turn window feed event
  chains. For example, a recent `legitimacy_crisis` raises civil-war odds by
  ×1.5, and a recent `civil_war` makes the next accession contested.
* **Curator:** twelve causal patterns, e.g. `psi_crisis → revolt/secession/civil_war`
  and `fiscal_crisis → institution_repealed`.
* **Narrator:** the per-turn prompt gains an "Institutions, rulers and the
  strains of the age" block. It is absent when governance is off, so the
  off-mode prompt is unchanged.
* **Viewer bundle:** `CivSnapshot.governance` carries per-turn institutions,
  coverage, legitimacy and sources, capital, ambitions, elite counts, raw and
  normalized MMP/EMP/SFD, PSI, crisis flag, regime, cycle phase, government
  form and W/S, and the revolt, civil-war and suppression totals.
* **Analytics:** `governance_metrics.extract_governance_metrics(bundles)` is the
  M67 measurement-first extractor. `generate_report` adds a `governance` section
  only when the bundles carry governance stats. It reports institution
  count/tenure, regime reachability, legitimacy and capital distributions,
  elite counts, the MMP/EMP/SFD/PSI distributions, crisis share,
  predictiveness (an outcome 10–40 turns after onset), sub-index co-occurrence,
  120-turn recovery and ambition completion.

## Determinism and persistence

* All draws use `stable_hash_int(label, seed, turn, offset, civ_idx, ...)`.
  None use the action RNG or global `random`.
* Iteration follows civ index, faction enum order and institution enum order.
* State lives in `Civilization.governance` (`governance_state.CivGovernance`),
  including the fractional stability carry and the smoothed PSI sub-indices.
  A save/load round trip therefore continues bit-identically (tested).
* The Phase 2 → Phase 10 funding record is stamped with its turn and only
  consumed on that turn.
* Trade routes are read with their cache saved and restored, so the tick
  leaves no route-cache side effects.

## Verification

* `tests/test_governance_runtime.py` covers:
  * dormancy: a disabled world never serializes or runs governance, and
    disabled runs equal never-enabled runs;
  * old-save load and mid-run enable;
  * the 80-turn multi-turn epoch contract;
  * events in the timeline;
  * conflict validity;
  * same-seed determinism;
  * the save/load round trip;
  * Phase 2 funding record consumption and stale-record rejection;
  * neglect collapse;
  * a capital-funded enactment, including no global RNG use;
  * suppression and its cooldown;
  * contested accession archiving;
  * the bucket clamp and global-cap retention;
  * the crisis multiplier;
  * snapshot and bundle fields with dormant omission;
  * the CLI flag through `execute_run`;
  * PSI composition, hysteresis and formulas;
  * regime labels and window exclusion;
  * cycle phases;
  * M63b buckets: inert when off, ceilings respected when on;
  * the eight government forms;
  * selectorate weight and crisis effects;
  * a native hybrid run that uses agent rows and is deterministic.
* The existing dormancy, performance-equivalence and harness suites pass
  unchanged with governance off.

Gate and outcome results are recorded in the final section below.

## Results (Linux, Python 3.13, native extension built from this tree)

**Subset gate** (`m53b_run_validation.py --profile subset`: 20 seeds × 200
turns, hybrid), compared with `validation_compare` against the 837a44f
baseline report:

| Run | Gate | Required failures | Comparator | Oracle changes vs baseline |
| --- | --- | --- | --- | --- |
| governance off, seeds 42–61 | PASS | none | no regression | none. Results are identical and all 12 regression metric deltas are 0.0 |
| governance on, seeds 42–61 | PASS | none | no regression | `arcs` PASS → FAIL (informational for subset). Six arc families became four, losing the two baseline singletons (cinderella 1, man_in_a_hole 1 of 118 civs); per-seed arc diversity rose 18 → 20 seeds with ≥ 3 types. Satisfaction mean 0.4085 → 0.3998 |
| governance on vs off, seeds 62–81 | PASS / PASS | none | no regression | none. arcs PASS with 6 families in both (cinderella 3 vs 1, rags_to_riches 3 vs 1); satisfaction mean 0.4089 → 0.4090 |

The pre-existing `regression: FAIL (terminal_population_extinction)` is
unchanged in every run. That is the separately tracked world-extinction bug.

Outcomes, governance on vs off, over the same 20 hybrid seeds (42–61):

* Stability: mean 20.1 vs 20.8 (civs with population ≥ 20: 23.7 vs 24.4).
* Event counts: secessions 46 vs 41, wars 66 vs 53, succession crises 55 vs
  67, final surviving civs about equal.

Governance-only metrics (`extract_governance_metrics`), 20 seeds:

| Metric | Value |
| --- | --- |
| PSI crisis share of civ-turns | 10.3% (33 onsets in 18 of 20 runs) |
| Stability, in crisis vs calm | 16.1 vs 20.6 |
| Crisis onsets followed by an outcome 10–40 turns later | 79% (secession, revolt, civil war, succession crisis, repeal) |
| Recovery (`psi_recovery`) within 120 turns | 42% |
| All three sub-indices ≥ 1 in the 20 turns before onset | 0% |
| M67 regime reachability (share of runs where the label appears) | frozen_stable 60%, highly_fluctuating 40%, complex_cycling 100% |
| Active institutions per civ-turn | median 2 (p90 3) |
| Completed tenure | median 29 turns |
| Ruler legitimacy | p10 0.44, median 0.54, p90 0.70 |
| Ambition completion | 65% |
| Per run | 13.8 enactments, 2.1 repeals, 3.9 revolts, 0.1 civil wars, 5.4 suppressions, 2.6 elite-overproduction episodes |

Crises are driven by two elevated sub-indices at a time, mostly EMP with SFD
or with MMP. Urbanization-limited MMP rarely reaches its reference, so the
M67 all-three co-occurrence target is not met. That is the first M67
calibration item.

**500-turn sanity runs** (governance on):

* Hybrid, seeds 42–45. Worlds still collapse to remnant polities by about turn
  200, with or without governance; this is the baseline extinction bug.
  * Over the 500 turns: succession crises 17 vs 36 and secessions 35 vs 45
    against ungoverned runs of the same seeds.
  * Final institutional regimes are mixed: complex_cycling 23, frozen_stable
    14, transitional 7, inert 5.
  * Final government forms include bureaucratic monarchy, autocracy,
    monarchy, military regime and chiefdom.
  * Reform pressure fires 7.75 times per run, as late remnants fall under
    single-faction capture.
* Aggregate mode (`--agents off`), seeds 42–43. Populations survive to turn
  500.
  * PSI crisis share 4.4%, with 57% of crises recovering within 120 turns.
  * Regimes are mostly complex_cycling, with frozen_stable reached in both
    runs.

**Determinism:** the `determinism-hybrid` and `determinism-off` profiles both
pass with `--governance`.

**Runtime:** governance costs 7.0–7.5% of unprofiled wall time in 150-turn
hybrid runs (tick about 3.7 ms/turn; Phase 2 funding is negligible). That is
inside the roadmap's +3.5–8% envelope. The cost scales with snapshot rows,
because the elite adapter builds one kernel input per agent.

## Known gaps and follow-ups

* **M63b bucket coverage.** Leader, grudge, tradition, holy-war, raider,
  weariness and peace contributors are still unbucketed. Buckets apply only
  with governance on.
* **M64 commons.** There is no exploitation-rate, κ-coupling or Rust ecology
  field yet. COMMONS_MANAGEMENT only nudges soil, and graduated sanctions
  (`commons_violation_tier`) are not implemented.
* **M65b vs the Rust politics batch.** PSI acts through stability, revolts,
  civil wars and crisis odds rather than a lagged `psi` column in the Rust
  politics input. Adding that column would let secession probability read PSI
  directly.
* **Elite fast path.** A vectorized, kernel-equivalent elite classifier
  (checked against G02 in tests) is needed before 10⁴+ agents per civ.
* **Viewer.** `viewer/src/types.ts` does not yet declare
  `CivSnapshot.governance`; the M73 InstitutionTimeline and PSIDashboard
  panels are still to build.
* **Angry/neutral stall weights** (Victoria 3, 1.5/0.5) are still not modelled.
  Only the kernel's raw > 0.30 veto applies.
* **Calibration** is a first pass on 6-seed × 200-turn hybrid batches against a
  baseline that already goes extinct by about turn 200 (separate fix in
  progress). M67's 200-seed × 500-turn campaign and M61b scale validation are
  still required for scientific claims.
