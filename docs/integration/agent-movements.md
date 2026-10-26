# Movements grounded in people (`--agent-movements`)

Two slices. Slice 1, branch `feat/agent-movements` (PR #31, from `ec229b5`):
members, creeds, founding, recruitment, demands, crackdowns, risings,
schisms and secession ([below](#slice-1-result)). Slice 2, branch
`feat/movements-2` from `main` `ea08126`, merged with `main` after bundle
version 6 (PR #35) and needs calibration (PR #36), without rebase: lasting
reforms that governance institutions carry and rulers repeal, restoration
movements, leaders promoted from the members, the viewer's Movements tab,
and the grievance thresholds recalibrated for the corrected needs.

Code: `src/chronicler/agent_movements.py` (decisions),
`src/chronicler/agent_movements_state.py` (persisted state),
`chronicler-agents/src/movements.rs` (membership, spread, the reform credit),
`chronicler-agents/src/ffi/mod.rs` (`set_movement_reforms`,
`queue_movement_leaders`), `politics.transfer_regions_to_new_civ`
(secession), `viewer/src/components/systems/MovementsPanel.tsx`,
`viewer/src/lib/movements.ts`; scripts `agent_movements_report.py`,
`agent_movements_identity.py`, `agent_movements_probe.py` (distributions),
`build_movements_fixture.py` (the viewer fixture).

**Status.** On by default for new worlds since slice 2
(`DEFAULT_ENABLED_FOR_NEW_WORLDS = True`; `--no-agent-movements` opts out;
saved worlds keep their setting). The full gate with the switch on passes
strict with no regression against the needs-calibration full gate
([Gates](#gates)). With the switch off every output is byte-identical to the
base ([Identity](#feature-off-identity)).

## Founders at founding, no empty movements

Branch `fix/movements-narration-polish` from `main` `2dd47d4`. A viewer
screenshot of the procedural 48 x 10 seed-7 run (400 hybrid turns, all
defaults) showed "the Ploughmen's League of Yajak Downs (347)" living at
turn 348 with 0 members and 0% strength, though its founding said "8 of 18
people there want relief from hunger and dues".

**Cause.** Not the viewer, which reads `members` as recorded. A movement
was founded in Phase 10, after the turn's agent tick, and its founders were
seeded by the next tick (the table's founding one-shot); a snapshot of turn
T + 1 holds the state after turn T, so every movement stood in its first
snapshot with 0 members, strength 0 and no stronghold. The founders are 15%
of the region's adults (at least 3), the most aggrieved first, not the
aggrieved the founding counts: the League seeded 3 of the 8, never grew and
faded at turn 357. And a movement whose members lapsed, died or left stood
living with none until its fade count (fewer than 3 for 5 turns) ran out.

Zero-member living snapshots on `main` (one snapshot a turn):

| | movements | living snapshots | at 0 members | first snapshot | later: snapshots (stretches; mean, max) |
| --- | ---: | ---: | ---: | ---: | --- |
| narration runs (template 42 500, procedural 7 400, template 1234 300) | 99 | 2,100 | 121 (5.8%) | 99 (all) | 22 (12; 1.8, 4), each ended by fading |
| subsets 42-61 and 62-81 (200 turns) | 359 | 7,395 | 427 (5.8%) | 359 (all) | 68 (40; 1.7, 4), each ended by fading |

Every movement had members by its second snapshot.

**Fix.**

- `movements.rs` `seed_founding` and `AgentSimulator.found_movement`
  enrol the founders when Python founds the movement, on the pool the
  end-of-tick census counted: the founder, then `FOUND_SHARE` of the
  region's adults by `founding_score` and agent id, as the next tick did; no
  draw. `_seed_founders` sets members, regions, strength and stronghold, so
  the snapshot after the founding turn shows them. A founding nobody can
  join (every aggrieved there already in a movement) is not made, for census
  and guild foundings alike.
- A movement observed with no member after its founding turn ends at once
  (`_fade`: won when satisfied, broken when suppressed, else faded).
- Founders not enrolled at founding (a save from before) are still seeded
  by the next tick's one-shot (`peak_members == 0`); resume seeds re-seed
  the others. `send_to_native` requires `found_movement`.

After: no living movement at 0 members in the narration runs (104
movements, 2,298 snapshots), the subsets (359, 7,147) or the procedural
seed-7 run (74, 1,643).

**Gates** (hybrid, `PYTHONHASHSEED=0`, Linux, Python 3.13; head `022deb2`
with a fresh release extension `4e2f699d...a328e`, base `main` `2dd47d4`
with `5ede10a9...8b07d6`, compiled `AgentSimulator`, `EcologySimulator`,
`PoliticsSimulator` verified). Subsets (`--profile subset`, 20 seeds x 200
turns, `--parallel 1`, compared with `--baseline-report` the base run):

| | `main` 42-61 | head 42-61 | `main` 62-81 | head 62-81 |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS | **PASS; NO REGRESSION** | PASS | **PASS; NO REGRESSION** |
| needs: net; lower bound; seeds (12 needed) | 0.136; 0.035; 14 | 0.215; 0.121; 17 | 0.185; 0.080; 16 | 0.151; 0.067; 14 |
| cohort; community; era (seeds) | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 |
| regression (informational) | FAIL (civ_survival) | FAIL (civ_survival) | FAIL (civ_survival) | FAIL (rebellion, civ_survival) |
| satisfaction; latest | 0.606; 0.621 | 0.607; 0.622 | 0.617; 0.621 | 0.617; 0.624 |
| migration; rebellion | 0.0693; 0.0439 | 0.0682; 0.0349 | 0.0632; 0.0218 | 0.0617; 0.0174 |
| final population min / median / max; extinct | 86 / 190 / 292; 0 | 108 / 186 / 279; 0 | 128 / 197 / 236; 0 | 142 / 187 / 238; 0 |

Full gate (`--profile full`, 200 x 500, `--parallel 3`) against the guilds
full gate (the merged head `6431c35`, whose simulation `main` carries):

| | guilds, `main` | **head `022deb2`** |
| --- | --- | --- |
| gate; comparator; adjudication | PASS; -; strict | **PASS; NO REGRESSION; strict** |
| needs, all pairs: net; lower bound; seeds with C > D | 0.214; 0.196; 172 | 0.210; 0.191; 173 |
| needs, binding pairs: net; lower bound; informative; seeds positive | 0.202; 0.178; 5,094; 157 | 0.195; 0.170; 4,986; 156 |
| community; cohort; era (silent collapses) | 200; 200; 200 (0) | 200; 200; 200 (0) |
| arcs (three types); artifacts (creation; loss) | 159; 1.71; 5.8% | 163; 1.71; 5.8% |
| satisfaction mean; latest (ceiling 0.65) | 0.617; 0.627 | 0.615; 0.626 |
| migration per agent-turn (strict floor 0.05) | 0.0644 | 0.0634 |
| rebellion per agent-turn (0.02-0.08) | 0.0368 | 0.0329 |
| final population min / median / max; extinct worlds | 63 / 183 / 304; 0 | 23 / 179 / 307; 0 |
| worlds whose founders all survive | 18% | 18% |
| per world: movements founded; significant; demands; reforms; risings | 18.2; 3.0; 10.96; 4.90; 0.91 | 17.6; 3.0; 10.97; 4.72; 0.91 |
| living movement snapshots at 0 members | not measured | 0 of 82,037 (3,620 movements) |

The comparator reports no regression reason, no new required failure and
no strict-regression downgrade. Rebellion per agent-turn is lower in all
three gates (-11% in the full gate, inside its band) while risings, demands
and peak members are unchanged; membership feeds no agent decision outside
the movement pass, so it comes through the worlds' changed trajectories.
Run with one part at a time on 42-61, ending a movement at zero members
leaves every validation figure equal to `main`'s (its 27 later empty
snapshots end, and the worlds otherwise run alike); enrolling founders at
founding alone gives the head's figures (rebellion 0.0439 -> 0.0349). The
founders are picked from the end-of-tick pool the census counted rather
than in the next tick's pass and are members a tick sooner, so each world
diverges from its first founding on; no single mechanism was isolated. One
world (seed 232) ends at 23 people (73 before); the next lowest are 52 and
73.

## Slice 2: lasting reforms, repeal, restoration, leaders

### Lasting reforms

A granted demand (or a concession after a rising) still gives the members
slice 1's one-off relief, and it now enacts a lasting reform
(`MovementState.reforms`, `Reform`; kinds `REFORM_NAMES`, append-only):

| creed | reform | covers | governance institution | city | opposed by (without an institution) |
| --- | --- | --- | --- | --- | --- |
| commons | poor relief | the realm | Commons Management, enacted or upheld | - | merchant faction; upkeep 0.75 treasury per region a turn (`keep`), ended after 3 unpaid turns |
| liberty | home rule | the stronghold (later grants add regions) | Written Law, enacted or upheld | the realm's city there gains one charter level (self-government at most, at the cities' rank floors) | military faction |
| sect | toleration of the members' faith, or the reform of the church when that is the ruler's own faith | the faith's believers in the realm | none; an active Holy Inquisition is abolished by the grant | - | clergy faction |

- **Institutions.** With governance on, the grant appends the institution to
  the ruler's `CivGovernance.institutions` (enacted that turn, legitimacy 1,
  the runtime's enforcement cost; logged as enacted), effective N+1: the
  next Phase 2 funds it and the next late Phase 10 resolves it like any
  other. It has its usual effects (Commons Management: action weights and
  soil recovery; Written Law: stability and a governing-cost rebate). No
  institution when the realm already holds three, or for toleration; the
  reform then stands alone. A reform in force of the same kind is extended
  instead (home rule adds the region).
- **Grievance.** Rust reads the creed need of an agent the reform covers as
  `need + 0.3 (1 - need)` (`REFORM_NEED_CREDIT`) for grievance, commitment,
  founding seeds and recruitment: material 0.40 reads 0.58 (no longer
  aggrieved), 0.20 reads 0.44 (still aggrieved). The needs themselves are
  untouched. Python sends the reforms in force every tick
  (`set_movement_reforms`: creed, civ, region or the realm, faith or every
  believer); Rust derives the covered regions from the controllers in the
  pass and the census uses the same cover. Standing state, rebuilt every
  tick from the persisted reforms.

### Repeal and restoration

Checked every Phase 10 before the movements, in this order:

| cause | `REPEAL_NAMES` | rule |
| --- | --- | --- |
| realm gone; home rule's regions lost | lapsed | no grievance follows |
| the institution collapsed (unpaid) or was forced out by its opposing faction | neglect / opposition | read from the governance institution log |
| a Holy Inquisition is active again | inquisition | toleration only |
| a new reign | ruler | once per reign: chance 0.25 for an aggressive, zealous, stubborn or bold ruler, else 0.03; takes the institution the grant enacted |
| without an institution: the opposing faction above 0.40 | opposition | chance 0.03 a turn |
| without an institution: relief unpaid 3 turns | fiscal | |

A repeal (not a lapse) is remembered against its realm for 60 turns. A
region it covered (relief: any of the realm's; home rule: its regions;
toleration: where the faith is the majority) then founds a movement of the
creed with twice the chance, even inside the creed's 20-turn cooldown, while
no other movement seeks the same restoration; the movement's demand is "the
restoration of" the reform and its founding cites the repeal. Its grant
enacts a new reform that `restores` the old one (counter `restored`). A home
rule repeal revokes the charter level it gave.

### Leaders

A movement that has made a demand or risen, has at least 8 members and no
living leader raises one: its boldest member in the stronghold (ties by
agent id) whose civ still holds land. A great person already is one; anyone
else is queued for a native promotion (`queue_movement_leaders`, trigger 5,
a prophet for a sect or a civilian, a general for a soldier). For leaders
the registry's caps (10 per civ, 50 in all) count living named characters
only: the registry keeps the dead, so its own check closes for good after
fifty promotions in a long run. Other promotions are unchanged. The person
appears in the next turn's promotions (with an agenda when agendas are on)
and is installed then (`movement_leader` event, a deed). A leader raises
the movement's appeal by half, a crackdown in the stronghold usually kills
them first, and their death makes a martyr; a secession crowns a living
leader as the new state's ruler (fate `ascended`).

### Viewer

A Movements tab when a snapshot records `agent_movements`: tiles (living
movements, members, reforms in force, founded and ended so far), each
movement's stage over time, living movements by creed, the scrubbed turn's
movements (creed, ruler, stage, members, strength, stronghold, leader,
martyrs) and lasting reforms (realm, since, institution, the movement that
won it), running totals, one movement's members and recorded moments with
its reform's repeal, and the movement and reform events, which pin in the
inspector. Snapshot rows gain optional `leader`, `restores` and a
`reforms` list (id, kind, civ, since, movement; regions, faith, church,
institution when set); `world_state.agent_movements` carries the records.
Live mode passes the field through. Fixture
`viewer/src/__fixtures__/movements_bundle.json` (115 KB): template seed 48,
500 hybrid turns on this branch, every fifth snapshot.

### Calibration after needs calibration

Needs calibration made material bind in dearth and famine and autonomy under
persecution, martial law and conquest; foreign rule settles at 0.61, the fed
poorest at 0.56, a dearth's median at 0.44. Movement grievance thresholds
were set for the old needs. `scripts/agent_movements_probe.py --grid`
samples every agent's needs every 10 turns and scores, per region with 5+
adults, whether a creed reaches the founding share (20%, 5 adults) under a
grid of thresholds and under each bad condition: an open famine episode,
occupation or conquest within 20 turns, persecution, a majority faith not the
ruler's. Template seeds 42-51, 500 hybrid turns, needs calibration with the
slice 1 thresholds. Region samples there: famine 43%, foreign rule 0.8%,
persecution 9%, minority faith 49%, none of these 28%.

Founding share reached (share of region samples), satisfaction below 0.45:

| creed, need threshold | all | famine | foreign | persecuted | minority faith | none of these |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| commons, material 0.55 (slice 1) | 17.6% | 28.5% | 14.3% | 22.8% | 17.9% | 1.5% |
| commons, material 0.45 (slice 2) | 11.0% | 18.2% | 4.8% | 13.8% | 11.0% | 0% |
| liberty, autonomy 0.60 (slice 1) | 19.5% | 26.2% | 33.3% | 33.1% | 20.7% | 7.0% |
| liberty, autonomy 0.50 (slice 2) | 7.6% | 11.3% | 19.0% | 18.3% | 8.6% | 0.9% |
| sect, spiritual 0.45 (both) | 7.5% | 9.3% | 14.3% | 12.9% | 8.3% | 4.4% |

Material 0.55 -> 0.45 and autonomy 0.60 -> 0.50 (both above the behaviour
thresholds, 0.30 and 0.35) take grievance out of good conditions and keep
it where conditions are bad; spiritual is unchanged by needs calibration and
stays. Repeal was made gentler at the same time (a new ruler 0.05 -> 0.03,
harsh 0.4 -> 0.25, the opposing faction 0.05 -> 0.03): median reform life
45 -> 61 turns.

Distributions per 500-turn world (template 42-51, hybrid; "significant": a
demand made and at least 10 members at the peak):

| | slice 1, before needs calibration | slice 2, before | slice 2, needs calibration, slice 1 thresholds | slice 2, shipped |
| --- | ---: | ---: | ---: | ---: |
| movements founded | 11.9 | 11.8 | 26.9 | 20.5 |
| significant (range over worlds) | 1.6 (0-3) | 1.0 (0-4) | 5.2 (3-8) | 3.0 (1-5) |
| commons / liberty / sect founded | 3.6 / 1.6 / 6.7 | 3.6 / 1.7 / 6.5 | 13.2 / 9.9 / 3.8 | 8.7 / 5.1 / 6.7 |
| living movement-turns per civ-turn | 0.23 | 0.21 | 0.47 | 0.37 |
| region samples at the founding share: commons / liberty / sect | 4.0% / 2.5% / 9.8% | 4.4% / 2.3% / 8.2% | 16.2% / 17.5% / 7.3% | 10.5% / 9.3% / 9.2% |
| foundings in a region with none of the bad conditions: commons / liberty / sect | - | - | 0% / 3.0% / 7.9% | 0% / 0% / 4.5% |
| demands / grants / refusals / crackdowns | 6.7 / 2.5 / 2.5 / 1.7 | 5.5 / 2.4 / 2.1 / 1.0 | 20.5 / 8.1 / 7.7 / 4.7 | 13.8 / 6.3 / 4.9 / 2.6 |
| risings; schisms; secessions | 0.5; 0.9; 0 | 0.5; 0.6; 0 | 1.7; 0.3; 0 | 0.8; 0.5; 0 |
| lasting reforms enacted / repealed / restored / in force at turn 500 | - | 2.6 / 1.5 / 0.2 / 0.7 | 8.4 / 6.9 / 1.2 / 1.2 | 6.3 / 4.7 / 0.7 / 1.2 |
| leaders raised | - | 0.7 | 4.5 | 3.4 |

So needs calibration more than doubled founding with the old thresholds:
0.47 living movements per civ-turn, against 0.21-0.23 before. Shipped: three
significant movements a world (one to five), founded where conditions are
bad: every commons founding in a famine region (44% of region samples),
liberty foundings under persecution at 2.4 times its base rate (26% against
11%), no commons or liberty founding in a region with none of the four
conditions (26% of region samples). Shipped reforms (63): 27 poor relief,
9 home rule, 22 toleration, 5 church reforms; of the 36 relief and home
rule reforms 11 carried an institution (7 Commons Management, 4 Written
Law) and 25 found three institutions in place; median life 61 turns
(quartiles 22 and 167); repealed by a new ruler 28, by opposition 19,
lapsed 4, in force at turn 500 12. The first column is slice 1 as merged
(`ea08126`), the second slice 2 before its recalibration.

### A 500-turn example

`scripts/agent_movements_report.py RUN_DIR --reforms` prints each movement's
record and the reform it won with the event text the simulation wrote.
Template world, seed 48, 500 turns, hybrid, `--agent-movements`, every other
system at its default (`--simulate-only`, `PYTHONHASHSEED=0`); spread lines
left out:

```
the Penitents of Crystalfen Marsh (sect), founded turn 56 in Crystalfen Marsh against Selurian
Republic, led by King Grammaris; peak 13 members, 1 demands, 1 martyrs; ended won turn 79
    56: founded: In Crystalfen Marsh, the discontented found the Penitents of Crystalfen Marsh:
         7 of 23 people there want freedom to worship in the Faith of Selurian Republic (Reformed 2)
    61: demand: the Penitents of Crystalfen Marsh, 7 strong (12% of the people of Selurian
         Republic), demands freedom to worship in the Faith of Selurian Republic (Reformed 2)
    61: refused: Selurian Republic refuses the Penitents of Crystalfen Marsh
    65: leader: King Grammaris rises to lead the Penitents of Crystalfen Marsh in Crystalfen Marsh
    65: rising: the Penitents of Crystalfen Marsh rises against Selurian Republic in Crystalfen
         Marsh (6 members)
    66: concession: After the rising, Selurian Republic tolerates the Penitents of Crystalfen
         Marsh and its worship; the Faith of Selurian Republic (Reformed 2) is tolerated in the
         realm and the Holy Inquisition is abolished
    71: martyr: The death of King Grammaris makes a martyr for the Penitents of Crystalfen Marsh
    79: ended: the Penitents of Crystalfen Marsh disbands, its demand met
  reform 3: the toleration of the Faith of Selurian Republic (Reformed 2) in Selurian Republic,
  enacted turn 66; in force
```

A sect of a minority faith, refused, raises a leader from its boldest
member (a promoted prophet; the name generator's title is not a rank),
rises the same turn and wins toleration in a concession, which also ends
the realm's Holy Inquisition. The movement disbands, its demand met; the
toleration is still in force at turn 500, 434 turns later, through every
later reign of the Selurian Republic: its believers read their spiritual
need with the reform's credit for the rest of the run.

The same realm's poor relief shows repeal and restoration:

```
    26: reform: Selurian Republic grants the Ploughmen's League of Ashara Desert relief: remitted
         dues and grain from the stores (12 from the treasury); poor relief becomes law under
         Commons Management
    71: reform_repealed: Elder Harbright of Selurian Republic repeals the poor relief
    72: founded: In Crystalfen Marsh, the discontented found the Levellers of Crystalfen Marsh:
         18 of 29 people there want the restoration of the poor relief
    77: refused: Selurian Republic refuses the Levellers of Crystalfen Marsh
    80: leader: Chancellor Mongke rises to lead the Levellers of Crystalfen Marsh in Crystalfen Marsh
    89: reform: Selurian Republic grants the Levellers of Crystalfen Marsh relief: remitted dues
         and grain from the stores (14 from the treasury); the poor relief is restored
   120: reform_repealed: The merchant faction of Selurian Republic has the poor relief repealed
   134: founded: In Crystalfen Marsh, the discontented found the Commons of Crystalfen Marsh:
         11 of 20 people there want the restoration of the poor relief
   139: reform: Selurian Republic grants the Commons of Crystalfen Marsh relief: remitted dues
         and grain from the stores (12 from the treasury); the poor relief is restored
   161: reform_repealed: The merchant faction of Selurian Republic has the poor relief repealed
```

A new ruler's repeal takes Commons Management with it (turn 71); the
restoration movement is founded the next turn, its founding citing the
repeal. The restored relief holds no institution (the realm holds three)
and the merchant faction, above 0.40, has it repealed twice.

### Gates

Every gate is hybrid, `PYTHONHASHSEED=0`, Linux, Python 3.13, with a native
extension built fresh from the gated source (`maturin develop --release
--locked`; compiled `AgentSimulator`, `EcologySimulator` and
`PoliticsSimulator` verified). Movement counts come from the runs' bundles.

**Full gate** (`--profile full`, 200 seeds x 500 turns, `--parallel 3`,
`--agent-movements`, 2,551 s on a shared machine) on `36c5617`, tree `669efe3` (run on
`7315a81`, the same commit on a local preview merge of PR #36's head, same tree; extension
SHA-256 `028c1fd1...248fc52a`), compared with the needs-calibration full
gate (`main` after PR #36; the same seeds and profile):

| | needs calibration (movements off) | `--agent-movements` |
| --- | ---: | ---: |
| gate / comparator | PASS / - | PASS / NO REGRESSION |
| regression adjudication | strict | strict |
| migration per agent-turn (strict floor 0.05) | 0.0626 | 0.0629 |
| rebellion per agent-turn | 0.0385 | 0.0409 |
| satisfaction mean / latest (ceiling 0.65) | 0.614 / 0.622 | 0.616 / 0.631 |
| needs: seeds with the expected sign; pooled lower bound | 190; 0.195 | 188; 0.192 |
| cohort (seeds; median effect) | 200; 1.73 | 200; 1.58 |
| era (seeds with inflections; silent collapses) | 200; 1 | 200; 0 |
| arcs (seeds with three types) | 165 | 164 |
| artifacts (creation per civ per 100 turns; loss) | 1.47; 6.1% | 1.62; 6.6% |
| extinct worlds; worlds whose founders all survive | 0; 17.5% | 0; 12.0% |
| final population min / median / max | 46 / 177 / 277 | 40 / 177 / 342 |
| movements founded (per world); significant | - | 4,323 (21.6); 678 (3.4) |
| demands / grants / refusals / crackdowns | - | 2,578 / 1,105 / 901 / 572 |
| martyrs | - | 1,695 |
| risings: concession / crushed / secession | - | 191: 95 / 88 / 8 |
| movement schisms; all schisms per world | - | 111; 12.6 |
| secessions per world (all) | - | 0.125 |
| lasting reforms enacted / extended / repealed / lapsed / restored | - | 1,138 / 62 / 850 / 47 / 163 |
| repeals: ruler / opposition / inquisition / neglect / fiscal | - | 493 / 340 / 11 / 4 / 2 |
| reforms in force at turn 500; city charters raised | - | 241; 88 |
| leaders raised | - | 667 |

The comparator reports no regression reason, no new required failure, no
oracle method or status change and no strict-regression downgrade. Rebellion
rises 0.0024 (risings add rebels in their strongholds; the band is
0.02-0.08); the needs oracle loses two seeds and 0.003 of its lower bound,
against 2-4 seeds per subset in slice 1 at 200 turns. The first movement
secessions appear: 8 in 200 worlds (liberty risings against rulers under
30 stability). The gated configuration is now the default
([below](#default-on)).

**Subset gates** (`--profile subset`, 20 seeds x 200 turns, `--parallel 2`;
the 62-81 on arm `--parallel 3`), `--no-agent-movements` against
`--agent-movements` on the final head, compared with `validation_compare`
(the off arms are identical to the base, below). The same reports came from
`7315a81` (`36c5617`'s tree) before the flip:

| | 42-61 off | 42-61 on | 62-81 off | 62-81 on |
| --- | ---: | ---: | ---: | ---: |
| gate / comparator | PASS / - | PASS / NO REGRESSION | PASS / - | PASS / NO REGRESSION |
| regression adjudication (informational in the subset) | strict | strict | fail (civ_survival) | fail (civ_survival) |
| migration per agent-turn | 0.0705 | 0.0689 | 0.0614 | 0.0621 |
| rebellion per agent-turn | 0.0521 | 0.0489 | 0.0229 | 0.0252 |
| satisfaction mean / latest | 0.594 / 0.614 | 0.599 / 0.619 | 0.606 / 0.619 | 0.610 / 0.625 |
| needs: seeds with the expected sign; pooled lower bound | 18; 0.170 | 15; 0.075 | 14; 0.097 | 15; 0.110 |
| schisms; secessions per world (all) | 12.00; 0.05 | 12.10; 0.05 | 12.00; 0.05 | 12.35; 0.05 |
| extinct worlds; polities alive at turn 200 | 0; 3.05 | 0; 3.10 | 0; 3.50 | 0; 3.60 |
| movements founded; significant | - | 229; 34 | - | 224; 29 |
| demands / grants / refusals / crackdowns | - | 139 / 58 / 58 / 23 | - | 127 / 49 / 44 / 34 |
| risings: concession / crushed / secession | - | 10: 7 / 3 / 0 | - | 7: 3 / 4 / 0 |
| lasting reforms enacted / repealed / restored / in force at turn 200 | - | 63 / 34 / 5 / 26 | - | 51 / 25 / 2 / 26 |
| leaders raised; martyrs | - | 32; 104 | - | 24; 110 |

The needs oracle's lower bound moves -0.095 on 42-61 and +0.013 on 62-81;
the full gate reads it on 200 seeds of 500 turns (above).

### Default on

`DEFAULT_ENABLED_FOR_NEW_WORLDS = True` in a separate commit (`cb4cefa`), as
[defaults-wave8.md](defaults-wave8.md) did: CLI help ("default on for new
worlds; --no-agent-movements opts out; saved on resume"), the live server
comment, `test_new_worlds_default_on_and_resume_keeps_saved_setting` (a fresh
world has movements, `--no-agent-movements` leaves them out, an on world
stays on and an off world stays off on resume), the mock-bridge CLI tests
(`tests/test_main.py`, a MagicMock simulator) pass the switch off
explicitly, and `scripts/benchmark_headless.run` pins `agent_movements=False`
so the frozen performance oracles replay the same worlds. Worlds from
`generate_world`, resumed and forked worlds keep their own setting.
`scripts/m53b_run_validation.py` already forwards both forms.

### Feature-off identity

Base: `e1b6a13` (PR #36's head; `main` `b5d41af` has the same tree)
exported as a source tree
and its extension built from that tree (SHA-256 `0cb2948c...7cdb8d`, the one
needs calibration recorded), `PYTHONPATH` on the export. Branch: the
worktree at the final head and its extension. Same interpreter,
`PYTHONHASHSEED=0`, `scripts/agent_movements_identity.py compare`:

| Comparison | Runs | Result |
| --- | --- | --- |
| base (no flags; movements off there) against the branch `--no-agent-movements` | template seeds 42 / 7 / 1234, `--agents off` 300 turns and hybrid 200; procedural 48 regions x 10 civs, seed 7, off 200 and hybrid 120 | 88 files, **0 differences** |
| the branch with no flags against `--agent-movements` | template 42 hybrid 200; procedural 48 x 10 seed 7 off 150 | 25 files, **0 differences**: the defaults are the gated configuration |
| an old save resumed: base save at turn 30 (agents off, no flags), resumed to turn 60 by the base and by the branch, no flags | template 42; procedural 48 x 10 seed 13 | 6 files, **0 differences**; the resumed worlds carry no movement field |
| subset gate 42-61 x 200 hybrid: base against the branch `--no-agent-movements` | 20 seeds | 2,201 run files, **0 differences**; validation report, gate decision, gate summary and summary identical once the batch path is normalised |

With the switch off the native pass never runs, `get_promotions` takes its
old path (no queued leader) and no reform table is sent. In the suite,
`test_feature_off_never_runs_movement_code`, the frozen exact-trajectory
oracles and the benchmark pin cover the same ground.

### Tick time

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, starting targets
18,800 and 43,700 (about 23,000 and 51,600 alive when measured), 30 warm-up
turns and 8 timed turns, two repeats, one child at a time, release builds;
base the `e1b6a13` export with its extension. The 4-core machine was shared
(other agents' gates and test runs, load average 4-6), so wall times
scatter; CPU is steadier. Per run, wall / process CPU, in ms:

| agents | | base `e1b6a13` | branch, `--no-agent-movements` | branch, `--agent-movements` |
| ---: | --- | ---: | ---: | ---: |
| ~23,000 | Rust tick | 153, 183 / 298, 292 | 142, 122 / 290, 292 | 186, 180 / 318, 294 |
| | whole turn | 265, 284 / 430, 411 | 230, 198 / 393, 390 | 289, 261 / 444, 375 |
| ~51,600 | Rust tick | 1,028, 690 / 1,688, 1,701 | 768, 797 / 1,628, 1,618 | 818, 619 / 1,663, 1,579 |
| | whole turn | 1,324, 917 / 2,136, 2,227 | 957, 1,041 / 2,043, 2,084 | 1,041, 860 / 1,990, 2,102 |

A kept rerun of the switched-on arm: the timed turns carried one or two
living movements of 168-297 members and no reform yet (they are founded
from turn 10; reforms come later). Every arm is within the run-to-run
spread (the switch-off branch runs the base's path). Slice 2 adds per agent
and creed a lookup in its region's list of covering reforms (empty until a
reform is in force, then a few entries) in the census and the recruitment
loop; leader promotion is one queued id per movement at most.

### Bundle size

The guard world (`tests/test_bundle.py::TestBundleSize`: seed 1, 5 civs,
10 regions, 500 turns, agents off, every default) now has movements on
(nothing is founded without agents). Bundle version 6, bytes of
`chronicle_bundle.json`:

| Guard world | base `e1b6a13` | branch (movements on by default) |
| --- | ---: | ---: |
| native, agents off | 8,276,564 (7.893 MB) | 8,277,349 (7.894 MB) |
| no-Rust, agents off | 9,029,934 (8.612 MB) | 9,030,719 (8.612 MB) |
| native, hybrid | 7,970,438 (7.601 MB) | 6,852,390 (6.535 MB) |

Agents off: +785 bytes, the `agent_movements` field (168 KB per history
decoded, a few hundred bytes as changes between snapshots). Hybrid: the
movements change the world's history (the field is 259 KB decoded). The
guard is 10.5 MB (MB here is 2^20 bytes); the no-Rust guard world stays at
8.61 MB.

### Tests and verification

Tests added or changed:

- `tests/test_agent_movements.py` (40 tests; offline lane chunk `systems-2`):
  a grant enacts relief with Commons Management (enacted turn, enforcement
  cost, the institution log) and a second grant extends it; the institution
  runs through the governance runtime's Phase 2 and Phase 10 for real turns;
  a reform falls with its institution (neglect, opposition); a new ruler
  repeals once per reign and takes the institution the grant enacted; relief
  without an institution pays upkeep until three unpaid turns end it, and the
  merchant faction repeals it; home rule raises the city's charter, a repeal
  revokes it, losing the region lapses it; toleration ends an Inquisition and
  falls to a new one; a church reform is named as one; a repeal founds a
  restoration movement inside the cooldown (and only then) whose grant
  restores the reform; a pressing movement queues its boldest member (a
  prophet, or a general for a soldier; none under 8 members) and installs
  the person on promotion; a secession crowns its leader;
  `test_new_worlds_default_on_and_resume_keeps_saved_setting`.
- `tests/test_wave3_combined.py`: the save/load resume identity world carries
  a lasting reform in force; the reform table is compared turn by turn and
  every byte of the world after 15 more turns.
- `tests/test_main.py`: three mock-bridge CLI tests pass the switch off.
- Rust: `movements` unit tests (the reform credit by region, creed and faith,
  the zero credit bit for bit, the census with and without reforms, covered
  agents not recruited) and `ffi` (leaders promoted once from the queue with
  trigger 5, unknown ids skipped, a registry full of the dead still admits a
  leader).
- Viewer: `lib/__tests__/movements.test.ts` (8) and three `MovementsPanel`
  tests in `SystemsPanel.test.tsx`.

Verification on the final head (Linux, Python 3.13.17, Node 22; extension
built fresh from the branch's Rust, unchanged since `36c5617`, SHA-256
`028c1fd1...248fc52a`, compiled submodule and classes verified):

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 982 passed, 0 failed, 2 ignored |
| `pytest -m "not slow" -n 2` | 6,178 passed, 3 skipped, 526 subtests |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust lane (venv without `chronicler_agents`, every test) | 5,953 passed, 228 skipped |
| `scripts/run_python_oracle_checks.py` | PASS in 84.7 s: 2,134 passed, 28 skipped; largest chunk 32.4 s of 110 s |
| Viewer `npm test` / `npm run lint` / `npm run build` | 38 files, 291 tests passed / clean / built (the existing large-chunk warning) |
| Golden and exact-trajectory fixtures | unchanged |
| Identity (switch off), resume, subset and full gates, tick time, bundle | above |

Not done: browser QA of the new tab; procedural-world distributions; the
tick benchmark with reforms in force.

## News-driven spread and the guild creed (`--guilds`)

Branch `feat/guilds` adds two things to movements behind `--guilds`
([guilds.md](guilds.md)); with the switch off neither runs and every output
is identical to the base.

**A guild creed** (`CREED_NAMES[3]`, `REFORM_NAMES[3]` guild charter):
a city's guild rises when its privileges are threatened; its people are
the city's civilian residents, recruited and released by the existing pass;
its reform is a lasting guild charter repealed and restored like the
others. Guild movements are founded by their guilds, never from the census,
and count apart from the census caps (`MAX_LIVING`, `MAX_PER_CIV`).

**Information packets as a spread channel** (roadmap item 1). Movement
foundings, risings, reforms and crackdowns become packets of a new type
(`knowledge.rs` `InfoType::MovementNews`). The agents of the event's region
observe them at the event's intensity (founding 120, rising 180, reform
220, crackdown 160 of 255), those of the adjacent regions at half of it;
they then pass on friend, kin, family, mentor and co-religionist bonds and
decay 10 a turn. News never displaces a threat, trade or religious packet,
and those packets take a news slot as if it were empty, so the four slots
hold for the other types exactly what they hold without news; the threat
warnings that drive migration are untouched.

| consumer | rule | bound |
| --- | --- | --- |
| joining (Rust recruitment) | an aggrieved agent holding news of a like movement (same creed) from another region: p x (1 + strength) for a founding, rising or reform, x (1 - 0.5 strength) for a crackdown | x2 / x0.5, under the 0.5 cap; not applied without news |
| founding (Python emergence) | the census counts the aggrieved holding inspiring news of a like movement elsewhere (`informed_*`); chance x (1 + min(1, 2 x informed / aggrieved)) | x2, under the founding cap |
| provenance (Python emergence, since `fix/movements-narration-polish`) | the census names the news most of them hold (`news_source_*`); a founding where a quarter of the aggrieved hold news of a like movement's won demand in another region cites that event as a cause | no event, no draw, no state |

Measured over 40 template worlds (seeds 42-81, 200 hybrid turns, `--guilds`
on), news on against news off (tuning `guilds.movement_news: 0`), paired by
seed; details in [guilds.md](guilds.md#news-and-movement-spread). Per
world:

| | news on | news off | difference (SE) |
| --- | ---: | ---: | ---: |
| movements founded (census creeds) | 10.65 | 10.22 | +0.42 (0.31), within noise |
| of them with news raising the chance | 1.70 | - | |
| significant | 1.62 | 1.40 | +0.23 (0.12), +16% |
| demands | 6.28 | 5.78 | +0.50 (0.37), within noise |
| reforms (grants) | 2.77 | 2.45 | +0.33 (0.26), within noise |
| risings | 0.47 | 0.35 | +0.12 (0.05), +34% |
| crackdowns | 1.32 | 1.38 | -0.05 (0.15) |
| peak members per movement | 6.80 | 6.75 | +0.04 (0.11) |
| regions reached per movement | 2.32 | 2.36 | -0.04 (0.04) |

News makes movements likelier to reach significance and to rise where a like
movement rose nearby; it does not widen a movement's own reach, since
members still do not cross borders. A first build that kept news to the
event's region and bonds changed nothing measurable; the shipped build adds
the neighbours at half intensity.

## Slice 1 result

Slice 1 as recorded on `feat/agent-movements` (`c93e87e`, `d5e3bf5`); its
grievance thresholds, defaults and roadmap have since changed (above).
Subset gates (20 seeds x 200 turns, hybrid), base `ec229b5` against the
switch on:

| | 42-61 base | 42-61 on | 62-81 base | 62-81 on | 82-101 base | 82-101 on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gate / comparator | PASS | PASS / NO REGRESSION | PASS | PASS / NO REGRESSION | PASS | PASS / NO REGRESSION |
| migration per agent-turn (strict floor 0.05) | 0.0619 | 0.0608 | 0.0548 | 0.0546 | 0.0619 | 0.0603 |
| rebellion per agent-turn | 0.0376 | 0.0350 | 0.0153 | 0.0162 | 0.0353 | 0.0319 |
| satisfaction mean / latest | 0.591 / 0.603 | 0.595 / 0.612 | 0.608 / 0.619 | 0.613 / 0.631 | 0.598 / 0.605 | 0.603 / 0.611 |
| needs (seeds with the expected sign; 12 required) | 16 | 12 | 16 | 13 | 16 | 14 |
| schisms per world (all) | 12.00 | 12.25 | 12.00 | 12.20 | 12.00 | 12.10 |
| secessions per world (all) | 0.05 | 0.05 | 0.05 | 0.05 | 0.05 | 0.00 |
| extinct worlds | 0 | 0 | 0 | 0 | 0 | 0 |
| movements founded per world | - | 7.6 | - | 7.2 | - | 7.0 |

## What exists

- **M16b ideas** (`movements.py`): every 30 turns an idea emerges from the
  civ with the highest culture and lowest stability and spreads between
  civs by contact or trade. An idea has a value affinity and per-civ variant
  counters; diverging variants record a `movement_schism` named event. No
  person belongs to an idea.
- **Faiths** (`religion.py`, M37/M38b): per-region majority belief,
  conversion signals, persecution by militant rulers (the builder owns
  `persecution_intensity` and `persecuting_faith` every turn,
  [persecution-fix-2026-10.md](persecution-fix-2026-10.md)), martyrdom boost
  from persecuted deaths, schisms when a region's minority exceeds 30%
  (`fire_schism` creates a faith and sets the region's one-turn schism
  conversion signal), reformations.
- **Factions** (`factions.py`): military, merchant, cultural and clergy
  influence, shifted by events and normalized with a floor.
- **Governance** (on by default): ruler legitimacy (M66a), whose failed
  outcomes (`CivGovernance.defeat_turns`) include revolts; PSI revolts.
- **Great persons** with a region and, in agent modes, an agent id.
- **Cities** (on by default): unrest, charters, urban revolts and free cities.
- **Agents** (Rust): beliefs, the six needs, satisfaction, loyalty, wealth,
  occupation, personality, memories (the persecution memory has rebel and
  migrate modifiers and a 25-turn half-life), bonds with sentiment,
  settlement ids, merchant trips. The needs already carry the grievances:
  famine and poverty lower material, foreign rule, displacement and
  persecution block autonomy, a minority faith or no temple lowers spiritual.

Nothing tied these together into people acting in concert.

## The slice

A **movement** is a set of agents with a shared grievance (its creed) and a
target: the ruler of the region where it was founded. It is founded where
grievances cluster and a carrier exists, grows through bonds, co-residence
and towns, spreads with migrants, bonds and merchants inside the target's
realm, and at scale presses its demand. The ruler grants, refuses or
suppresses. A refused or suppressed movement that holds a stronghold rises;
a sect breaks away from its church instead. Movements fade, win, are
crushed or dissolve. Three creeds (append-only `CREED_NAMES`):

| creed | grievance (need) | carriers | demand | escalation | ally faction |
| --- | --- | --- | --- | --- | --- |
| `commons` | material: hunger, poverty | bread and peasant leagues | relief from hunger and dues | rising: concession or crushed | cultural |
| `liberty` | autonomy: foreign rule, displacement, persecution | nativist and autonomist currents | own customs and officers | rising: secession, concession or crushed | military |
| `sect` | spiritual: minority faith, no temple | reform and millenarian sects | freedom of worship, or reform of the ruler's church | schism through `fire_schism`, else a rising | clergy |

The ally faction gains from the movement's pressure and shapes the response:
the cultural faction favours grants, the military and the clergy favour
crackdowns. Guild, craft and cross-border movements are later slices
([Roadmap](#roadmap)).

### Membership (Rust)

- `AgentPool.movement_ids: Vec<u16>`: 0 = none, otherwise the movement's
  index in `world.agent_movements.movements` + 1. At most one movement per
  agent; spawn, slot reuse and death set 0.
- The snapshot gains `movement_id` (UInt16, appended last). The Python
  contract (`bridge_contract.SNAPSHOT_SCHEMA`) has 24 fields; a capture in
  the earlier 23-field layout is still accepted, so detached snapshot
  sessions keep reading old captures.
- Persistence: the native pool is not saved (hybrid resume rebuilds it from
  region populations). Each movement saves its members by region; a resumed
  hybrid run re-seeds that many members per region on its first tick
  (`AgentSimulator.seed_movement_members`: the aggrieved first, then the
  boldest), so membership survives save/load at region resolution. With
  `--agents off` a world that carries movements keeps them at their saved
  counts and their politics run from persisted state; the resume test uses
  that mode.

### Grievance

(Slice 2 sets material 0.45 and autonomy 0.50 for the corrected needs, see
[Calibration](#calibration-after-needs-calibration), and credits agents a
lasting reform covers.)

An adult (16+) is aggrieved for a creed when its satisfaction is below 0.45
and the creed's need is below 0.55 (material), 0.60 (autonomy) or 0.45
(spiritual); intensity `g` is the mean of the two normalized deficits. The
thresholds come from a probe of the base (seeds 42 and 47, 200 turns, every
10 turns per region): 3-12% of adults per creed, 10-30% in the worst tenth
of regions. They sit above the behaviour thresholds (0.25-0.30), so
movements form before people are desperate. Members have hysteresis: they
stay while satisfaction and need are within 0.10 of the thresholds. Rust
takes the census at the end of each tick (`movements::census`), so Phase 10
reads it as it stands.

### Emergence (Python)

From turn 10, each turn: a region of a living civ is a candidate for a
creed when at least 5 adults and 20% of them are aggrieved, its ruler has
no living movement of that creed, fewer than 2 living movements and none of
that creed in the last 20 turns, and the world has fewer than 8.

- Chance 0.03 x share / 0.20, times the carrier, at most 0.25; at most one
  founding per turn, candidates rolled in order of share x carrier.
- Carriers: an active great person of the ruler in the region (x2 for a
  prophet founding a sect, x1.5 otherwise; the person leads and is the first
  member), else a city (x(1 + unrest)), else the boldest aggrieved agents.
- The founders are enrolled at founding (`AgentSimulator.found_movement`,
  since `fix/movements-narration-polish`; before, by the next tick): 15% of
  the region's adults (at least 3), the most aggrieved by
  `g x (1.5 + boldness)` then agent id, plus the leader. A founding nobody
  can join (every aggrieved there already in a movement) is not made.
- If the target has adopted an M16b idea whose value fits the creed
  (commons: wealth, progress, unity; liberty: freedom, independence, honor;
  sect: faith, tradition, knowledge), the movement carries it (named, appeal
  x1.25): the idea is the content, the movement its carriers.

### Recruitment and spread (Rust, each tick)

After the knowledge phase, before delivering merchants go home:

- Lapse first, with the combined chance of: movement ended (always), won
  (0.10), content (0.04), outside the target's realm and not travelling
  (0.10), a crackdown in its region while timid (boldness < 0: 0.5).
- Then each aggrieved adult of the target's realm: `p = 0.25 x appeal x
  (0.5 + 0.5 g) x exposure x (1 + 0.5 boldness) x loyalty x stage`, at most
  0.5, where exposure = positive bonds to members (two count fully) +
  members' share of the region's adults + members' share of the agent's
  settlement (towns accelerate), loyalty = 1.5 - loyalty for the target's
  own people (0.5-1.5), stage 0.5 suppressed, 1.5 rising, 0 satisfied. One
  draw over the candidate movements; counts are taken before the pass.
- Spread between regions: migrants keep their membership, bonds reach
  across regions, merchants on a trip recruit where they are. Information
  packets are a later slice.
- RNG: ChaCha8 streams per region, `MOVEMENT_LAPSE_STREAM_OFFSET = 2400`
  and `MOVEMENT_RECRUIT_STREAM_OFFSET = 2500`.

### Pressure, demands and responses (Python, Phase 10)

From the Phase 10 rows: members, members by region, strength (members'
share of the target realm's adults) and the stronghold (the realm region
with the largest member share).

- **Pressure.** At 5% strength the ally faction gains `min(0.01, 0.05 x
  strength)` a turn.
- **Demand.** At 10% strength and 5 members, from 5 turns after the
  founding, every 12 turns. Grant chance 0.35, +0.2 for cautious,
  calculating, shrewd or opportunistic rulers, -0.2 for aggressive, zealous,
  stubborn or bold ones, +0.15 under 30 stability, +0.5 x (strength - 0.10),
  +0.5 x (cultural - 0.25) for commons, -0.5 x (military - 0.25) for
  liberty, -0.5 x (clergy - 0.25) for sects, and with governance +0.3 x
  (0.5 - legitimacy); within 0.05-0.9. Otherwise a crackdown with chance
  0.35 (+0.2 harsh traits, +0.5 x (military - 0.25), sects also +0.5 x
  (clergy - 0.25)), else a refusal.
- **Reform** (slice 2 adds the [lasting reform](#lasting-reforms)). Commons
  cost the treasury `8 + 40 x strength` (`keep`);
  liberty costs 3 stability (`guard-shock`); a sect lowers the clergy by
  0.03. On the next tick members regain half their creed need's deficit;
  their satisfaction gains 0.08, falling to 0 over 20 turns. The movement is
  satisfied, recruits no one, its members lapse at 0.10 a turn, and it ends
  as won.
- **Refusal.** Grievance +0.25, ruler stability -1 (`guard-shock`).
- **Crackdown** in the stronghold. The members there get the persecution
  memory on the next tick and the timid lapse; the boldest tenth (1 to 5)
  are killed as martyrs through the war-casualty path
  (`queue_targeted_deaths`). Martyrs raise the appeal (x(1 + 0.1 each), at
  most x2); a sect's martyrs add to the region's `martyrdom_boost` with the
  M38b constants. Military +0.02, ruler stability -1, grievance +0.35,
  suppressed for 10 turns. A leader's death also makes a martyr.

### Risings, schisms and secession

At grievance 0.5 (0.25 for sects), with 25% members in the stronghold (20%
for sects) and 5 of them (4), 20 turns after the last rising:

- A **sect** of the ruler's or the stronghold's church **breaks away**:
  `religion.fire_schism` in the stronghold (a new faith and the region's
  conversion signal, as the religion path does); its members adopt the new
  faith on the next tick; the movement ends absorbed in it. The religion
  path's detector fills the 16-faith registry in the first dozen turns of
  every gate world (12 schisms by turn 7-11; most of those faiths later have
  no believer). A movement schism in a full registry therefore takes the
  place of a faith that no agent holds and nothing refers to (regions,
  rulers, temples and builds, the one-turn signals): same faith id, same
  registry position. The detector keeps its cap. A sect of a minority faith
  rises instead.
- Otherwise it **rises**: ruler stability -5 (`guard-shock`), a failed
  outcome for M66a legitimacy, and on the next tick +0.4 rebel utility for
  the members in the stronghold. That turn's Phase 10 resolves it from the
  rebels the tick produced (turnout over the members):
  - **secession** for liberty, when the ruler's stability is under 30 (the
    free-city threshold), turnout is at least 30%, the stronghold is
    neither the capital nor occupied and the ruler keeps a region: the
    stronghold and the adjacent realm regions where the movement holds 25%
    leave as a new civ (`Free <region>`) through the transfer helper the
    cities' free city uses (military and economy split `guard`, treasury by
    region share `keep`, ruler stability -10 `guard-shock`, agents
    transferred in hybrid mode, hostile to the old ruler, a `secession`
    event). The movement ends as seceded;
  - **concession** under 30 stability or with chance 0.35: a reform;
  - otherwise **crushed**: a crackdown with twice the martyrs;
  - a stronghold that changed hands meanwhile disperses the rising.

### Decay

Fewer than 3 members for 5 turns ends a movement: won when satisfied,
broken when suppressed, else faded; no member left (observed after its
founding turn) ends it at once, by the same rule. It dissolves when its
target civ is gone. Ended movements stay in the list (identity by index);
their members are released on the next tick.

### Contracts

- Switch: `WorldState.agent_movements: MovementState | None`, omitted while
  None; `--agent-movements` / `--no-agent-movements`; new worlds off; saved
  worlds keep their setting; `main.py`, `live.py` and
  `scripts/m53b_run_validation.py --agent-movements` (recorded in
  `run_manifest.json`).
- The bridge sends the movement table only with the switch on; the native
  pass and census run only after a table was set. Switched off: no table,
  no census call, a zero `movement_id` column, no draw.
- The table (`set_movement_table`, one row per living movement plus a
  schism's movement on the tick after) is rebuilt from persisted state
  every tick. One-shots come from turns stored on the movement (founding,
  reform age, crackdown, rising, schism at `turn - 1`); Rust clears them
  after the tick, so a tick without a new table repeats none. Python keeps
  no transient movement field on the world.
- Randomness: `random.Random(stable_hash_int("agent_movements", namespace,
  seed, turn, index))`, namespaces `emerge`, `response`, `rising`,
  `secession`, `name`, `regnal`. Identity: region index, civ index,
  movement index; a secession appends a civ as secession does.
- Accumulator: treasury `keep`; stability `guard-shock`; the secession split
  `guard`. Faction influence is written to the faction state.
- Persecution is untouched: crackdowns reuse the persecution memory and the
  martyrdom constants, never `persecution_intensity`. No migration weight
  changed.
- Append-only orders: `CREED_NAMES`, `STAGE_NAMES`, `END_NAMES`,
  `HISTORY_KINDS`, `COUNTER_KEYS` (Python), the stats columns and creed and
  stage codes (Rust), the snapshot column (last).

## Turn placement

| When | What |
| --- | --- |
| Agent tick, after the knowledge phase | `movements::movement_pass`: release and lapse, founding and re-seeding, recruitment, relief, crackdown memories, rising boost, schism conversion |
| Agent tick, step 1 / step 3 | members' reform relief on satisfaction / the rising's rebel utility |
| Agent tick, end | `movements::census` |
| Phase 10, after cities | `tick_agent_movements`: observe, fade, pressure, demands and responses, risings and their resolution, schisms, secessions, emergence (founders enrolled natively at once) |
| Next tick | the table built from the state |

Narration: every movement event carries its causes (the founding cites the
region's famine, epidemic, occupation, conquest or persecution; a refusal
its demand; a rising its refusals and crackdowns; a secession its rising),
so the curator's recorded chain reaches the narrator; sect schisms and
secessions use the existing `Schism` and `secession` event types.

## Slice 1: a movement's history

`scripts/agent_movements_report.py RUN_DIR` prints each movement's record
with the event text the simulation wrote. Template world, seed 46, 300
turns, hybrid, `--agent-movements`, everything else at its default
(`--simulate-only`, `PYTHONHASHSEED=0`, head `c93e87e`):

```
the Penitents of Sapphire Coast (sect), founded turn 19 in Sapphire Coast against Vrashni
Dominion; peak 9 members, 2 demands, 0 martyrs; ended schism turn 47
    19: founded: In Sapphire Coast, the discontented found the Penitents of Sapphire Coast: 9
         of 33 people there want the reform of the Faith of Vrashni Dominion
    23: spread: the Penitents of Sapphire Coast spreads to Obsidian Shore (2 members)
    24: demand: the Penitents of Sapphire Coast, 5 strong (10% of the people of Vrashni
         Dominion), demands freedom to worship in the Faith of Ashkari Nomads
    24: refused: Vrashni Dominion refuses the Penitents of Sapphire Coast
    36: demand: the Penitents of Sapphire Coast, 7 strong (19% of the people of Vrashni
         Dominion), demands the reform of the Faith of Vrashni Dominion
    36: refused: Vrashni Dominion refuses the Penitents of Sapphire Coast
    47: spread: the Penitents of Sapphire Coast spreads to Stormbreak Cliffs (2 members)
    47: schism: the Penitents of Sapphire Coast breaks away from the Faith of Ashkari Nomads
         in Sapphire Coast: 'Faith of Ashkari Nomads (Reformed)' is founded in place of the
         vanished 'Faith of Selurian Republic (Reformed 7)'
    47: ended: the Penitents of Sapphire Coast becomes the church of 'Faith of Ashkari Nomads
         (Reformed)'

the Ploughmen's League of Iron Peaks (commons), founded turn 55 in Iron Peaks against Kethani
Empire, led by Queen Seafoam; peak 9 members, 2 demands, 1 martyrs; ended won turn 87
    55: founded: In Iron Peaks, Queen Seafoam founds the Ploughmen's League of Iron Peaks: 7
         of 29 people there want relief from hunger and dues
    60: demand: the Ploughmen's League of Iron Peaks, 8 strong (21% of the people of Kethani
         Empire), demands relief from hunger and dues
    60: refused: Kethani Empire refuses the Ploughmen's League of Iron Peaks
    61: martyr: The death of Queen Seafoam makes a martyr for the Ploughmen's League of Iron Peaks
    64: spread: the Ploughmen's League of Iron Peaks spreads to Verdant Plains (2 members)
    72: demand: the Ploughmen's League of Iron Peaks, 6 strong (26% of the people of Kethani
         Empire), demands relief from hunger and dues
    72: refused: Kethani Empire refuses the Ploughmen's League of Iron Peaks
    73: rising: the Ploughmen's League of Iron Peaks rises against Kethani Empire in Iron
         Peaks (7 members)
    74: concession: After the rising, Kethani Empire grants the Ploughmen's League of Iron
         Peaks relief: remitted dues and grain from the stores (7 from the treasury)
    87: ended: the Ploughmen's League of Iron Peaks disbands, its demand met
```

The recorded causes tie the record together: the founding cites the dearth
open in Sapphire Coast at turn 18, each demand the founding and the last
refusal, each refusal its demand, the schism the refusal of turn 36, the end
the schism. The members' commonest faith changes between the demands (the
Faith of Ashkari Nomads, the stronghold's majority, and the ruler's Faith of
Vrashni Dominion), so the second demand asks for the reform of the ruler's
faith. At turn 47 the registry is full (the base detector's 12 schisms in turns
1-10) and the sect takes the place of the vanished 'Faith of Selurian
Republic (Reformed 7)'. The second record, from the same run, is a rising:
two refusals, the death of its leader, a rising in Iron Peaks that cites the
refusal and the dearth of turn 70, and a concession.

Over the twelve 300-turn runs of this probe (seeds 42-53): 147 movements,
108 demands, 44 reforms, 43 refusals, 21 crackdowns, 55 martyrs, 12
risings (5 concessions, 7 crushed), 6 movement schisms, no secession; 47
ended as won, 76 faded, 5 broken, 2 dissolved.

## Slice 1 feature-off identity

Base: `ec229b5` exported with `git archive` and its extension built from
that tree (SHA-256 `46f4fa81...c52b9b`, the one city-markets recorded),
`PYTHONPATH` on the export; branch: the worktree and its extension. Same
interpreter, `PYTHONHASHSEED=0`, `scripts/agent_movements_identity.py`.

1. **Direct runs**: template seeds 42 / 7 / 1234, `--agents off` 300 turns
   and hybrid 200; procedural 48 regions x 10 civs, seed 7, off 200 and
   hybrid 120. Every file (`state.json` and its historiography and
   languages sidecars, `chronicle.md`, `memories_*.json`,
   `agent_events.arrow`, the bundle without `metadata.generated_at`): **88
   files, 0 differences** with the default switch; **73 files, 0
   differences** with `--no-agent-movements` (template off and hybrid,
   procedural hybrid).
2. **Switch on, agents off**: the three template runs with
   `--agent-movements`: **27 files, 0 differences** once the layer's own
   field is removed (`compare-inert`). Without agents there is no census,
   so nothing is founded.
3. **Subset gate** 42-61 x 200 hybrid, base gate (exported tree) against
   this branch's switch-off gate: every run file identical (20 seeds x 110
   files, 0 differences); validation report, gate decision, gate summary and
   summary identical once the batch path is normalized.
4. **In the suite**: the frozen exact-trajectory oracles pass unchanged;
   `test_feature_off_never_runs_movement_code` forbids every movement entry
   point through 20 off-mode turns; natively, with the switch off the
   snapshot's `movement_id` is all zero and the simulator never enabled the
   pass. In Rust, `without_a_table_the_tick_is_unchanged` compares the plain
   tick with a disabled and an enabled-but-empty runtime bit for bit.

## Slice 1 switch-on subset gates

`scripts/m53b_run_validation.py --profile subset --parallel 1
--agent-movements`, compared by `validation_compare` with the base gate of
the same seeds (shown identical to the branch's switch-off gate above).
Gate head `c93e87e`; its three switch-on validation reports equal those of
`d5e3bf5` (the later commit changes event text only).

| | 42-61 base | 42-61 on | 62-81 base | 62-81 on | 82-101 base | 82-101 on |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| gate / comparator | PASS / - | PASS / NO REGRESSION | PASS / - | PASS / NO REGRESSION | PASS / - | PASS / NO REGRESSION |
| migration per agent-turn | 0.0619 | 0.0608 | 0.0548 | 0.0546 | 0.0619 | 0.0603 |
| rebellion per agent-turn | 0.0376 | 0.0350 | 0.0153 | 0.0162 | 0.0353 | 0.0319 |
| satisfaction mean / latest | 0.591 / 0.603 | 0.595 / 0.612 | 0.608 / 0.619 | 0.613 / 0.631 | 0.598 / 0.605 | 0.603 / 0.611 |
| needs (seeds with the expected sign; 12 required) | 16 | 12 | 16 | 13 | 16 | 14 |
| schisms per world (all) | 12.00 | 12.25 | 12.00 | 12.20 | 12.00 | 12.10 |
| secessions per world (all) | 0.05 | 0.05 | 0.05 | 0.05 | 0.05 | 0.00 |
| extinct worlds | 0 | 0 | 0 | 0 | 0 | 0 |
| local rebellions (agent summaries) | 858 | 885 | 356 | 393 | 872 | 790 |
| movements founded (20 worlds) | 0 | 152 | 0 | 143 | 0 | 139 |
| demands / reforms / refusals / crackdowns | 0 / 0 / 0 / 0 | 94 / 41 / 36 / 17 | 0 / 0 / 0 / 0 | 73 / 42 / 18 / 13 | 0 / 0 / 0 / 0 | 83 / 36 / 31 / 16 |
| martyrs | 0 | 52 | 0 | 45 | 0 | 50 |
| risings: concession / crushed / secession | 0: 0 / 0 / 0 | 5: 3 / 2 / 0 | 0: 0 / 0 / 0 | 5: 3 / 2 / 0 | 0: 0 / 0 / 0 | 13: 6 / 6 / 0 |
| movement schisms | 0 | 5 | 0 | 4 | 0 | 2 |
| ended: won / faded / broken / dissolved | 0 / 0 / 0 / 0 | 43 / 86 / 4 / 1 | 0 / 0 / 0 / 0 | 44 / 76 / 4 / 3 | 0 / 0 / 0 / 0 | 42 / 73 / 4 / 1 |

- **Migration** -0.0011, -0.0002, -0.0016; every set stays above the strict
  0.05 floor (0.0608, 0.0546, 0.0603). No migration weight changed; the
  crackdown's persecution memory adds migrate utility for few members.
- **Rebellion** -0.0026, +0.0009, -0.0034: risings add rebels in their
  stronghold, reforms take aggrieved people out of the pool.
- **Satisfaction** +0.004 to +0.005 (mean), +0.006 to +0.012 (latest):
  reform relief.
- **Needs** 16 -> 12, 13, 14 (12 required): the direction holds in all three
  sets. The oracle pairs a handful of agents per seed (matched civ, region,
  occupation and personality) and compares their events over 20 turns;
  movements select people by the same needs and personality and change
  their events (relief, crackdowns, risings). A probe build without the
  members' need restoration on a reform gives 14 on 42-61 (12 with it):
  part of the drop at most, within the oracle's seed-to-seed spread. The
  restoration stays (a reform answers the need it was granted for); the
  full gate is the check.
- **Schisms** stay near 12 per world: movement schisms (0.2-0.25 per world)
  reuse vanished faiths' places. **Secessions**: none from movements in the
  60 worlds (liberty movements are the rarest creed; autonomy is the need
  least often deficient); the path is tested.
- **Extinction**: no world went extinct; polities alive at the end
  2.95 -> 3.2, 3.2 -> 3.1, 2.8 -> 2.85.

## Slice 1 tick time

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, starting targets
18,800 and 43,700 (about 22,800 and 54,500 alive when measured), 30 warm-up
turns (movements are founded from turn 10) and 8 timed turns, two repeats,
one child at a time, release builds, shared 4-core machine (another agent's
full gate running). Median per run, wall / process CPU, in ms:

| agents | | base `ec229b5` | branch, off | branch, `--agent-movements` |
| ---: | --- | ---: | ---: | ---: |
| ~22,800 | Rust tick | 117, 114 / 249, 261 | 108, 104 / 255, 245 | 107, 111 / 246, 250 |
| | whole turn | 212, 192 / 353, 349 | 196, 175 / 342, 311 | 189, 210 / 326, 343 |
| ~54,500 | Rust tick | 451, 438 / 1,372, 1,363 | 451, 434 / 1,429, 1,352 | 455, 469 / 1,377, 1,467 |
| | whole turn | 576, 603 / 1,884, 1,944 | 592, 579 / 1,968, 1,944 | 593, 596 / 1,947, 2,008 |

In the switched-on runs the timed turns carried one movement of 108 members
(~22,800) and two of 671 (~54,500). Every arm is within the machine's run
to run spread (the switch-off branch runs the base's code path and differs
from it by up to 5% CPU). The pass is a census, a lapse loop over members,
and, for aggrieved adults only, a bond scan through an id map built once a
tick; Phase 10 adds a few `bincount` passes over the rows per movement.

## Slice 1 bundle size

The 500-turn guard world (`tests/test_bundle.py`: seed 1, 5 civs, 10
regions, agents off) has the switch off by default: 18.78 MB, unchanged.
With `--agent-movements` and agents off (no census, nothing founded): 18.90
MB, the `agent_movements` field 0.13 MB. The same world in hybrid mode:
20.06 MB off, 19.10 MB on (field 0.14 MB, the rest the diverged world). All
under the 24 MB guard.

## Slice 1 tests

- `tests/test_agent_movements.py` (30 tests, in the offline lane's
  `systems-2` chunk; the four native ones skip there): switch, dormancy and
  old saves; emergence where grievances cluster, the caps and the creed
  cooldown, a great person carrier, an M16b idea; members, strength,
  stronghold and spread from the rows; pressure on the ally faction;
  grants with relief signals, the grant and crackdown chances, refusals,
  crackdowns that kill the boldest and leave `persecution_intensity` alone;
  a rising and secession (governance's failed outcome), concession and
  crushing, a schism through the religion path and in a full registry; the
  narrator's recorded chain of a rising; fading, winning, dissolving, being
  broken, a leader's martyrdom; the table and seeds from persisted state;
  snapshot, history and metrics; the feature off never running movement
  code; off-mode determinism; the CLI flag, gate forwarding, live default,
  resume and analytics; the identity script; native: the switch off sends
  nothing and the column is zero, a founding seeds members and an ended
  movement releases them (one-shots consumed once), crackdown memories
  written once, re-seeding after a fresh pool, a hybrid run founding
  movements.
- `tests/test_wave3_combined.py`: save/load resume identity with movements,
  cities and every other system on (32-region procedural world, `--agents
  off`, two movements placed as a save carries them): saved at the first
  turn from 30 on with demands, refusals, crackdowns, a reform and a rising
  recorded; the movement table compared turn by turn and every byte of the
  world after 15 more turns.
- Rust: `movements` unit tests (grievance, the disabled runtime, founding
  seeds and their one-shot, recruitment by bonds and needs, the realm gate,
  release, relief once, crackdown intents and the rising boost, schism
  conversion, re-seeding, determinism) and `tests/test_agent_movements.rs`
  (full ticks: unchanged without a table, a founding growing and an ended
  movement releasing its members, relief and rising on the next tick only);
  the stream registry test includes the two new offsets.
- Snapshot contract: the campaign snapshot tests follow the 24-field
  layout; `test_a_capture_from_before_the_movement_column_is_accepted`; the
  frozen-baseline workflow comparison reads a 23-field capture.

## Slice 1 verification

Verification on `c93e87e` (Linux, Python 3.13; extension built fresh from
the branch's Rust source, SHA-256 `cde64b3e...b5cf6a`, compiled submodule
and classes verified; the Rust source is unchanged since `5311761`):

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off, at `d5e3bf5`, same Rust) | 959 passed, 0 failed, 2 ignored (main 945) |
| `pytest -m "not slow" -n 2` | 6,080 passed, 3 skipped, 526 subtests (main 6,046) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust lane (venv without `chronicler_agents`, every test) | 5,861 passed, 222 skipped (main 5,831 / 218) |
| `scripts/run_python_oracle_checks.py` | PASS in 75.5 s: 2,050 passed, 24 skipped; largest chunk 26.4 s of 110 s |
| Golden and exact-trajectory fixtures | unchanged |
| Identity (switch off), subset gates (switch on), tick time, bundle | above |

No viewer file changed. The full 200-seed gate was not run; the subset
gates are not a milestone qualification.

## Roadmap

Done in slice 2: lasting reforms through governance institutions, with
repeal and restoration; leaders as great persons, crowned by a secession;
the viewer's Movements tab; the full gate with the switch on, now default.
Next:

1. **Information packets** as a spread channel: done behind `--guilds`
   ([above](#news-driven-spread-and-the-guild-creed---guilds); news yields
   its slots to the other packets). Open: movements across borders
   (co-religionists and kin abroad; news already crosses borders, members
   do not).
2. **Guilds and craft leagues** in cities: done behind `--guilds`
   ([guilds.md](guilds.md): guilds, the guild creed and charter, the burgher
   faction). Open: craft leagues spanning several cities.
3. **Taxes and dues as a direct grievance**, and reforms that change the
   needs themselves (granaries in a famine, officers under foreign rule)
   rather than how a grievance reads.
4. **Agendas for leaders**: a leader takes the agendas of its role
   (prophet, general); an agenda of its own (lead the movement, found the
   state) needs a great-person ambition type in the M66b kernel.
5. **Viewer**: a map layer of strongholds and reforms by region.
6. **Calibration**: liberty secessions stay rare (8 in 200 full-gate
   worlds); the founding share and the cooldown are unchanged since slice 1;
   template worlds dominate the gate, so the procedural distributions are
   not measured here.
