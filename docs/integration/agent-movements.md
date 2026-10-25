# Movements grounded in people (`--agent-movements`)

Branch `feat/agent-movements`, from `origin/feat/city-markets` `b4ce043`,
fast-forwarded to `origin/main` `ec229b5` (PR #30, the same tree). Code:
`src/chronicler/agent_movements.py` (decisions),
`src/chronicler/agent_movements_state.py` (persisted state),
`chronicler-agents/src/movements.rs` (membership and spread),
`politics.transfer_regions_to_new_civ` (secession, shared with the cities'
free cities), `scripts/agent_movements_report.py` and
`scripts/agent_movements_identity.py`.

**Status.** Default off (`DEFAULT_ENABLED_FOR_NEW_WORLDS = False`). With the
switch off every output is byte-identical to `ec229b5`, agents off and
hybrid, direct runs and the subset gate ([Identity](#feature-off-identity)).
With it on, the subset gates 42-61, 62-81 and 82-101 pass with no comparator
regression ([Gates](#switch-on-subset-gates)); the needs oracle loses 2 to 4
seeds in each set (still above the 12 required), the open item for the full
gate. The full 200-seed gate was not run.

## Result

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
- The next tick seeds 15% of the region's adults (at least 3), the most
  aggrieved by `g x (1.5 + boldness)` then agent id, plus the leader.
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
- **Reform.** Commons cost the treasury `8 + 40 x strength` (`keep`);
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
broken when suppressed, else faded. It dissolves when its target civ is
gone. Ended movements stay in the list (identity by index); their members
are released on the next tick.

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
| Phase 10, after cities | `tick_agent_movements`: observe, fade, pressure, demands and responses, risings and their resolution, schisms, secessions, emergence |
| Next tick | the table built from the state |

Narration: every movement event carries its causes (the founding cites the
region's famine, epidemic, occupation, conquest or persecution; a refusal
its demand; a rising its refusals and crackdowns; a secession its rising),
so the curator's recorded chain reaches the narrator; sect schisms and
secessions use the existing `Schism` and `secession` event types.

## A movement's history

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

## Feature-off identity

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

## Switch-on subset gates

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

## Tick time

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

## Bundle size

The 500-turn guard world (`tests/test_bundle.py`: seed 1, 5 civs, 10
regions, agents off) has the switch off by default: 18.78 MB, unchanged.
With `--agent-movements` and agents off (no census, nothing founded): 18.90
MB, the `agent_movements` field 0.13 MB. The same world in hybrid mode:
20.06 MB off, 19.10 MB on (field 0.14 MB, the rest the diverged world). All
under the 24 MB guard.

## Tests

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

## Verification

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

1. **Information packets** as a spread channel (word of a movement crossing
   regions with packets), and movements across borders (co-religionists and
   kin abroad).
2. **Lasting reforms**: a granted demand that enacts a governance
   institution (commons management, written law, toleration of a faith)
   instead of a one-off relief, and taxes and dues as a direct grievance.
3. **Guilds and craft leagues** in cities: a city faction (a new
   `FactionType`, a state change) and urban movements for charters.
4. **Leaders**: members promoted to great persons; prophets' agendas
   leading sects; movement leaders as rulers of the states they found.
5. **Viewer**: a Movements tab and map layer from `history[n].agent_movements`.
6. **Calibration**: the needs oracle's 2-4 seed drop and the rarity of
   liberty secessions at the full gate; an `--agents off` proxy.
