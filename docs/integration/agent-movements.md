# Movements grounded in people (`--agent-movements`)

Branch `feat/agent-movements`, from `origin/feat/city-markets` `b4ce043`,
fast-forwarded to `origin/main` `ec229b5` (PR #30, the same tree). Code:
`src/chronicler/agent_movements.py` (decisions),
`src/chronicler/agent_movements_state.py` (persisted state),
`chronicler-agents/src/movements.rs` (membership and spread), and
`scripts/agent_movements_report.py`.

**Status.** Default off (`DEFAULT_ENABLED_FOR_NEW_WORLDS = False`). With the
switch off every output is byte-identical to the base (see
[Identity](#feature-off-identity)). Results are recorded below.

## What exists

- **M16b ideas** (`movements.py`): every 30 turns an idea emerges from the
  civ with the highest culture and lowest stability and spreads between
  civs by contact or trade. An idea has a value affinity and per-civ variant
  counters; diverging variants record a `movement_schism` named event, and
  disposition drifts with shared ideas. No person belongs to an idea.
- **Faiths** (`religion.py`, M37/M38b): per-region majority belief,
  conversion signals, persecution by militant rulers (the builder owns
  `persecution_intensity` and `persecuting_faith` every turn,
  [persecution-fix-2026-10.md](persecution-fix-2026-10.md)), martyrdom boost
  from persecuted deaths, schisms when a region's minority exceeds 30%
  (`fire_schism` creates a faith and sets the region's one-turn schism
  conversion signal), reformations.
- **Factions** (`factions.py`): military, merchant, cultural and clergy
  influence, shifted by events and normalized with a floor; power struggles.
- **Governance** (`governance_runtime.py`, on by default): institutions,
  ruler legitimacy (M66a), PSI and its revolts. Revolts and lost wars are
  failed outcomes (`CivGovernance.defeat_turns`) that lower legitimacy.
- **Great persons and agendas**: prophets, generals, merchants and
  scientists with a region and (in agent modes) an agent id.
- **Cities** (`cities.py`, on by default): unrest, charters, urban revolts
  and free cities (a new civ built as `check_secession` builds one).
- **Agents** (Rust): beliefs, the six needs, satisfaction, loyalty,
  wealth, occupation, personality (boldness, ambition, loyalty), memories
  with persecution and other modifiers, bonds with sentiment, settlement
  ids, merchant trips. Needs already carry the grievances: famine and
  poverty lower material, foreign rule, displacement and persecution block
  autonomy, a minority faith or no temple lowers spiritual.

Nothing ties these together into people acting in concert.

## The slice

A **movement** is a set of agents (per-agent membership) with a shared
grievance and a target: the ruler of the region where it was founded. It is
founded where grievances cluster and a carrier exists, grows through bonds,
co-residence and towns, spreads with migrants and merchants inside its
target's realm, and at scale presses its demand. The ruler grants, refuses or
suppresses. Refused or suppressed movements that hold a stronghold rise; a
risen sect breaks with the church instead. Movements fade, win or are
crushed.

Three creeds, one per grievance (append-only `CREED_NAMES`):

| creed | grievance (need) | carried by | demand | escalation | ally faction |
| --- | --- | --- | --- | --- | --- |
| `commons` | material: hunger, poverty | leagues of the poor, peasant leagues | relief | rising; concession or crushed | cultural |
| `liberty` | autonomy: foreign rule, displacement, persecution | nativist and autonomist currents | local rights | rising; secession of the stronghold | military |
| `sect` | spiritual: minority faith, no temple | reform and millenarian sects | toleration | schism through `fire_schism` (ruler's faith) or rising | clergy |

Guilds, broader egalitarian programmes and cross-border movements are later
slices ([Roadmap](#roadmap)).

### Membership (Rust)

- `AgentPool.movement_ids: Vec<u16>`: 0 = none, otherwise the movement's
  index in `world.agent_movements.movements` + 1. An agent belongs to at
  most one movement. Spawn and slot reuse set 0; deaths free the slot.
- The snapshot gains the column `movement_id` (UInt16, appended last; the
  Python bridge contract is updated with it). Phase 10 reads membership
  from the same rows every other consumer reads.
- Persistence: the native pool is not saved (hybrid resume is unsupported,
  `checkpoint_replay`). The world saves each movement's members by region;
  on a resumed hybrid run the bridge re-seeds that many members per region
  (`seed_members` in the movement table), so membership survives a
  save/load at region resolution. With `--agents off` a world that carries
  movements keeps them: members stay at the saved counts, and the political
  side (demands, responses, risings, fading) runs from persisted state. The
  save/load resume test uses that mode.

### Grievance

An adult (16+) is aggrieved for a creed when its satisfaction is below 0.45
and that creed's need is below its threshold: material 0.55, autonomy 0.60,
spiritual 0.45. Intensity `g` is the mean of the two normalized deficits
(0..1). The thresholds come from a probe of the base (template worlds, seeds
42 and 47, 200 turns, every 10 turns per region): about 3-10% of adults are
aggrieved per creed, 10-30% in the worst tenth of regions; the need
thresholds sit above the behaviour thresholds (0.25-0.30), so movements form
before people are desperate.

### Emergence (Python, each turn)

Rust reports per region the adults and the aggrieved per creed
(`get_movement_stats`). A region of a living civ is a candidate for a creed
when at least 5 adults and 20% of them are aggrieved, its ruler has no living
movement of that creed and fewer than 2 living movements, and the world has
fewer than 8.

- Chance: 0.03 x share / 0.20, times the carrier, at most 0.25.
- Carrier: an active great person in the region (x2 for a prophet founding a
  sect, x1.5 otherwise; the person leads the movement and is its first
  member), else a city in the region (x(1 + unrest)), else the boldest
  aggrieved agent (x1).
- At most one founding per turn: candidates in order of score (share x
  carrier), each rolled once.
- Founding seeds the most aggrieved bold adults of the region: 5% of its
  adults, at least 3, ordered by `g x (1.5 + boldness)` then agent id, plus
  the leader.
- If the target civ has adopted an M16b idea whose value fits the creed
  (commons: wealth, progress, unity; liberty: freedom, independence, honor;
  sect: faith, tradition, knowledge), the movement carries it (named, appeal
  x1.25). This is the M16b link: the idea is the content, the movement its
  carriers in the population.

### Recruitment and spread (Rust, each tick)

After the knowledge phase and before delivering merchants go home, so a
merchant member is present in the market it reached:

- Lapse first. A member leaves with the combined chance of: its movement
  ended (always), won (0.10), no longer aggrieved (0.04), outside the target
  realm (0.10), a crackdown in its region while it is timid (boldness < 0:
  0.5).
- Then recruitment of non-members who are aggrieved for a movement's creed,
  in a region of its target's realm: `p = 0.25 x appeal x g x exposure x
  (1 + 0.5 boldness) x loyalty x stage`, at most 0.5, where exposure =
  member bonds (positive bonds to members, two count fully) + members'
  share of the region's adults + members' share of the agent's settlement
  (towns accelerate), loyalty = 1.5 - loyalty for the target's own people
  (within 0.5-1.5), stage = 0.5 while suppressed, 1.5 while rising, 0 once
  satisfied. One draw per agent over the candidate movements in index
  order. Counts are taken before the pass.
- Spread between regions has three carriers: migrants keep their
  membership, bonds reach across regions, and merchants on a trip recruit
  where they are. Information packets are left for a later slice.
- RNG: one ChaCha8 stream per region, `MOVEMENT_STREAM_OFFSET = 2400`.

### Pressure, demands and responses (Python, Phase 10)

From the Phase 10 rows, per movement: members, members by region, the
share of the target realm's adults (strength) and the stronghold (the realm
region with the largest member share).

- **Pressure.** While strength is at least 5%, the creed's ally faction
  gains `min(0.01, 0.05 x strength)` (normalized). The ally faction shapes
  the response: the cultural faction favours grants, the military and the
  clergy favour suppression.
- **Demand.** At 10% strength and 5 members, every 12 turns at most, the
  movement presents its demand. The ruler grants with chance 0.35, +0.2 for
  cautious, calculating, shrewd or opportunistic rulers, -0.2 for
  aggressive, zealous, stubborn or bold ones, +0.15 under 30 stability,
  +0.5 x (strength - 0.10), +0.5 x (cultural - 0.25) for commons, -0.5 x
  (military - 0.25) for liberty, -0.5 x (clergy - 0.25) for sects, and with
  governance +0.3 x (0.5 - legitimacy); within 0.05-0.9. Otherwise it
  suppresses with chance 0.35 (+0.2 for the harsh traits, +0.5 x (military -
  0.25), +0.5 x (clergy - 0.25) for sects; within 0.05-0.9), else refuses.
- **Reform** (grant): commons cost the treasury `8 + 40 x strength`
  (`keep`), liberty costs 3 stability (`guard-shock`), a sect lowers the
  clergy by 0.03. The movement is satisfied. Its members' creed need is
  restored by 0.5 of the deficit on the next tick, and their satisfaction
  gains 0.08, falling to 0 over 20 turns. A satisfied movement recruits no
  one; its members lapse at 0.10 a turn and it ends as won.
- **Refusal**: grievance +0.25, ruler stability -1 (`guard-shock`).
- **Suppression** (crackdown) in the stronghold: members there get a
  persecution memory on the next tick (the M48 persecution memory, its rebel
  and migrate modifiers and its 25-turn half-life), timid members lapse, the
  boldest tenth of them (at most 5) are killed (queued native deaths, the
  war-casualty path) as martyrs. Martyrs raise the appeal (x(1 + 0.1 per
  martyr), at most x2); a sect's martyrs add to the region's
  `martyrdom_boost` with the M38b constants. Ruler: military +0.02,
  stability -1. Grievance +0.35; suppressed for 10 turns.

### Risings, schisms and secession

A movement with grievance 0.5 (two refusals, or a refusal and a crackdown)
whose stronghold holds 25% members and 5 members, 20 turns after its last
rising:

- A **sect of the ruler's faith** breaks with the church: `fire_schism` in
  the stronghold (the region conversion signal and a new faith in the
  registry, as the religion path does), its members adopt the new faith on
  the next tick, and the movement ends absorbed in it (`schism`).
- Otherwise it **rises**: ruler stability -5 (`guard-shock`), a failed
  outcome for governance's legitimacy, and on the next tick its members in
  the stronghold get +0.4 rebel utility. The rising is resolved in that
  turn's Phase 10 from the rebels the tick produced (turnout over the
  stronghold's members):
  - **secession** for liberty, when the ruler's stability after the rising
    is under 25, turnout is at least 30%, the stronghold is not the
    capital or occupied and the ruler keeps another region: the stronghold
    and the adjacent realm regions where the movement holds 25% leave as a
    new civ, transferred by the helper the cities' free city uses
    (`politics.transfer_regions_to_new_civ`; military and economy split
    `guard`, ruler stability -10 `guard-shock`, agents transferred in
    hybrid mode, hostile to the old ruler). The movement ends as seceded;
  - **concession** under 30 stability or with chance 0.35: a reform as
    above;
  - otherwise **crushed**: a crackdown with twice the martyrs.

### Decay

A movement with fewer than 3 members for 5 turns ends: as won when it was
satisfied, crushed when it lost members to crackdowns, else faded. It ends
dissolved when its target civ is gone. A suppressed movement resumes after
10 turns. Ended movements stay in the list (identity by index); their
members are released on the next tick.

### Contracts

- Switch: `WorldState.agent_movements: MovementState | None`, omitted while
  None; `--agent-movements` / `--no-agent-movements`; new worlds off; saved
  worlds keep their setting; `main.py`, `live.py` and
  `scripts/m53b_run_validation.py --agent-movements` wire it.
- The native pass runs only when the movement table has been set; the
  bridge sends it only with the switch on. Switched off, no table, no
  stats call, no new snapshot values (the column is all zero) and no new
  draw.
- Movement table (`AgentSimulator.set_movement_table`, one row per living
  movement) is rebuilt from persisted state every tick. One-shots are
  derived from turns stored on the movement (founded, reform, crackdown,
  rising, schism and re-seeding at `turn - 1`); Rust clears them after the
  tick, so a second tick without a new table does not repeat them.
- Randomness: `random.Random(stable_hash_int("agent_movements", namespace,
  seed, turn, index))`; Rust as above. Identity: region index, civ index,
  movement index; nothing else is invented.
- Accumulator: treasury `keep`, stability `guard-shock`, secession split
  `guard`. Faction influence is written to the faction state.
- Persecution is untouched: crackdowns reuse the persecution memory and the
  martyrdom constants, never `persecution_intensity`.
- Append-only orders: `CREED_NAMES`, `STAGE_NAMES`, `END_NAMES`,
  `HISTORY_KINDS`, `COUNTER_KEYS` (Python), the stats columns (Rust).

## Turn placement

| When | What |
| --- | --- |
| Agent tick, after the knowledge phase | `movements::movement_pass`: release and lapse, founding seeds, recruitment, relief, crackdown memories, rising boost, schism conversion, stats |
| Agent tick, step 1 | members' satisfaction relief after a reform |
| Agent tick, step 3 | rising rebel boost |
| Phase 10, after cities | `tick_agent_movements`: observe, fade, pressure, demands and responses, risings and their resolution, schisms, secession, emergence |
| Next tick | the movement table built from the state |
