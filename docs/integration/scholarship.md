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
| Default | TBD |
| Gate runner | `scripts/m53b_run_validation.py --scholarship` forwards the switch and records it in `run_manifest.json` |
| Bundle | `history[n].scholarship`: living seats (id, name, kind, region, ruler, level, scholars, great scholars, refugees and unpaid upkeep while present), the fallen count, counters; omitted while off; the viewer reads `world_state.scholarship` for each seat's record |
| Analytics | `generate_report` gains `scholarship` for runs that carry it |
| Old saves | load with `scholarship` None |

## A seat's history

TBD

## What seats do to techniques and archives

TBD

## Gates

TBD

## Feature-off identity

TBD

## Tick time

TBD

## Bundle size

TBD

## Narration

TBD

## Tests

TBD

## Verification

TBD

## Open items

TBD
