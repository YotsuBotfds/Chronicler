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
