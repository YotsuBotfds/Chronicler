# Procedural drift (2026-10)

> Follow-ups in [`oracle-followups.md`](oracle-followups.md): the cohort
> oracle's windows (cohort method 3, censored at the pair's first death),
> age in the needs pairs (measured; age matching not adopted) and the
> spiritual pairing (needs method 6 reports it beside method 5's verdict).

Branch `fix/procedural-drift` from `main` `7bb2bd4` (PR #52), merged with
`db5eff4` (PR #53, native turn speed) and `13f735a` (PR #54, checkpoint
continuation), both byte-identical in output for runs without checkpoints. Diagnosis of
three procedural-world behaviours, and one oracle correction:

1. Needs concordance on procedural worlds fell with PR #51 and PR #52
   (method 4 pooled +0.169 -> +0.132 -> +0.111) while template worlds did
   not.
2. Procedural fiscal crises rose 1.40 -> 1.59 per civ-century with PR #48,
   attributed to item 1 (named-character caps that count the living).
3. Procedural restorations oscillate: in hybrid mode a restoration's +15
   stability does not hold and deposed rulers counter-restore.

**Changed:** the needs oracle, method 5 (outcomes counted while both matched
agents live; section 1.5); template and procedural full gates PASS with
it, NO REGRESSION, needs the only method change (section 4). **Not
changed:** any simulation code. No
behavioural defect was found that a change would correct: item 1 does not
raise fiscal crises in today's code, and the restoration's +15 cannot
persist in hybrid under any accumulator category.

## Method

Linux, Python 3.13.17, `PYTHONHASHSEED=0`, hybrid, one worker per batch
(`PYTHON_CPU_COUNT=2`, sequential in-process batches), each arm from a
frozen copy of its tree with its own venv and a release extension built
fresh (`maturin develop --release --locked`, its own `CARGO_TARGET_DIR`;
compiled module and the three classes checked):

| Arm | Tree | Extension SHA-256 | Reproduces |
| --- | --- | --- | --- |
| 2f654a8 | `main` before PR #51 | `735558c9...a489` | the `2f654a8` procedural full report |
| PR #51 | `7bb2bd4` with `ecology.mine_soil_realized: 0` | `c8ef41f5...b6ff` | the `c0f354d` (PR #51) procedural full report |
| main | `7bb2bd4` | `c8ef41f5...b6ff` | the `b51ec01` (PR #52) procedural full report |
| main, old repulsion | `7bb2bd4` with `2f654a8`'s `spatial.rs` | `4f736221...3aa7` | - |
| main, old caps | `7bb2bd4` with `027fb55`'s named-character Rust reverted | `0f0c228a...4df6` | - |
| main, restoration as guard-shock | `7bb2bd4`, in-process patch | `c8ef41f5...b6ff` | - |
| main, ungated intelligence | `7bb2bd4`, in-process patch | `c8ef41f5...b6ff` | - |

Every procedural arm is the procedural full gate's cohort: seeds 42-141, 300
turns, 32 regions, 10 civs, `--validation-sidecar`. A wrapper around the
validation sidecar writer (`_write_sidecar_snapshot`) also records, at each
needs snapshot, the native agent snapshot (age, wealth, position,
settlement, origin, loyalty, parents) and each region's terrain, resources,
controller, soil, food shortfall and endemic disease. It only reads: seed 42
x 40 turns with and without it gives identical files (bundle without
`generated_at`, every sidecar, the state file). The needs pairs were
rebuilt with the oracle's own matchers, one row per pair with both agents'
features: for the three arms with a report the per-seed, per-pairing pooled
and binding tallies equal the full-gate reports in all 100 seeds. The
analysis scripts and per-arm extracts (pair tables, region tables, per-world
fiscal and restoration summaries) are kept with the run reports, not in the
repository.

## 1. Needs concordance on procedural worlds

### 1.1 The drop is real

The seed-clustered standard error is calibrated: random half-splits of one
report's 100 seeds give z with standard deviation 0.997-1.012 and
P(|z| > 1.96) 0.047-0.056 (pooled and binding, four reports). Paired by seed
(worlds diverge within a few turns; seed correlation 0.07-0.31), method 4:

| Step | Procedural pooled | z | Template pooled | z |
| --- | --- | ---: | --- | ---: |
| PR #51 (`2f654a8` -> `c0f354d`) | +0.169 -> +0.132 | -2.25 | +0.175 -> +0.202 | +1.85 |
| PR #52 (`c0f354d` -> `b51ec01`) | +0.132 -> +0.111 | -1.38 | +0.202 -> +0.196 | -0.52 |
| both | +0.169 -> +0.111 | -3.46 | +0.175 -> +0.196 | |

The procedural statistic has moved this much before (method 3, paired):
PR #42 -0.035 (z -1.70), PR #48 +0.050 (z +2.47); method 3 -> 4 on the same
batch -0.026. In method 3 terms main sits near +0.137, inside the +0.129 to
+0.164 range of the gates before PR #48: the corrections took the statistic
back from PR #48's high.

### 1.2 Where it falls

By pairing (paired, `2f654a8` -> `b51ec01`): material +0.222 -> +0.149
(z -2.70), social +0.143 -> +0.077 (z -2.35), purpose +0.036 -> +0.002,
safety +0.037 -> +0.018, autonomy +0.364 -> +0.410. By window: turns 0-99
+0.150 -> +0.107, 100-199 +0.174 -> +0.095, 200-279 +0.206 -> +0.137: every
window. By region type, the change lives in one terrain:

| Pairs (method 4, pooled) | 2f654a8 | PR #51 | main | main, old repulsion | main, old caps |
| --- | --- | --- | --- | --- | --- |
| all | +0.169 (0.012) | +0.132 (0.013) | +0.111 (0.013) | +0.149 (0.015) | +0.136 (0.015) |
| coastal regions | **+0.240 (0.026)** | +0.107 (0.023) | **+0.062 (0.026)** | +0.198 (0.026) | +0.141 (0.028) |
| other regions | +0.139 (0.013) | +0.143 (0.017) | +0.130 (0.016) | +0.128 (0.016) | +0.134 (0.017) |
| coast's share of informative pairs | 0.297 | 0.294 | 0.282 | 0.296 | 0.284 |
| binding pairs | +0.168 (0.022) | +0.136 (0.022) | +0.117 (0.020) | +0.170 (0.020) | +0.177 (0.022) |

Seed-clustered standard errors in brackets (each calibrated by half-splits,
z sd 1.00-1.05, the coastal stratum included). Non-coastal pairs read
+0.128 to +0.143 in all five arms. Coastal pairs (4.2 coastal regions of 32,
29% of informative pairs) lost nearly all of their concordance: of the
pooled change of -0.059, -0.050 is within coastal pairs. It is spread over
seeds (seeds with positive coastal net 76 -> 53 of 100; per-seed median
+0.25 -> +0.05; trimming the five most positive and negative seeds changes
nothing), over pairings (coastal social +0.233 -> +0.009, material
+0.256 -> +0.119), windows, cell sizes, urban and rural agents, kin and
non-kin pairs, pair distances and bond configurations. Mining regions (8% of
pairs, where the mine-soil correction acts) read +0.167 -> +0.127.

### 1.3 What did it

Three exact arms and an ablation separate the corrections:

* **The coincident-repulsion correction (PR #51) carries most of it.**
  Reverting `spatial.rs` alone on today's `main` restores coastal pairs to
  +0.198 (from +0.062) and the pooled net to +0.149; PR #51's step moved
  coastal pairs +0.240 -> +0.107 (realized mineral depletion included). Two
  independent contrasts give -0.13 each. The population-entities ablation
  (the repulsion reverted on PR #51) gave +0.151 pooled, the same.
* **The mine-soil correction (PR #52)** moved coastal pairs +0.107 -> +0.062
  (z -1.3; -0.013 of the step's -0.022) and the mortality composition (1.4,
  -0.008).
* **Coastal concordance is a sensitive stratum.** Restoring the old
  named-character caps on today's `main`, an unrelated change, moves it
  +0.062 -> +0.141 (z +2.1), non-coastal pairs again unchanged.

What does not change between the arms on coasts: agent-turns per world
(48,043 / 47,922), crowding (0.60), food-shortfall share (0.23), migrations
(69.4 / 68.9 per 1,000 agent-turns), their drivers (famine memory 32%,
spiritual need 12%, wage 11% in both), sea or land destinations, deaths
(18.1 / 18.2), births, mean needs; world-wide, household follows (31.3 per
1,000 agent-turns in every arm), marriages' births, inheritance, and agents
coincident within 0.001 (2.05% / 2.08%; coasts 1.21% / 1.14%). Positions
enter only bond and marriage formation (`formation.rs`); the bond
configuration of coastal social pairs (both bonded 84%, low agent isolated
13%) is the same in both repulsion arms, and the drop is inside each
configuration. **The micro-mechanism inside coastal cells is not
identified**: the correction changes which coastal agents with lower needs
also move more, not how much anyone moves.

### 1.4 The hypotheses

| Hypothesis | Test | Verdict |
| --- | --- | --- |
| Less hardship variance, fewer divergent pairs | Within-cell need spread (median sd material 0.0296 / 0.0288, social 0.0440 / 0.0437), shares below threshold (material 3.62% / 3.43%, social 7.65% / 7.61%), pairs 9,314 / 8,900, informative 6,007 / 5,678 | Refuted: the spread and counts barely move, and a count cannot move a ratio |
| A change in the composition of the matched pairs | Kitagawa split of the change by every stratum above (terrain, window, gap, binding, mortality, recent migrants, kin, children, urban, wealth, age, cell size, crowding, food) | Composition terms are below 0.005 except mortality (-0.016, 27% of the drop, 1.5); the rest is within strata |
| Another mechanism now dominates the pairings | Binding share of informative pairs 35% / 34%; migration drivers identical (first 60 worlds of each arm: famine memory 39%, wage 11%, spiritual need 9%, material need 0.8%, social need 1.4%); the material pairing's concordance comes mostly through famine memory (+0.13 of +0.22; +0.12 of +0.15), its own term +0.04 / +0.03 | Refuted |
| A real defect: a need no longer drives its behaviour | No needs code changed in PR #51 or #52; need-driven migrations 0.60 / 0.55 (material) and 0.96 / 1.02 (social) per 1,000 agent-turns (first 60 worlds); non-coastal concordance unchanged | Refuted |
| A measurement artifact in pair matching | SE calibration (1.1); matching unchanged; a separate flaw in the outcome window found (1.5) | The drop is not an artifact; the window flaw is real and contributes the mortality composition term |

Spiritual need, which drives 9% of migrations and has no oracle pairing,
reads +0.077 -> +0.111 as an informational spiritual -> migration pairing
(method 5: +0.105 / +0.102): not eroded.

### 1.5 A measurement flaw: deaths in the outcome window (method 5)

Method 4 counts each matched agent's events over the whole window t+1 ..
t+20. An agent that dies in the window has less time to act, so a pair in
which one agent dies is decided by who died. Needs rise with age (the higher
agent is older in 68% of informative pairs) and the old die: on the procedural full gate
52% of informative pairs had a death in the window, the higher-need agent's
alone 26% of them (net +0.70), the lower-need agent's 18% (net -0.54), both
9% (net 0.00); pairs where both lived read +0.169 / +0.097. Method 4 credits
the needs with what mortality did.

**Synthetic demonstration** (200 replicated batches of 10 seeds x 60 cells,
two matched agents per cell, material 0.2 / 0.7, migration hazard per turn
independent of the need unless stated; full-profile verdicts):

| World | Method 4 PASS | Method 5 PASS | Method 4 net | Method 5 net |
| --- | ---: | ---: | ---: | ---: |
| no effect, equal mortality (0.15) | 4.5% | 5.5% | -0.003 | -0.004 |
| no effect, higher-need agent dies more (0.05 / 0.30) | **52.0%** | 5.5% | +0.100 | +0.001 |
| no effect, lower-need agent dies more (0.30 / 0.05) | 0.0% | 4.0% | -0.100 | -0.002 |
| effect (hazard 0.06 / 0.04), equal mortality | 100% | 100% | +0.291 | +0.299 |
| effect, lower-need agent dies more | 98.5% | 100% | +0.186 | +0.294 |

**Method 5** (`NEEDS_ORACLE_METHOD_VERSION = 5`) ends each pair's window at
the first death of either agent (that turn's events count: decisions precede
deaths in a tick, and no event follows a death in the stream). Matching,
criteria, profiles and output fields are method 4's; results add
`outcome_censoring: "first_death_in_pair"` and `censored_pairs` (pooled and
binding). Death turns come from `agent_events.arrow`
(`_load_agent_deaths`, `run["deaths"]`); a run without them scores as
method 4. `run_needs_oracle(..., method_version=4)` re-scores method 4
exactly; the comparator reports 4 against 5 as a method change
(`rebaseline_required`), never as a new or resolved failure. No threshold
changed.

Re-scored (every retained needs sidecar set, and the capture batches above):

| Set | Method 4 pooled (lb), seeds | Method 5 pooled (lb), seeds | Method 4 binding (lb) | Method 5 binding (lb) | Full gate 4 / 5 |
| --- | --- | --- | --- | --- | --- |
| procedural full, `main` (`b51ec01` sidecars) | +0.111 (+0.088), 84 | +0.091 (+0.066), 72 | +0.117 (+0.084) | +0.134 (+0.098) | PASS / PASS |
| procedural full, `2f654a8` | +0.169 (+0.149), 89 | +0.145 (+0.122), 83 | +0.168 (+0.131) | +0.201 (+0.162) | PASS / PASS |
| template full, `main` (this branch's gate, section 4) | +0.196 (+0.177), 170 | +0.166 (+0.144), 154 | +0.176 (+0.152) | +0.191 (+0.164) | PASS / PASS |
| template full, needs follow-ups head `d44cf4f` (200 x 500) | +0.209 (+0.190), 175 | +0.170 (+0.150), 168 | +0.185 (+0.160) | +0.197 (+0.170) | PASS / PASS |

Over the 48 retained 20 x 200 sets (`needs-followups`, `needs-oracle-power`;
the method 4 re-scores equal `validation-integrity`'s in all 48):

| Sets | Subset profile PASS, method 4 -> 5 | Full-profile rules PASS, 4 -> 5 |
| --- | --- | --- |
| 15 with the need terms on (needs-followups) | 15 -> 14 | 12 -> 11 |
| 15 with the need terms zeroed (needs-followups) | **15 -> 8** | 3 -> 2 |
| 5 with the terms on (needs-oracle-power, older code) | 5 -> 4 | 3 -> 2 |
| 3 with the terms zeroed (needs-oracle-power) | 2 -> 1 | 0 -> 0 |
| 3 hunger mid range (not shipped) | 2 -> 2 | 2 -> 1 |

Method 4 passed every terms-zeroed subset under the subset profile; method 5
fails about half of them while keeping 14 of 15 terms-on subsets: the
mortality channel was part of what made zeroed terms look alive. Method 5
also lowers the procedural drop's mortality term (-0.054 with method 5,
coastal pairs +0.186 -> +0.041): it does not explain the drop.

### 1.6 Why procedural only

Template worlds have as many coastal pairs (28% of informative pairs), but
their coastal concordance does not respond. Template arms of `main` and
`main` with the old repulsion, seeds 42-121 x 500 turns (the template full
gate's first 80 seeds; `main`'s per-seed tallies equal the `b51ec01`
template report in all 80):

| Template pairs (method 4) | main | main, old repulsion |
| --- | --- | --- |
| all | +0.184 (0.019) | +0.190 (0.017) |
| coastal regions | +0.158 (0.036) | +0.186 (0.037) |
| other regions | +0.194 (0.022) | +0.191 (0.020) |

Template coastal pairs differ by -0.028 (z -0.5). What responds is
procedural coasts. Template and procedural coasts differ
in the maritime layer: sea trade runs in every procedural world (30% of
template worlds, a tenth of the volume per civ) with fleets and colonies.
The repulsion correction acts almost only on merchants: agents within 0.001
of another are 6.8% of coastal merchants and 18.4% of other merchants
(placed at the same trip entry point, `spatial::transit_entry_position`)
against 0.05-0.2% of every other occupation (procedural `main`, 40 worlds,
every 50 turns). Coastal pairs are 81% farmers. How the merchants' new
spacing reaches coastal farmers' need contrasts (through bond and marriage
formation, the only place positions enter) is not established.

## 2. Fiscal crises and the named-character caps

A fiscal crisis (`governance_runtime.fund_institutions_phase2`) starts when
the projected treasury cannot pay the institutions' enforcement demand
(funding ratio below 1; an episode ends at full funding). Great persons have
no upkeep or stipend: the army is the only upkeep (`finance._plan`). Their
treasury channels are agendas (a trading house costs 15, a shrine a
temple), merchants' crown lending (domestic credit capacity x1.5 per
lender, at most two), the court (through the elite consumption index, in
which a living agent-backed great person counts as an elite qualifier) and
the wars generals' campaign agendas bias toward (`WAR` x1.1).

**Item 1 does not raise fiscal crises in today's code.** Paired over the
same 100 worlds (per world, 300 turns; fiscal crises per world are about
1.44 x 30 civ-centuries):

| Measure (per world unless stated) | `main` | `main`, old caps | z |
| --- | ---: | ---: | ---: |
| fiscal crises per civ-century | 1.437 | 1.518 | +0.99 |
| fiscal crises, turns 0-99 | 17.96 | 15.39 | -2.95 |
| fiscal crises, turns 100-199 | 12.74 | 14.44 | +1.42 |
| fiscal crises, turns 200-299 | 12.41 | 15.71 | +2.38 |
| great persons per civ-turn | 1.108 | 0.946 | -5.77 |
| agendas declared | 165.9 | 107.5 | -14.4 |
| trading houses founded | 15.8 | 8.5 | -8.5 |
| wars declared / calls to arms | 32.8 / 5.8 | 34.2 / 5.5 | +0.8 / -0.6 |
| loans taken / defaults | 75.4 / 9.4 | 79.2 / 9.7 | +1.2 / +0.4 |
| PSI crises / elite overproduction events | 7.3 / 7.1 | 8.7 / 7.8 | +3.0 / +3.3 |
| mean treasury / court spending per civ-turn | 416 / 22.5 | 388 / 20.6 | -1.9 / -1.9 |

The old caps name up to 50 agent-born persons per world in the first
decades and almost none after turn 50; the living caps name fewer early and
a steady stream later. Fiscal crises follow the opposite way in each
century: more of them where fewer great persons live. So the living caps
do not cause crises; if anything, great persons reduce them (more treasury,
fewer PSI crises; the crown-credit and trading-house channels are the
likely ones, not separated here).

**Item 3 (accuracy bonuses only toward civs in contact) does not either**:
restoring the ungated bonuses on `main` gives 1.432 per civ-century (z
-0.07), wars declared 33.9 (z +0.75).

**The 1.40 -> 1.59 rise.** PR #48's full gate measured 42.05 -> 47.76 fiscal
crises per world (+13.6%, paired z +2.09, all four items together). The
same statistic across today's arms, whose differences have nothing to do
with finance, spans 1.43-1.59 per civ-century (`2f654a8` 1.592, the PR #48
simulation, reproducing the gate's 1.59; PR #51 1.550; `main` 1.437; old
repulsion 1.436; old caps 1.518; ungated intelligence 1.432): any change
that reshuffles trajectories moves it by up to about 0.1, and `main`, with
items 1 and 3 in place, is back at 1.44. The rise is within that
version-to-version spread and is not attributable to item 1 or item 3. Not
a defect; nothing changed. Procedural fiscal crises stay about four times
the template rate per civ (1.44 against 0.34 per civ-century; open
item 5 of `procedural-gates.md`: wars in reach borrowing for their war
chests).

## 3. Restorations in hybrid mode

### 3.1 Why the +15 does not persist

`succession.check_exile_restoration` (Phase 10) adds 15 stability through
the accumulator as `keep`. In hybrid mode `AgentBridge._write_back` sets
every civ's stability to `min(100, mean satisfaction x mean loyalty x 100)`
after each agent tick, so the +15, applied at the Phase 10 keep flush, holds
from the end of the restoration turn until the next tick's write-back: the
end-of-turn snapshot, the next turn's Phases 1-9 and that tick's input
(`stability_bonus = stability / 200`, +0.075 satisfaction for one tick).
The next Phase 10 restoration check reads the agent value. Origin stability
around the 176 restorations of the `main` arm (history snapshots, which
record the end of each turn):

| Origin stability at the end of | the turn before | the restoration turn | 1 turn later | 4 turns later | 9 turns later |
| --- | ---: | ---: | ---: | ---: | ---: |
| mean, `keep` (`main`, 176 restorations) | 17.9 | 31.6 | 18.4 | 18.8 | 19.7 |
| share below 20 | | 3% | 63% | 59% | 49% |
| mean, routed as guard-shock (probe, 182) | 16.8 | 16.3 | 17.5 | 17.3 | 18.6 |
| share below 20 | | 100% | 72% | 72% | 59% |

The deposed ruler becomes a pretender at once
(`create_exiled_leader`) and its origin is below 20 at the next check:
74 of 176 restorations (42%) were counter-restorations, 44 within 10 turns
(2f654a8: 60 of 161; PR #51: 67 of 158; old caps 96 of 200; old repulsion
71 of 171).

### 3.2 Not an accumulator-category defect

This is the overwrite the question named, but rerouting it does not help.
Stability is not a stored quantity in hybrid: it is recomputed every tick
from satisfaction, which is itself recomputed from conditions, and loyalty.
A one-shot change, whatever its category, reaches the agents for one tick.
Routed as `guard-shock` (the B-1 convention of the passive recovery, the
election +10 and the vassal +10), the +15 becomes a positive stability
shock in the next tick (+15 / max(stability, 10), merged and clamped): the
probe shows 182 restorations (0.061 per civ-century) and 71
counter-restorations (39%) against 176 (0.059) and 74 (42%), and lower
origin stability afterwards (72% below 20 a turn later, 63% with `keep`):
the next turn's Python phases no longer see the +15, and the shock lifts
the next end-of-turn stability by about one point (16.3 -> 17.5). The merged
shock is not saturated for low-stability civs (civs at 1-19: mean +0.07, 8%
at +1.0, 37% negative; 5 probe worlds), so the shock arrives, and is gone the
tick after. Civs below 20 differ from the rest mostly in satisfaction (0.456
against 0.553; loyalty 0.429 against 0.459).

So no accumulator category makes a one-shot +15 persist in hybrid, and the
`keep` routing was left as it is (changing it alters hybrid trajectories
with no measured benefit). The oscillation comes from the restoration rule's
gate (origin stability below 20, 5% a turn, x1.5 when the exile's faction
does not dominate) reading an agent statistic that the restoration cannot
move for more than a turn. Options, each a design decision with its own
gates: a grace period after a restoration during which its civ's pretenders
cannot be restored; a restoration that acts on the agents (a loyalty boost
to the origin's agents); or a gate on a smoothed stability.
`politics.py`'s civ restoration (stability set to 50 through `keep`) has the
same one-turn effect in hybrid; it was not measured.

## 4. Gates, tests

Both full gates ran on the branch head (`10c67a8`: `main` `13f735a` plus
the oracle change), from a frozen copy of the tree, with a release
extension built fresh from it (`maturin develop --release --locked`, own
`CARGO_TARGET_DIR`; compiled module and the three classes checked;
SHA-256 `99c1e1d5...e12f`), `PYTHONHASHSEED=0`, one gate at a time, a
fresh empty output root each, against `main`'s method 4 full reports
(`b51ec01`, the `7bb2bd4` simulation):

```
python scripts/m53b_run_validation.py --profile full --parallel 3 \
  --require-strict-regression --output-root <fresh> \
  --baseline-report <main template full report>
python scripts/m53b_run_validation.py --profile full --worldgen procedural \
  --parallel 3 --require-strict-regression --output-root <fresh> \
  --baseline-report <main procedural full report>
```

| Gate | Verdict | Comparison | Needs, method 4 -> 5: pooled (lb), seeds | Binding (lb), seeds | Informative pairs | Censored pairs (pooled / binding) |
| --- | --- | --- | --- | --- | --- | --- |
| template full, 200 x 500 (1,582 s) | PASS, exit 0 | NO REGRESSION, exit 0 | +0.196 (+0.177), 170 -> +0.166 (+0.144), 154 of 200 (120 required) | +0.176 (+0.152), 150 -> +0.191 (+0.164), 155 | 9,748 -> 8,114 | 7,831 / 3,990 |
| procedural full, 100 x 300 (1,430 s) | PASS, exit 0 | NO REGRESSION, exit 0 | +0.111 (+0.088), 84 -> +0.091 (+0.066), 72 of 100 (60 required) | +0.117 (+0.084), 74 -> +0.134 (+0.098), 67 | 5,678 -> 4,781 | 4,410 / 1,799 |

* **Only the needs method differs.** Each comparison lists one oracle
  method change, needs 4 -> 5 (PASS / PASS), and sets
  `rebaseline_required`; no new or resolved required failure, no
  regression reason. Every other oracle's result (arcs, artifacts, cohort,
  community, determinism SKIP, era, regression, per seed included) is
  JSON-equal to `main`'s report, and the twelve regression metric deltas
  are 0.0. Regression and artifacts adjudicate strict in both.
* **Method 4 re-scores exactly.** `run_needs_oracle(load_seed_runs(batch),
  profile="full", method_version=4)` on each new batch equals `main`'s
  needs result (the whole result: per seed, by pairing, binding); method 5
  through the same loader equals the gate's needs result. The procedural
  method 5 numbers equal the re-score of `main`'s retained sidecars in 1.5.
* Other oracles (both gates PASS): artifacts 1.846 / 2.500 per civ-century
  (strict); cohort 200 / 200 and 100 / 100 seeds in the expected direction;
  community 200 / 200 and 100 / 100 qualifying; era 200 / 200 and 100 / 100
  with inflections, one silent collapse seed each; arcs six families;
  regression strict (satisfaction mean 0.621 / 0.567).

These two reports are the method 5 baselines for later gates. Method 5 adds
no simulation or persisted state (checkpoints are unaffected; a resumed
run keeps every agent event, which is where the deaths come from).

Tests:

* New tests (`tests/test_validate.py`): a mortality-only synthetic world
  (method 4 PASS, method 5 not); the window ending at the pair's first
  death (either agent, that turn included); a run without deaths scoring
  as method 4; deaths loaded from `agent_events.arrow`; the method-version
  argument (2-5 accepted, 1, 6, `True`, `"4"` refused; method 4 has no
  censoring fields). `tests/test_validation_compare.py`: method 4 against
  method 5 is a method change in both profiles, not a new failure.
* Focused validation suites at the merge head `ee9da60`: 262 passed.
* `python scripts/run_python_oracle_checks.py` at `ee9da60`: PASS in
  84.0 s, all 11 chunks PASS.
* `pytest -m "not slow" -n 2` with a fresh release extension of `7bb2bd4`,
  at `c7cec53` (before the merges of PR #53 and PR #54): 6,579 passed, 3
  skipped. Not rerun after the merges, which change no file this branch
  changes; their native code needs its own extension.

## 5. Open

* **The coastal micro-mechanism** (1.3, 1.6). Which coastal agents with the
  lower need move more after the repulsion correction, and how the
  merchants' spacing reaches coastal farmers' need contrasts, is not
  identified.
* **Coastal pairs are a volatile stratum.** An unrelated change (the old
  caps) moves them by +0.08 (z +2.1). Procedural pooled concordance has
  moved 0.03-0.05 per version before (1.1); future steps of that size need
  not mean a needs defect.
* **Method 5's procedural margin is narrower.** 72 of 100 seeds against 60
  required (method 4: 84), lower bound +0.066; template 154 of 200 against
  120. Later gates compare against the section 4 reports; one against an
  older method 4 report needs its baseline re-scored.
* **Other oracles' windows.** The cohort oracle also counts outcomes over a
  whole window; whether deaths bias it was not examined.
* **Age is not matched.** Method 5 removes the mortality channel, not every
  age-linked behaviour; the higher-need agent is older in 68% of
  informative pairs.
* **Spiritual need has no oracle pairing** (9% of migrations; the
  informational pairing reads +0.10).
* **Fiscal mediators.** Which channels (crown credit, trading houses, PSI
  crises) carry great persons' effect on fiscal crises was not separated.
* **Restorations.** The oscillation stays; the options in 3.2 are design
  decisions with their own gates. `politics.py`'s civ restoration
  (stability 50 through `keep`) was not measured in hybrid.
