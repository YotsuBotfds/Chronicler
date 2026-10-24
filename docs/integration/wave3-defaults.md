# Wave 3 defaults: oracles for living worlds

Branch `feat/wave3-defaults`, based on `integrate/wave-3` at `92b6122`
(PR #20: the world-extinction and food-balance fixes, plus epidemiology,
finance and diplomacy behind default-off switches). This branch first
recalibrates the validation oracles that were tuned on worlds that died,
then decides the three defaults on a full gate.

Each oracle change is its own commit and section below: the old and new
definition, the evidence that the old one measured the wrong thing on living
worlds, and its effect on the base with all three systems off.

## 1. Era oracle: a silent collapse is one nothing marks

**What it is for.** M53 oracle 3 (`docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`)
asks whether a run has clear rise and collapse turning points, and forbids
"silent collapses": population drops of more than 30% that do not
correspond to any detected inflection point, in more than 10% of seeds. A
silent collapse is a civilization losing a third of its people while
nothing in its era signals or its recorded history marks it, so neither the
era register nor the narrator has anything to say about it.

**Old definition.** For each civ, take its global population peak and the
lowest point after it. If the trough is at most 70% of the peak, the seed
is silent unless *any* civ has an inflection point (any of population,
treasury, stability, territory or prestige, pooled over all civs and merged
within five turns) between five turns before the peak and five after the
trough.

**Calibration history.** The M53b implementation (`e2a74a0`, 2026-03-21)
required an inflection within five turns of the trough; the canonical full
gate then had 36 silent-collapse seeds. The next day `aff1b18` ("capture
passing canonical baseline") widened the window to the whole peak-to-trough
span and pooled every civ's inflections, with no recorded rationale, and the
same gate reported 0. Those worlds died: the M53 baseline records agent
extinction at turn 77 on average.

**Why it measures the wrong thing on living worlds.**

- *Any civ's inflection counts.* A civ's collapse is "marked" by another
  civ's treasury jump. Treasury series supply 71% of all inflection points
  in base 500-turn worlds (1,837 of 2,586 over seeds 62-81); the pooled set
  holds 55 inflections per run, one every nine turns, so almost any window
  contains one whatever happened to the collapsing civ.
- *The window can span centuries.* The global peak and the later global
  minimum are often more than a century apart (seed 78: turns 23-158 for
  Vrashni Dominion). The check could only fire when a whole peak-to-trough
  window fell into a gap of the pooled set.
- *One collapse per civ.* Living civs are small (median peak about 50
  agents) and boom and bust with famine: their smoothed populations fall by
  30% or more about 21 times per 500-turn run (base, seeds 62-81). The old
  check looked at one of these per civ.
- *Finance moves it without any change to collapses.* With `--finance`,
  treasuries are homeostatic: treasury inflections fall from 1,837 to 608
  (seeds 62-81, all three systems on) and pooled inflections from 55 to 38
  per run, so gaps open in the pooled set and ordinary, well-recorded
  declines read as silent. The money-credit write-up found 5 of 20 such
  seeds on the pre-food-balance base.
- *Late civs were read on the wrong clock.* Each civ's series starts when
  the civ first appears, and the pooled inflection indices mixed series
  that start at different turns (a seceded civ's index 0 is not turn 1).

Two cases the old rule flags, both heavily recorded:

- Seed 55 (all three on, 200 turns): Kethani Empire falls from 129 to 25
  people over turns 124-158. In that window the chronicle names it in 30
  epidemic arrivals, 16 famines, 12 epidemics, 11 mass migrations, 8 local
  rebellions and 3 plagues. Flagged because the pooled set has no inflection
  between turns 80 and 116 and none after.
- Seed 78 (all three on, 500 turns): Dorrathi Clans falls from 128 to 87
  over turns 304-332, with 23 famines, 8 supply shocks, 6 mass migrations,
  4 locust swarms and 2 epidemics naming it. The pooled set has a 171-turn
  gap (turns 241-412).

**New definition** (`validation_io.run_era_oracle`,
`detect_collapse_episodes`, `ERA_*` constants).

- *Collapses.* Each civ's population is smoothed with the inflection
  detector's own five-turn rolling mean. From a running peak, a collapse
  opens when the smoothed value falls to 70% of the peak (the spec's 30%)
  and follows the trough until the series regains the peak or rebounds from
  the trough by the same ratio. The next peak is tracked from there, so every
  collapse in a run is checked, not only the one below the global peak.
- *Era signal.* An inflection point of the collapsing civ's own five
  series, on world turns, between five turns before the peak and five after
  the trough (the unchanged slack).
- *Narrative signal.* A recorded crisis naming the civ (`actors` or
  `civs`) in the same window. `ERA_CRISIS_EVENT_GROUPS` lists them: hunger
  (famine, supply shock, drought, locusts, soil exhaustion, fishery
  collapse, demographic crisis), disease (plague, epidemic, epidemic
  arrival, pandemic), war (war, declaration, battle, siege, occupation, army
  destroyed, scorched earth, capital loss, conquest, annexation), flight
  (migration, mass migration, notable migration, persecution, brain drain),
  disaster (earthquake, flood, wildfire, sandstorm, supervolcano, mine
  collapse), unrest (rebellion, local rebellion, revolt, civil war,
  secession, coup, PSI crisis, vassal rebellion, loyalty cascade,
  succession and legitimacy crises) and the fall of the state (collapse,
  twilight, absorption, union annexation, vassalization). Fiscal, cultural
  and routine events do not count.
- A collapse with neither is silent. Unchanged: a seed with a silent
  collapse is a silent seed; PASS needs at least 80% of seeds with two or
  more inflections and at most 10% silent seeds.
- The report adds `collapse_episode_count`,
  `collapses_marked_by_era_signal`, `collapses_marked_by_crisis_only` and
  `silent_collapse_episodes` (seed, civ, peak and trough turns and sizes),
  and per seed `collapse_count` and `silent_collapse_count`. Inflection
  turns are now world turns.

**It still fails what it should.** Unit tests: a slow 40% decline of one civ
is silent even when another civ's treasury jumps inside it (the old rule
passed it); a crisis naming the collapsing civ marks it, one naming another
civ, or one long before or after, does not; a late civ is read on world
turns; one silent seed in ten passes and two fail. On real batches, removing
the crisis events (a world whose deaths go unrecorded) leaves 17 of 20 base
seeds, 15 of 20 all-on seeds (500 turns) and 19 of 20 all-on seeds (200
turns) with silent collapses: FAIL. Removing only the hunger group leaves
0-2 silent seeds, so the verdict does not rest on famine alone.

**Effect, seeds 62-81 at 500 turns and the all-on subset.**

| Batch | Old rule | New rule |
| --- | --- | --- |
| All off, seeds 62-81, 500 turns | PASS, 0 silent seeds | PASS, 0 silent; 429 collapses, 335 marked by the civ's own era signals, 94 by recorded crises only |
| All on, seeds 62-81, 500 turns | PASS, 1 silent seed (78) | PASS, 0 silent; 405 collapses, 244 era-marked, 161 crisis-only |
| All on, seeds 42-61, 200 turns | PASS, 1 silent seed (55) | PASS, 0 silent; 237 collapses, 137 era-marked, 100 crisis-only |

The full-gate effect on the base is in [Gate results](#gate-results).

## 2. Late-run satisfaction: the late run, not its last sample

**What the ceiling protects.** The M53 regression suite bounds the agents'
satisfaction distribution: mean 0.45-0.65 and standard deviation 0.10-0.25
over the run (spec section 7.2). Below the floor agents starve or revolt
without end; above the ceiling nobody has a reason to migrate or rebel. The
run-wide `satisfaction_mean` check carries both bounds and is unchanged.

**What `latest_satisfaction_mean` was for, and where it was set.** It came
in with `bcd96e1` (2026-05-10, "gate regression on latest satisfaction");
its test is `test_run_regression_summary_requires_latest_satisfaction_to_clear_floor`.
It reused the run band to catch late-run collapse on worlds that died: the
M53 baseline records agent extinction at turn 77, terminal living
population was not required until `cebc650` (2026-10-05), and the statistic
walks back to the last sample that still has agents, so on those worlds it
read the dying cohort. The food-shortage weight cuts that the food-balance
work undid (0.10, 0.08, 0.07) were made to meet this floor. Its ceiling
never bound until worlds lived.

**Why one sample measures the wrong thing on living worlds.** Seasons
(`resources.get_season_id`: a 12-turn year) and the climate cycle
(`climate.get_climate_phase`: 75 turns) are functions of the turn number.
Every world's last sample therefore falls on the same calendar point: turn
499 and turn 199 are both autumn of a drought phase, so both standard
profiles end at harvest. The final sample is also the only one taken off the
sampling grid: regular samples read the tick of turn T for T a multiple of
10 (always an even turn of the year), the post-loop sample reads the tick of
turn 499 (the seventh). Since the food-balance fix, satisfaction follows the
harvest, and averaging 200 worlds does not remove a swing they all share:

- Base full profile (seeds 42-241, 500 turns), pooled over the 200 worlds:
  0.580 at turn 480, 0.602 at 490 and 0.643 at the final sample. By season
  of the sampled turn (turns 50 and later): spring 0.591, summer 0.597,
  autumn 0.598, winter 0.562. 153 of the 200 worlds end above their own
  last-60-turn mean (by 0.038 on average); the last 60 turns pool to
  0.607 and the run to 0.594.
- Base seeds 62-81, 500 turns: 0.573, 0.589 and 0.651 at the same three
  samples. That batch fails regression on the ceiling alone (0.6513; run
  mean 0.599); 17 of its 20 worlds end above their last-60-turn mean. The
  full base gate passes it by 0.007.
- High final samples come with somewhat less late unrest, as they should,
  not with a quiet late game: in the base full profile, the 100 worlds whose
  final sample is above 0.65 have late-run (last 100 turns) migration 0.046
  and rebellion 0.042 per agent-turn, inside the 0.02-0.08 rebellion band;
  the other 100 have 0.054 and 0.065.

**New definition.** `latest_satisfaction_mean` is the agent-weighted mean
of every sampled turn in the 60 turns ending at the run's last sample with
living agents (`REGRESSION_LATEST_SATISFACTION_WINDOW_TURNS`), with the
same band (floor 0.45, calibrated floor 0.40, ceiling 0.65). With the
sidecar's 10-turn cadence, 60 turns visit every even turn of the 12-turn
year once: the same seasonal mix as the run-wide mean. A dying world's
window still ends at its last living sample, and a late collapse still fails
the floor (tests: a final harvest high is pooled with the five samples
before it; a 60-turn late collapse fails; a dead world is read before its
death). The old single sample is reported as `final_sample_satisfaction_mean`.

**Effect.**

| Batch | Final sample (old) | Last 60 turns (new) | Regression |
| --- | --- | --- | --- |
| All off, seeds 62-81, 500 turns | 0.6513 | 0.6110 | FAIL -> PASS (calibrated floor: migration 0.0496 misses the strict 0.05) |
| All on, seeds 62-81, 500 turns | 0.6263 | 0.6047 | PASS (calibrated floor) both |
| All on, seeds 42-61, 200 turns | 0.6076 | 0.6098 | FAIL both (`civ_survival` 0.25; informational in the subset) |

The full-gate effect on the base is in [Gate results](#gate-results).

## 3. Founder survival band: checked, unchanged

`civ_survival` fails when every founding civ is still alive at the end in
more than 20% of runs (with any run losing all civs). The M53 spec sets it as
a design target for turn 500 ("0 or all 4 surviving in >20% of seeds"): a
500-turn history in which no founder falls in more than a fifth of the
worlds has no state death. It was not tuned on dying worlds; there it read
0.0 and never bound. It measures the right thing on living worlds, so it is
unchanged.

Is it sitting in noise? The base full profile reads 0.165 (33 of 200).
That is 1.3 binomial standard deviations (0.026) below the limit; the 95%
interval is 0.12-0.22. A fresh 200-seed set from the same worlds would fail
it about 8% of the time (9% at 0.167, the rate pooled over every base
batch here, 40 of 240 runs). The 20-seed subset reads it at 200 turns, not
the spec's 500, and fails it by chance about 23% of the time; it is
informational there. Base batches: 0.15 (seeds 42-61, 200 turns) and 0.20
(seeds 62-81, 500 turns). All three systems on: 0.25 and 0.20 on the same
seeds. The full-profile reading with all three on is in
[Gate results](#gate-results).

## 4. Other thresholds: checked, unchanged

Every other required check was compared with its calibration history and its
margin on the base full profile (seeds 42-241, 500 turns, all three off).
None is demonstrably calibrated on dying worlds in a way that misreads
living ones, so none changes.

| Check | Band | Base full | History and reading |
| --- | --- | --- | --- |
| satisfaction mean (run) | 0.45-0.65 | 0.594 | M53 spec band; 0.056 inside. Carries the ceiling the spec means. |
| satisfaction std | 0.10-0.25 | 0.182 | M53 spec. |
| migration per agent-turn | 0.05-0.15 (calibrated floor 0.045) | 0.0556 | M53 spec band; the 0.045 tolerance came with `bcd96e1` for stochastic batches. Living worlds have read 0.048 (extinction fix), 0.0556 (food balance) and 0.0496 on base seeds 62-81 at 500 turns: it is the tightest required margin left, and it moves with crowding, which the food-balance brake now holds at about two thirds of capacity. A strict miss is a `calibrated_floor` pass that `validation_compare` reports as a regression against a strict baseline. |
| rebellion per agent-turn | 0.02-0.08 | 0.0529 | M53 spec. |
| Gini in range | at least 20% of civs in 0.30-0.70 | 85% | |
| occupation | no share above 70% or at 0; latest-turn agents | 0.14%, latest 0.02% | |
| treasury | no long negative streaks | 0 seeds | Finance floors treasuries at zero. |
| artifact creation | 1-3 per civ per 100 turns (tolerance 0.90) | 1.10 | M53 spec; lowered to this level by the extinction fix's treatise-flood correction. Base seeds 62-81 read 0.94 (the tolerance). |
| artifact loss | 2-30%, both channels | 3.8% (40 lost, 127 destroyed) | Recalibrated in `b63ea62` with evidence. |
| arcs | 5 of 6 families, none above 40%, 50% of seeds with 3 types | 6 families, 161 seeds | |
| needs / cohort / community | 60% / 60% / 75% of seeds | 190 / 200 / 200 | |
