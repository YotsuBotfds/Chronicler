# Seats of learning (`--scholarship`)

Branch `feat/scholarship` from `main` `fc01d6e` (PR #44, turn speed).
Code: `src/chronicler/scholarship.py` (behaviour),
`src/chronicler/scholarship_state.py` (persisted state), hooks in
`techniques.py` (research, adoption, carried techniques), `historiography.py`
(archive copies, the scholars' own chronicles), `agent_bridge.py` (two region
columns), `narration_context.py` (standing state), the Rust learning driver in
`chronicler-agents/src/migration_drivers.rs`; viewer `LearningPanel.tsx`,
`lib/learning.ts`; scripts `scholarship_report.py` (a seat's record),
`scholarship_probe.py` (what seats do to techniques and archives, per world),
`scholarship_identity.py`, `build_learning_fixture.py`.

**Status.** TBD

## Result

TBD

## Design

Knowledge already moved: techniques are practised per region and diffuse
along the contact ledger ([techniques.md](techniques.md)); chroniclers keep
archives that sacks and fires destroy ([historiography.md](historiography.md)).
Nothing kept it in a place or in anyone's hands. A seat of learning is that
place, its scholars are those hands, and both can be lost.

### Seats

One seat per region, identified by its index in `ScholarshipState.seats`
(fallen seats stay in the list). Three kinds, each with its patron:

| kind | founded by | when (per turn) | founding cost | kept by (upkeep) |
| --- | --- | --- | --- | --- |
| academy | the ruler, at its capital | treasury 60, culture 30, stability 30, at peace, the capital not in famine, no academy of its own; chance 0.03 (x2 under the scholarship focus or the Knowledge value) | 30 treasury (`keep`) | the region's ruler's treasury (`keep`) |
| temple school | a temple of the realm's faith | prestige 30, its faith not persecuted there; chance 0.02 | 10 prestige | the temple's prestige (its offerings) |
| library | a city of rank 2 or more (`--cities`) | 20 in its civic purse; chance 0.05 | 20 from the purse | the civic purse |

A seat has a **level** (modest, renowned, great). Upkeep is 0.3, 0.6 and 1.0
a turn by level, paid in whole units with the fraction carried. A patron that
cannot pay four times in a row costs the seat a level (and a modest seat its
life). Every 20 turns at most, a seat whose patron is paying rises a level
when its scholars reach 5 (renowned) or 10 (great) and the patron pays the
fee (20, 40).

### Scholars

The scholar body of a seat, at the reference scale (`cities.scale`, mean
region capacity / 60):

- the agents of the scholar occupation in its region (Phase 10 agent rows);
  with `--agents off`, 10% of the region's people;
- 2 for every great scholar (an active great-person scientist of the seat's
  ruler) teaching there: in the seat's region, or, for one in none of the
  ruler's regions, at the ruler's best seat (`seat_master` event the first
  time a great scholar teaches at a seat);
- refugees from fallen seats, 5% of whom settle or leave each turn.

**Drawn by migration** (Rust, `migration_drivers.rs`, a fifth healthy-world
driver in the style of the urban pull, with its own gate). Python gives each
region a `seat_pull`: its seat's level weight (0.4, 0.7, 1.0), halved while
the patron fails to pay, zero while the region is occupied. The gate: a
scholar adult; a neighbouring region of the same realm whose `seat_pull`
exceeds home's by 0.25; that region fed (food sufficiency 1) and below
capacity. Pull 0.5 x ramp(gap, 0.25, 0.75), opening at `PULL_AT_GATE` as the
other drivers do; it counts net of roots and only toward a region the agent
would not leave again at once. For 10 turns after a seat falls, its region
carries `seat_flight`: its scholars' learning pull may then cross a border to
a seat next door (the only voluntary pull that may). No existing weight
changes; the pull is added last (`VoluntaryPull::total`), so with no column
the sum keeps its bits; no new random draw. The budget gains the `learning`
term (appended after `social_need`, `TERM_LEARNING` = 19) and
`open_learning` / `gate_learning`; `models.MIGRATION_DRIVER_NAMES` and
`VOLUNTARY_MIGRATION_DRIVERS` gain `learning` ("left X for the seat of
learning in Y").

### What learning does

| effect | where | rule |
| --- | --- | --- |
| invention | `techniques._research_multiplier` | research x(1 + 0.15 x the levels of the ruler's living seats, at most 4 levels counted) |
| adoption | `techniques._update_practice` | the diffusion hazard from contacts x(1 + 0.4 x level) in the seat's region and x(1 + 0.15 x level) next to it |
| keeping | `techniques._update_practice` | forgetting x(1 - 0.15 x level) in the seat's region |
| archives | `historiography` `_Turn.copies` | an archive in a seat's region keeps one more copy per level; one more for another seat of the owner's realm; at most 3 more |
| migration | Rust learning driver | above |

### What destroys it

| strike | rule | at level 1 | above |
| --- | --- | --- | --- |
| sack | the region taken by an enemy at war, newly occupied, or a city of it sacked; a temple school's temple burned by a conqueror | falls | falls with chance 0.5, else loses a level |
| famine | a famine report in its region (not a dearth), chance 0.3 | falls | loses a level |
| persecution | 5 turns of persecution of the scholars' faith in its region (an academy keeps the court's faith, a temple school its temple's, a library its region's) | falls | falls |
| loss of patronage | unpaid upkeep four times in a row; the temple given to another faith or gone; the library's city fallen | falls | loses a level (unpaid) or falls (temple, city) |

One strike in 10 turns. Every fall and decline cites its cause (the
occupation, the sack, the famine report, the persecution, the temple's
destruction, the city's fall).

**Flight.** A fallen seat's scholars flee to the nearest living seat within 4
region hops, a rival's (another ruler's) before one of their own ruler's,
ties by seat index (`scholars_fled`, importance 5 into another realm, 4
otherwise). Half the fallen seat's body arrives as refugees. With techniques
on, the fall leaves a **carry** in the persisted state, consumed by the next
technique tick (Phase 4): in the refuge's region, up to 3 techniques the
fallen seat's region practised at 0.25 or more, which the refuge lacks
(under 0.20) and whose prerequisites it practises (0.20), highest tier
first, start at 0.20 (the refuge's civ then takes them up at once:
`technique_adopted` "X learned Y from scholars fleeing Z", channel
`scholars`, citing the flight and the source's invention or adoption); and
where the seat fell, the practice of every technique of tier 2 or more
loses 30%. A fall with no seat in reach loses the knowledge without moving
it.

### History

- **The scholars' own chronicles**: every seat has a chronicler
  (`seat:<seat index>`, "the scholars of the Academy of X") with its archive
  at the seat (1 + level copies). They write every event of the seat's
  record (founding, rises, new patrons, great scholars, refugees, strikes,
  decline, fall, flight) and the inventions made in its region, plainly (no
  transformation), citing the causes they hold. When the seat falls its
  archive goes with the scholars to their refuge (loss cause `flight`,
  survival 0.8 per copy) or is left behind (`abandonment`, 0.5).
- **Courts** tell foundings and rises as the realm's glory, and declines,
  falls and flights as disasters, from importance 3.
- The layer stays observational: the chroniclers read the seats; nothing in
  the simulation reads the chronicles.

### Contracts

- Randomness: `random.Random(stable_hash_int("scholarship", namespace,
  seed, turn, ...))`, namespaces `academy` (civ index), `school` (region
  index), `library` (settlement id), `sack` and `famine` (seat index). The
  Rust driver adds no draw.
- Identity: region index, civ index, seat index, settlement id, faith id;
  great scholars by name (as great persons are).
- Bridge signals: `seat_pull` (f32) and `seat_flight` (bool) are rebuilt from
  persisted seats for every region batch; Rust resets both from every batch
  and reads 0 / false without the columns; nothing transient is kept on the
  world. The pending carries are persisted state (saved between Phase 10 and
  Phase 4) and consumed once. Multi-tick checks:
  `tests/test_learning_pull.rs`,
  `test_native_seat_pull_signal_is_consumed_and_reset_each_turn`,
  `test_seat_pull_and_flight_come_from_persisted_seats_and_reset`.
- Accumulator: founding fees, rise fees and upkeep are `keep` treasury
  through `war.common.add_stat` (affordability read with
  `projected_treasury`); temple prestige and civic purses are changed in
  place, as temples and cities do.
- Append-only orders: `KIND_NAMES`, `PATRON_NAMES`, `LEVEL_NAMES`,
  `FALL_CAUSES`, `HISTORY_KINDS`, `COUNTER_KEYS`; techniques `CHANNELS`
  "scholars" (7); `MIGRATION_DRIVER_NAMES` "learning" (19);
  `MIGRATION_TERM_NAMES` / `TERM_LEARNING`, `VOLUNTARY_DRIVER_NAMES`
  "learning" (Rust); historiography `SURVIVAL` "flight", "abandonment".

## Turn placement

| When | What |
| --- | --- |
| Region batch, each tick | `seat_pull`, `seat_flight` from the persisted seats |
| Agent tick | the learning driver |
| Phase 4 (techniques) | seats' research factor, adoption and keeping factors; last Phase 10's carries |
| Phase 10, after cities and guilds | `tick_scholarship`: per living seat its ruler and patron, sack, temple or city, famine, persecution, upkeep, scholars and great scholars, rise, pull; falls and flights; then foundings (academies, temple schools, libraries) |
| After the turn (historiography) | the scholars' chronicles; archive copies |

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--scholarship` / `--no-scholarship` (`BooleanOptionalAction`) |
| World field | `WorldState.scholarship: ScholarshipState \| None` (presence = on), omitted while `None` |
| Default | off for new worlds (`scholarship.DEFAULT_ENABLED_FOR_NEW_WORLDS = False`); resumed, forked and caller-supplied worlds keep their saved setting |
| Gate runner | `scripts/m53b_run_validation.py --scholarship` forwards the switch and records it in `run_manifest.json` |
| Bundle | `history[n].scholarship`: living seats (id, name, kind, region, ruler, level, scholars, great scholars, refugees and unpaid upkeep while present), the fallen count, counters; omitted while off; the viewer reads `world_state.scholarship` for each seat's record |
| Analytics | `generate_report` gains `scholarship` for runs that carry it |
| Old saves | load with `scholarship` None |

## A seat's history

Template world, seed 42, 500 turns, `--agents hybrid --scholarship`
(`scripts/scholarship_report.py RUN_DIR --seat 0`). Twelve seats were founded
(2 academies, 8 temple schools, 2 libraries); 8 fell (7 for loss of
patronage, 1 to famine), every one with a refuge in reach.

**The Academy of Amber Valley** (seat 0) is the one that lasted.

- **Founding, turn 103.** Elder Oceania of the Kethani Empire founds it at
  the court, Amber Valley being the Kethani capital then (30 treasury; the
  ruler's treasury pays its upkeep for the rest of the run).
- **Scholars and rises.** Renowned at turn 123 (11 scholars). A famine
  strikes it at 129 and it drops back to modest. It is renowned again at 149
  and great at 170. Two great scholars teach there, Elder Thalor (135) and
  Warchief Nautica (201). Famines at 211 and 221 cost it two levels; it rose
  again at 241 and 268, then peaked at 23 scholars.
- **A refuge.** Five seats nearby fell and their scholars came here: two
  successive Temple Schools of Verdant Plains (Thornwall's, 128 and 194, each
  when its temple was given to another faith), the Library of Verdant Plains
  Settlement 1 (329, its city stopped paying), and the Temple Schools of
  Ashara Desert (347, its temple gone) and Obsidian Shore (382).
- **Techniques.** The Kethani Empire's only two inventions of the run
  were both made in Amber Valley while the academy stood: bronze working
  (179) and iron working (277). Its research is multiplied by
  1 + 0.15 x the seat's level. Three of its ten adoptions arrived with
  fleeing scholars: irrigation (129, the turn after the first flight),
  then horsemanship and the ox plough (195). All three were Thornwall
  inventions made in Verdant Plains (121, 183, 187), and each adoption
  cites the flight and that invention.
- **Survival.** The academy outlived the run: renowned at turn 500, with 2.5
  scholars, after the 451 famine thinned its students. Its own
  chroniclers wrote 19 accounts: the founding, each rise, strike, great
  scholar and refuge, and both inventions. The archive kept 2 to 4 copies
  through 24 plague episodes and lost none. The scholars of the second
  Temple School of Verdant Plains, by contrast, carried their archive to
  Amber Valley (cause `flight`). Of its five accounts, a plague took one
  before the flight, one was lost on the way, and later plagues took two
  more.

The same run's Library of Thornwood Settlement 1 shows a decline. It
rose to great by 211, its city stopped paying at 226, a famine struck at
374, and it closed at 376 ("its city no longer pays its masters"). Its
scholars fled to the Ashkari Academy of Stormbreak Cliffs.

## What seats do to techniques and archives

`scripts/scholarship_probe.py` over paired worlds (the same seeds with the
switch off and on), mean per world and the paired difference with its
standard error. The subsets are 200 turns. The off arms are byte-identical
to main, and the on arms reproduce the gated ones exactly. The archive
measures need `cd0ccfd`, which records the seats' copies; its simulation
equals `03a406a`'s (reports identical).

| per world | template 40 worlds: off | on | difference (SE) | procedural 20 worlds: off | on | difference (SE) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| techniques invented | 12.73 | 13.23 | +0.50 (0.42) | 14.65 | 13.95 | -0.70 (0.80) |
| techniques adopted (all channels) | 21.73 | 22.58 | +0.85 (0.84) | 65.95 | 65.30 | -0.65 (2.51) |
| adopted from fleeing scholars | 0 | 0.13 | +0.13 (0.08) | 0 | 0.40 | +0.40 (0.13) |
| techniques lost to decay | 1.45 | 0.68 | -0.78 (0.41) | 2.00 | 2.00 | 0.00 (0.68) |
| known per living civ, final | 9.45 | 9.95 | +0.50 (0.40) | 8.61 | 8.43 | -0.18 (0.32) |
| known per living civ, mean over the run | 5.89 | 6.08 | +0.19 (0.16) | 5.32 | 5.52 | +0.20 (0.19) |
| courts' and temples' accounts written | 541.5 | 570.7 | +29.2 (14.7) | 2,622.6 | 2,682.1 | +59.5 (82.1) |
| share of them lost (all causes) | 0.202 | 0.151 | **-0.052 (0.008)** | 0.209 | 0.148 | **-0.061 (0.014)** |
| agent migrations led by the learning pull | 0 | 54.8 | | 0 | 198.8 | |

**Archives.** Courts and temples lose about a quarter fewer of their
accounts: 20% to 15% on templates, 21% to 15% on procedural worlds. That
is 6.5 and 4.4 standard errors, over every loss cause, because an archive in a
seat's region, or in a realm with seats, keeps more copies against
plague, quake and fire as well as war. Few war losses strike an archive
that seats protect. Courts' and temples' archives had 81 war-loss episodes
(sack, conquest, collapse, absorption) on the 40 switched-on template
worlds, and seats kept copies in 4. On the procedural worlds the figure
is 25 of 147. In those episodes, `SURVIVAL` with the copies the archive
held, against the same episode without the seats' copies, gives the
seats' part:

| war losses where seats kept copies | episodes | accounts at risk | survived | expected with the seats' copies | expected without |
| --- | ---: | ---: | ---: | ---: | ---: |
| template, 40 worlds | 4 | 123 | 87.0% | 89.6% | 76.8% |
| procedural, 20 worlds | 25 | 2,346 | 91.2% | 90.3% | 78.0% |

So where a seat stands, a conquest or sack destroys 10-13 points fewer of
an archive's accounts. Pooled war-loss survival across the arms (68.0% off
against 59.3% on, template; 62.6% against 73.1%, procedural) mixes
different wars in different histories and is not the seats' effect.

**Techniques.** The technique counts move in the expected direction on
templates (more invented and known, half the decay losses) but within
about two standard errors. On procedural worlds they do not move. The
mechanisms act locally, on a seat's region and its ruler, while 2.9 seats
are alive at a time in a world of 4-10 civs. A civ-level count over 200
turns dilutes them. What is direct is the movement of knowledge with
people. Over the 200 full-gate worlds, 6.5 techniques per run were
carried to a refuge's region and 0.27 per run were taken up by a civ
through the `scholars` channel (34 worlds). Where a seat fell, 49
practices per run lost 30%. LONG_PROBE

## Gates

Every gate: hybrid agents, `PYTHONHASHSEED=0`, Linux, Python 3.13, the
native extension built from the branch's Rust (`maturin develop --release`,
`chronicler_agents...so` SHA-256 `5a9619cd...0262c`; unchanged since
`21a2b51`), run from an export of the commit named.
`scripts/m53b_run_validation.py --scholarship` / `--no-scholarship`,
compared with `chronicler.validation_compare`. Oracle thresholds are
unchanged.

**Fresh directories and seed sets.** `batch.py` reuses an existing
`batch_<seed>` directory and the validator finds bundles recursively, so a
rerun into a used directory would mix stale seeds with fresh ones. Every
gate below ran into its own output root, created by that run and deleted
after its reports were copied. Each output root was started once
(`gates.log`). For each report, the validator's analysed seeds
(community, era, cohort) equal the requested count. For every subset, the
probe listed the batch's `seed_*` directories and found exactly the
requested range. The full gate reports 200/200/200 analysed seeds and no
duplicate seed pairs (determinism oracle). The main baselines are
`c8f7eb4` merged-head reports; `fc01d6e` changes no output byte (PR #44).
They analysed 200/200/200 (template full), 100/100/100 (procedural full)
and 20/20/20 (subsets).

### Subsets (20 seeds x 200 turns)

The switched-off arms at `03a406a` reproduce main's subset reports exactly
(`tsub42`, `tsub62`, procedural `psub42`: every result, batch paths
normalised). The switched-on arms are compared with them.

| | 42-61 off | 42-61 on | 62-81 off | 62-81 on |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS; - | PASS; NO REGRESSION | PASS; - | PASS; NO REGRESSION |
| regression (adjudication; failed checks) | FAIL (fail); civ_survival | FAIL (fail); civ_survival | FAIL (fail); rebellion_rate_per_agent_turn, civ_survival | FAIL (fail); rebellion_rate_per_agent_turn, civ_survival |
| needs: net; lower bound; seeds (needed) | 0.210; 0.116; 17 (12) | 0.199; 0.118; 15 (12) | 0.120; 0.038; 13 (12) | 0.159; 0.060; 15 (12) |
| cohort (seeds; median effect); community; era (inflections; silent) | 20; 0.97; 20; 20; 0 | 20; 1.11; 20; 20; 0 | 20; 1.20; 20; 20; 0 | 20; 1.11; 20; 20; 0 |
| arcs (status; three types; families) | FAIL; 11; 5 | PASS; 14; 5 | PASS; 15; 5 | PASS; 15; 5 |
| artifacts (status; per civ per 100; loss) | PARTIAL; 3.04; 2.1% | PARTIAL; 3.12; 1.2% | PARTIAL; 3.42; 2.2% | PARTIAL; 3.59; 1.4% |
| satisfaction mean; latest | 0.607; 0.621 | 0.602; 0.614 | 0.618; 0.626 | 0.617; 0.617 |
| migration; rebellion per agent-turn | 0.0682; 0.0349 | 0.0692; 0.0385 | 0.0618; 0.0173 | 0.0633; 0.0180 |
| all founders survive; extinct worlds | 0.250; 0 | 0.250; 0 | 0.450; 0 | 0.600; 0 |
| final population min / median / max | 108 / 187.5 / 279 | 114 / 198 / 251 | 142 / 187 / 238 | 132 / 187.5 / 266 |

In the subset profile only community, needs and cohort are required. The
regression failures (`civ_survival`; rebellion under its floor on 62-81)
are main's own and the same in both arms.

| procedural 32 regions x 10 civs | 42-61 off | 42-61 on |
| --- | --- | --- |
| gate; comparator | PASS; - | PASS; NO REGRESSION |
| regression (adjudication; failed checks) | PASS (strict); - | PASS (strict); - |
| needs: net; lower bound; seeds (needed) | 0.165; 0.119; 17 (12) | 0.204; 0.121; 16 (12) |
| cohort (seeds; median effect); community; era (inflections; silent) | 20; 0.90; 20; 20; 0 | 20; 0.89; 20; 20; 0 |
| arcs (status; three types; families) | FAIL; 18; 6 | FAIL; 19; 6 |
| artifacts (status; per civ per 100; loss) | PASS; 2.69; 3.7% | PASS; 2.83; 4.6% |
| satisfaction mean; latest | 0.572; 0.579 | 0.568; 0.580 |
| migration; rebellion per agent-turn | 0.0769; 0.0342 | 0.0758; 0.0292 |
| all founders survive; extinct worlds | 0.200; 0 | 0.200; 0 |
| final population min / median / max | 504 / 619.5 / 871 | 467 / 620 / 897 |

**Satisfaction.** Switched on, latest satisfaction on 42-61 reads 0.614
against 0.621 (62-81: 0.617 against 0.626). Both stay under the 0.65
ceiling, and the comparator calls it no regression. Ablations on 42-61,
from the same commit with one part removed by a probe-only hook (never
committed), trace it to the learning pull. Without the pull latest
satisfaction reads 0.621, without the technique effects 0.619, and
without upkeep 0.612. Every ablation passes, with no regression. On the
full gate (below) latest satisfaction is 0.626 in both arms.

### Full gates

Template, 200 seeds x 500 turns, `03a406a`, `--scholarship
--require-strict-regression --parallel 2`, against main's newest template
full report:

| | main (switch absent) | branch, `--scholarship` |
| --- | --- | --- |
| gate; comparator | PASS; - | PASS; NO REGRESSION |
| regression (adjudication; failed checks) | PASS (strict); - | PASS (strict); - |
| needs: net; lower bound; seeds (needed) | 0.212; 0.193; 174 (120) | 0.225; 0.206; 181 (120) |
| needs binding: net; lower bound | 0.195; 0.170 | 0.211; 0.184 |
| cohort (seeds; median effect); community; era (inflections; silent) | 200; 1.57; 200; 200; 0 | 200; 1.55; 200; 200; 0 |
| arcs (status; three types; families) | PASS; 163; 6 | PASS; 165; 6 |
| artifacts (status; per civ per 100; loss) | PASS; 1.69; 6.0% | PASS; 1.66; 5.6% |
| satisfaction mean; latest | 0.615; 0.626 | 0.615; 0.626 |
| migration; rebellion per agent-turn | 0.0635; 0.0330 | 0.0653; 0.0342 |
| all founders survive; extinct worlds | 0.175; 0 | 0.160; 0 |
| final population min / median / max | 23 / 180 / 307 | 58 / 184 / 306 |
| era collapses (by the civ's signals / by crises only) | 4,509 (2,755 / 1,754) | 4,487 (2,744 / 1,743) |

PROCEDURAL_FULL

What the seats did over the 200 template worlds (per run):

| | Per run |
| --- | ---: |
| seats founded (academies / temple schools / libraries) | 16.3 (3.3 / 10.1 / 2.8) |
| living at a time (mean) | 2.9 |
| rises / declines / strikes | 14.5 / 6.2 / 9.6 |
| falls (patronage / famine / persecution / sack) | 12.6 (6.6 / 3.3 / 2.2 / 0.5) |
| flights to a refuge | 11.9 |
| techniques carried to a refuge / taken up by a civ through `scholars` | 6.5 / 0.27 |
| practices cut 30% where a seat fell | 49.3 |
| agent migrations led by the learning pull | 210 (in 197 worlds) |
| upkeep / founding and rise fees paid (treasury, prestige, purse units) | 825 / 650 |

## Feature-off identity

`scripts/turn_speed_identity.py`, the nine-case matrix of PR #44: template
seeds 42 and 7 with agents off (300 turns) and hybrid (200 turns, with the
validation sidecar), seed 1234 hybrid, procedural 48 x 10 hybrid and off,
and the scaled worlds at about 22k and 52k agents. Every output file is
compared byte for byte (the bundle without `metadata.generated_at`).

| Base | Branch | Result |
| --- | --- | --- |
| `fc01d6e` export, its own native build (`a6d0de13...726d31`) | `cd0ccfd` export (the head's simulation and Rust source; later commits change scripts and docs only), branch build (`5a9619cd...0262c`), no flags | 9 cases, 395 files, **0 differences** |
| same | same, `--no-scholarship` | 9 cases, 395 files, **0 differences** |

An earlier run of the same matrix, from the working tree between
`9985b1a` and `21a2b51`, gave the same result. The branch's Rust (the learning driver and two
optional columns) therefore changes nothing while the columns are absent.
Old saves load with `scholarship` None, and a resumed world keeps its
saved setting (`test_switch_dormancy_and_old_saves`,
`test_new_worlds_follow_the_default_and_resume_keeps_the_saved_setting`).

**Resume with the switch on**
(`test_wave3_combined.py::test_save_load_resume_identity_with_scholarship_and_everything_on`).
The world has every Wave 3-7 system, guilds and cities on. It is
advanced until seats, guilds and cities are all live (at least 30 turns,
with a seat fallen and a refuge taken), with a knowledge carry pending
between Phase 10 and Phase 4. It is then saved, loaded and run 15 more
turns beside the unsaved world. Each turn the `seat_pull` and
`seat_flight` columns match, the carries match, and at the end the two
world dumps are identical.

## Tick time

TBD

## Bundle size

The bundle-size guard world (`tests/test_bundle.py::TestBundleSize`: seed 1,
500 turns, 10 regions, 5 civs, agents off; v6 codec; limit 10.5 MB, MB =
2^20 bytes):

| Guard world | switch off | `--scholarship` |
| --- | ---: | ---: |
| native | 8.643 MB | 8.334 MB |
| no-Rust | 7.874 MB | 7.397 MB |

The `history[n].scholarship` field is 0.46 MB of raw JSON over the run
(living seats only, fallen ones counted). The switched-on bundle is smaller
because the history differs, not because the field is free.

## Narration

- **Events.** Seven types (`seat_founded`, `seat_rose`, `seat_declined`,
  `seat_fell`, `scholars_fled`, `seat_patron`, `seat_master`), each with a
  readable line (`curator.event_label`). Founding, rise, decline, fall and
  flight are scored by importance (3-6; a flight into another realm 5).
  A new patron and a great scholar teaching are routine
  (`narration_context.ROUTINE_TYPES`). Falls and declines cite their cause
  events, so the causal context reaches the occupation, famine report or
  persecution behind them.
- **Standing state.** `narration_context.seat_lines` names the living seats
  in the moment's regions or its civs' lands: "Seat of learning: The
  Academy of Amber Valley (great academy in Amber Valley under Kethani
  Empire, kept by its ruler), 10 scholars, 1 great scholar teaching,
  refugees from a fallen seat among them". At most two per moment: the
  moment's own regions first, then by level and scholars.
- **Migration.** `DRIVER_WORDS["learning"]` = "a seat of learning"; a mass
  migration it leads reads "{count} {occupation} left X for the seat of
  learning in Y" (`agent_bridge.MASS_MIGRATION_BY_DRIVER`).
- **Coverage.** Checked against the coverage table of
  [narration-coverage.md](narration-coverage.md#5-coverage-table) with
  `scripts/narration_coverage.py`. The table's seat rows come from the
  seed 42 run above (12 foundings, 15 rises, 10 declines, 8 falls, 8
  flights, 5 great scholars; 22 of these listed among the 50 curated
  moments). 17 of the 50 prompts carry a seat line.

## Tests

TBD

## Verification

TBD

## Open items

TBD
