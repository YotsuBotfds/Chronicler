# Cities as historical actors (`--cities`)

Branch `feat/cities`, from `integrate/wave-7` at `bcf14d8` (healthy-world
migration and the persecution fix). Code: `src/chronicler/cities.py`
(behaviour), `src/chronicler/cities_state.py` (persisted state) and one
migration driver in `chronicler-agents/src/migration_drivers.rs`.

**Status.** Design (this section) written before the build. Results,
identity proofs, gates and tick time are recorded below as they are run.

## What exists

- **M56a** (`settlements.py`) detects dense agent clusters every 15 turns
  from the Phase 10 agent rows, matches them across passes, promotes a
  candidate after two passes, and dissolves a settlement after its inertia
  and grace run out. Identity is `settlement_id` (monotonic, never reused);
  the name is `"<region> Settlement <n>"`. Agents-off worlds have no
  settlements.
- **M56b** sends active and dissolving footprints to Rust each tick; every
  agent carries `settlement_id` (0 = rural) and urban agents get small
  needs, satisfaction, culture-drift and conversion modifiers. The snapshot
  aggregates urban fractions per civ; narration gets the top settlements.
- Sieges already treat a settled region as fortified (`war/common.py`,
  `war/battles.py`). The languages layer names each settlement; narration
  maps canonical names in event text to in-world names.

What is missing: a settlement has no wealth, no politics, no draw on the
countryside and no history of its own. It forms and dissolves; nothing in
between is recorded or acts.

## The slice

One coherent actor, built on the M56a settlement and its `settlement_id`:
a city with **wealth**, a **population drawn from its hinterland**, a
**political voice**, and the capacity to **rise and fall**. Disease and war
act on it through existing systems. Everything else in the candidate list
(guild factions as a fifth faction, scholars and archives tied to places,
merchant routing toward city markets) is left for later slices.

Default off behind `WorldState.cities` (CLI `--cities`). Cities need
agents: with `--agents off` no settlement is detected, so a fresh world
founds no city and runs identically with the switch on.

### Founding, rank, decline and fall

- Each turn the Phase 10 agent rows give every settlement's residents (the
  agents whose `settlement_id` it is) by occupation, with their mean
  satisfaction and wealth. An ACTIVE settlement with at least the town
  threshold of residents becomes a **city** (record keyed by its
  `settlement_id`, region index, founder civ index).
- Ranks: town 1, city 2, great city 3, at `RANK_POP` residents (12 / 25 /
  40) scaled by the world's mean carrying capacity over 60. A rank is lost
  after `DOWN_TURNS` turns below `DOWN_FACTOR` (0.7) of its threshold.
- A city **falls** when M56a dissolves its settlement (abandoned), or after
  `FALL_TURNS` turns under `FALL_POP` residents (deserted). The fall cites
  the latest sack, epidemic or famine in its region, if any. Fallen cities
  are kept as records; a city founded later in the same region names its
  fallen predecessor.

### Wealth

- **Commerce** per turn: residents by occupation (merchants most, farmers
  least), times market access (the region's goods trade routes, from the
  economy result), times food (the region's food sufficiency, capped at 1),
  and a quarter while an enemy occupies the region.
- The city keeps commerce net of **dues** in a civic purse that decays 2% a
  turn. Dues fall with its charter (30% without one, 20% with market
  rights, 10% self-governing). They are owed to the lord (the region's
  controller) and paid at the start of the next turn's Phase 2, as
  `keep` treasury income beside the goods-economy tax, so `--finance`
  counts them as revenue. A free city keeps 30% of its commerce for its own
  treasury the same way.
- With `--finance`, chartered cities deepen their lord's domestic credit
  (merchant lenders): `credit_factor` 1 + 0.1 per charter level, at most
  1.5, beside the techniques and agenda factors.

### Population drawn from the hinterland (Rust)

A fourth healthy-world driver, **urban pull**, with its own gate. Python
gives each region a `city_pull` (the largest city's rank weight 0.4 / 0.7 /
1.0, times one minus its unrest, times its food sufficiency capped at 1;
zero while occupied). The region batch carries it as an optional column
only when the switch is on; Rust reads 0 when the column is absent.

- Gate: a rural adult (`settlement_id` 0) who is not a soldier; a
  neighbouring region of the same realm whose `city_pull` exceeds home's by
  `URBAN_MIN_GAP` 0.25; that region fed (food sufficiency at least 1) and
  below its carrying capacity (farmers: below 0.80, the frontier gate's
  threshold, so the pull does not refill a region frontier settlement is
  leaving).
- Pull: `URBAN_PULL` 0.5 x ramp(gap, 0.25, 0.75), opening at
  `PULL_AT_GATE` like the other drivers; it counts net of roots and only
  toward a region the mover would not leave again at once (the reach rule).
- No existing weight changes; the hysteresis, the 5-turn lock, the
  persecution terms and the 0.05 floor are untouched; no new random draw.
  The budget tally gains a `urban` term.

### Political voice

- **Patricians.** Each turn a lord's merchant faction gains 0.002 per unit
  of `rank x (1 + charter / 2)` over its cities, at most 0.015 a turn.
- **Charters.** A town with the fee in its purse petitions for market
  rights (fee 12); a city for self-government (fee 30); at most every 15
  turns. The lord grants with a chance from its ruler's trait (cautious,
  calculating and shrewd rulers sell privileges; aggressive, zealous,
  stubborn and bold ones refuse), an empty treasury, weakness and merchant
  influence. A grant pays the fee to the lord (`keep`) and lowers dues; a
  refusal leaves a grievance.
- **Unrest** follows a target from residents' mean satisfaction under 0.55,
  hunger (food sufficiency under 1), dues, occupation and the decaying
  grievance (refusals, sacks).
- **Urban revolt.** Above 0.5 unrest a revolt breaks out with chance up to
  0.25 a turn (cooldown 12): the lord loses 5 stability (`guard-shock`).
  Outcome:
  - **free city**: a lord below 25 stability with at least three regions,
    and a city (rank 2+) with a charter that is not the lord's capital or
    occupied: the region secedes as a city-state (a new civilization, as
    `check_secession` builds one: hostile to its old lord, the region's
    agents transferred to it in hybrid mode, the lord's military and
    economy split by population share, `guard`; stability -10,
    `guard-shock`), with half the civic purse as treasury;
  - **concession**: a lord below 40 stability, or with chance 0.3: the
    charter rises one level and the grievance is dropped;
  - **suppression** otherwise: a fine of a quarter of the purse to the lord
    (`keep`), unrest falls, the grievance grows.

### War and disease

- **Sack.** An enemy that occupies the city's region, or takes it while at
  war with its lord, carries off half the purse (`keep` to the sacker),
  leaves a grievance and, on conquest, revokes one charter level; at most
  once in 20 turns. The event cites the occupation or conquest.
- **Walls.** A city of rank 2 or more (or any city whose lord is at war)
  with 20 in its purse and no fortifications in its region starts them
  through the infrastructure pipeline (`pending_build`, three turns), paid
  from the purse. The campaign layer's fortification rules then apply.
- **Disease.** With `--epidemiology`, a region's susceptibility is
  multiplied by 1 + 0.5 x its urban share (city residents over region
  population). Epidemics in a city's region enter its history.

### Determinism, identity and signals

- Randomness: `random.Random(stable_hash_int("cities", <namespace>, seed,
  turn, settlement_id))` for petitions and revolts; no other draws. The
  Rust driver adds no draw.
- Identity: region index, civ index, `settlement_id`. A free city is a new
  civ index appended to `world.civilizations`, as secession does.
- `city_pull` is recomputed from persisted city state for every region
  batch; Rust resets it to 0 for a batch without the column. Nothing
  transient is left on the world.
- Accumulator categories: dues, fees, fines and loot `keep`; revolt and
  secession stability `guard-shock`; the free city's military and economy
  split `guard`. Merchant influence is written to the faction state and
  renormalized.

### Placement in the turn

| When | What |
| --- | --- |
| Phase 1 (`--epidemiology`) | urban susceptibility factor |
| Phase 2, after the goods-economy tax | dues owed last turn paid to lords (`keep`) |
| Phase 3b (`--finance`) | city credit factor in domestic credit |
| Agent tick | `city_pull` in the region batch; the urban driver |
| Phase 10, after diplomacy and agendas | `tick_cities` (order: falls, lord changes and sacks, residents and ranks, commerce and dues, unrest, walls, charters, revolts, pull, foundings, voice) |

### Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--cities` / `--no-cities` |
| World field | `WorldState.cities: CityState \| None` (presence = on), omitted while `None` |
| Default | off (`cities.DEFAULT_ENABLED_FOR_NEW_WORLDS = False`) for `execute_run`, batch and the live server; resumed worlds keep theirs |
| Gate runner | `scripts/m53b_run_validation.py --cities` forwards the switch |
| Bundle | `history[n].cities` (optional, omitted while off) |

With `--agents off`, a world that already carries settlements (a resumed or
forked world) keeps its cities; their residents stay at M56a's last
estimate, since nothing re-detects them. This is the mode the save/load
resume test uses.
