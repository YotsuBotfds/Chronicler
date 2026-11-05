# Costly voluntary relocation (L7, `--relocation-costs`, default off)

Sprint 2, wave 2B, of the livelihoods/commons plan
([plan](../superpowers/roadmaps/livelihoods-commons-sprint2.md)). This page
records what the package implements, what it does not, and its evidence.

## Switch and modes

`--relocation-costs` requires `--agents hybrid`. It is refused together with a
household-mobility liquid requirement, because both use the same native gate.
`--relocation-mode` chooses:

| Mode | Gate | Payment |
| --- | --- | --- |
| `paid` (default) | the fare must be held | adult movers pay after the move is applied |
| `assisted` | as paid, or held with the destination ruler's assistance | movers pay the fare minus assistance; the ruler pays the assistance |
| `liquidity_only` (control) | the fare must be held | nothing is paid: a liquidity restriction alone |

A world that never enabled the switch has no container, snapshot key,
checkpoint flag or manifest entry. The snapshot key is
`snapshot.livelihoods.relocation_costs`. The livelihoods protocol derives the
CLI flag, the module and the key from one switch name, so the brief's
suggested `relocation` key became `relocation_costs`; the modules are
`relocation_costs.py` and `relocation_costs_state.py`.

## What is priced, and what is not

The priced unit is one ordinary household move per turn, an adjacency move.
The household is the consolidator's group: a moving lead, plus the spouse and
dependent children it actually linked, all with the same origin and
destination. These are the same groups the liquid-reserve gate uses. The fare
is `FARE_MILLI` (1.0 wealth unit) per person, children included.

The gate is in `chronicler-agents/src/relocation.rs` and runs after household
consolidation:

- **Liquidity.** It sums the adult movers' liquid wealth in whole
  milli-units, as the wealth transfer will debit them.
- **Assistance.** In assisted mode, a household short of the fare is offered
  `ASSIST_MILLI` (0.5) per person, never more than the fare. The offer comes
  from the destination ruler's budget for the turn and is reserved in the
  gate's deterministic order: origin bucket, then origin, destination and
  stable id.
- **Blocking.** A household that cannot cover the fare is blocked. Its moves
  are removed before the apply phase, and its members' other decisions
  (rebellion, occupation switch) are restored as the liquid-reserve gate does.

Never charged:

- moves the consolidator cancelled (a rebelling spouse, a contested
  destination), which never reach the gate;
- blocked moves;
- duplicated proposals (one group per person);
- merchant trips, refugees and conquest flows, which do not move agents
  through this path.

An unknown or non-adjacent route, or a member on a trip, passes unpriced, as
the liquid-reserve gate lets them pass. A return is a new move and pays again.

## Payment, arrival and service are recorded separately

- **Arrival.** After the apply phase (the only native relocation of ordinary
  agents), each passed group is marked applied only when every member is alive
  in the destination. A passed assisted group that was not applied releases its
  assistance. The native receipt is taken once by Python and records:
  - each group: members, adults and their gate liquidity, children, fare,
    assistance, payer, reason, applied;
  - alive counts by region before the gate and after the moves. Only moves
    change these counts in between.
- **Payment, movers.** Right after the tick and before Phase 10 wages, the
  movers' share (fare minus assistance) is debited from the adult movers.
  - It is split pro rata by gate liquidity, with the largest remainder going
    to the lower stable id on ties, through `transfer_wealth` under the
    appended purpose `relocation_fare` (index 1), batch 0, once per turn.
  - Children are counted in the fare but never debited.
  - Whatever the transfer cannot take is recorded as the household's
    residual, never forgiven silently: a mover who died later in the same
    tick (status `absent`), or less wealth.
  - The fare goes to a disclosed travel-cost sink (provisions, carts,
    tolls). There is no recipient.
- **Payment, assistance.** In Phase 10 (`phase10_before_reserves`, keep
  accumulator), each destination ruler is charged once, and only for applied
  assisted moves. Settlement first re-checks two things:
  - that the same civilization still rules the destination. A conquest,
    secession or revolt in Phase 10 politics refuses the charge
    (`controller_changed`);
  - that its projected treasury covers the charge, otherwise
    `treasury_short`.

  A refused grant is recorded as unfunded and the move stands. The treasury
  pays whole units (the ceiling of the grant); the rounding is disclosed in
  `assistance_rounding_milli`.
- **Service.** The next turn, last turn's tracked arrivals (up to 256) get a
  receipt for the region they now live in. It always records the food signal
  they read. With `--food-allocation`, it also compares their own rations
  with the other residents' (`relocation.rs::observe_rations`, read right
  after the allocation). Nothing is granted on arrival: arrivals share the
  destination's finite food, work and care.

## Receiving pressure

For every region a move touched in a turn, the record shows:

- arrivals: people, households and assisted households;
- departures;
- alive counts before the gate and after the moves, against carrying
  capacity (people per capacity);
- the turn's food sufficiency.

Jobs, care and learning are not given to arrivals. Arrivals face the same
occupation targets, health care and learning cohorts as residents. The record
reports crowding and food, the signals arrivals actually read.

## Budgets and parameters

The assistance budget for each civilization and turn is `ASSIST_SHARE` of its
treasury minus other pending Phase 2 livelihoods bills
(`commons_rules.pending_phase2_bills`). It is computed before the tick, after
Phases 1–9 keep changes have been applied. The lead plans to rewire this into
one ledger.

Declared modeling choices, not calibrated:

- `FARE_MILLI` 1000 (one wealth unit, about three turns of a farmer's
  ordinary income);
- `ASSIST_MILLI` 500 per person;
- `ASSIST_SHARE` 0.05;
- `MAX_HOUSEHOLDS` 64 (households kept per turn);
- `MAX_TRACKED` 256.

## Determinism and checkpoints

No randomness is drawn, and the order is deterministic by stable id. The
native policy and receipt are transient and never checkpointed. Python
settlement is once per turn across exact checkpoints (`last_settled_turn`,
`last_assistance_turn`), and the native wealth-transfer key log refuses a
repeated key. The previous turn's tracked arrivals, and their origins (to
name returns), are persisted for the service receipt.

## Evidence

All checks ran on 2026-11-05 on the branch source (from integration head
`e555b0db`) with the extension built fresh from it.

### Tests

- **Rust** (`cargo test --locked --lib relocation`), 6 tests:
  - a household pays per person, children included, from adult liquidity;
  - a short household is blocked and never applied;
  - identical short households move only with funded assistance, in gate
    order, and an unapplied assisted move releases its assistance;
  - unpriced routes and regions without a payer;
  - a zero fare passes everyone; install validates; the tick check refuses a
    policy for another turn or one alongside the liquid reserve;
  - tracked arrivals' rations against residents'.

  The whole lib unit suite passes (694 tests).
- **Offline** (`tests/test_relocation_costs.py`), 14 tests with a native
  stand-in:
  - prerequisites;
  - paid: pro-rata debit, the child never debited;
  - the liquidity-only control;
  - identical short families under assisted and liquidity-only;
  - the bounded budget in gate order;
  - cancelled and unapplied moves charged nothing;
  - death after the move leaving a residual;
  - conquest between plan and settlement;
  - a short treasury at settlement;
  - a return paying again;
  - service receipts with and without rations;
  - once-per-turn settlement and exact round trips;
  - dated snapshots that keep unknown distinct from zero;
  - the split rule;
  - append-only codes.

  They pass under the bounded lane's offline guard (guard PASS).
- **Native** (`tests/test_relocation_costs_native.py`), 8 tests on template
  seed 1:
  - **Live wealth.** Over 14 turns, every debit equals the drop in the live
    adult's wealth. Blocked households stay at home and pay nothing. Applied
    households are at their destination. Children count in the fare and are
    not debited. For each region, after − before = arrivals − departures.
  - **Assistance against liquidity alone.** One exact checkpoint is forked
    into liquidity-only and assisted arms. The same short household, with the
    same members and gate liquidity, stays at home in one arm. In the other it
    moves with assistance, pays the rest, and its ruler is charged.
  - **Conquest.** A declared controller transition in Phase 10, before
    settlement, refuses the charge (`controller_changed`).
  - **Death residual.** In turn 11 a mover died later in the tick of the move,
    leaving an `absent` residual. Debited plus residual equals the fare due.
  - **Pressure.** Region-turns exist where a move worsened destination
    congestion and where one relieved origin pressure.
  - **Exact resume.** A run resumed through the CLI from the turn-5
    checkpoint has the same history and world as the straight run.
  - **Identity.** A run without the switch equals one with
    `--no-relocation-costs`. Liquidity-only with a zero fare equals the run
    without the switch (history identical apart from the new key; nobody
    short).
  - **Native refusals.** The tick refuses a policy for another turn and one
    alongside the liquid reserve. Purposes are `["workshop_wage",
    "relocation_fare"]`.

  Related suites also pass (44 tests): household mobility, workshop payroll,
  learning cohorts, food allocation, M57b households and merchant mobility.
  The payroll native test's exact purposes assertion now checks the
  append-only prefix.
- **Viewer.** `src/lib/__tests__/relocation.test.ts` (4 tests) and
  `src/components/systems/__tests__/Relocation.test.tsx` (2 tests) pass;
  lint and build pass. The component is not mounted; the lead mounts it.

### Feature-off identity against the integration head

Template seed 1 was run for 200 turns two ways: the integration-head source
(`e555b0db`) with its own extension, and the branch source and extension with
the switch off. The bundles are byte-identical (without
`metadata.generated_at`). They are also identical with `--cities --workshops
--food-allocation`.

### Development funnel (template seeds 1–3, 200 turns)

Run with `scripts/relocation_costs_funnel.py run OUT --seeds 1,2,3`. Each arm
runs its own trajectory, so households are counted per arm.

| Seed 1 | paid | assisted | liquidity only | assisted + L2 |
| --- | --- | --- | --- | --- |
| Households proposed | 1,341 | 1,731 | 1,865 | 1,993 |
| Passed with own means | 528 | 868 | 879 | 980 |
| Passed with assistance | 0 | 69 | 0 | 71 |
| Blocked, short | 811 | 791 | 985 | 940 |
| Unpriced (trip) | 2 | 3 | 1 | 2 |
| Moved (people; children) | 530 (1,069; 168) | 940 (2,012; 388) | 880 (1,908; 359) | 1,053 (2,262; 451) |
| Fare due / debited / residual (units) | 1,060 / 1,044.2 / 15.8 | 2,003 / 1,917.7 / 22.3 | 1,903 / 0 / 0 | 2,255 / 2,147.3 / 39.7 |
| Assistance granted = charged (units) | 0 | 63 | 0 | 68 |
| Households with a residual (deaths) | 14 | 23 | 0 | 31 |
| Returns | 192 | 222 | 258 | 281 |
| Region-turns: congestion worsened / origin relieved | 21 / 28 | 43 / 53 | 22 / 27 | 30 / 43 |

Seeds 2 and 3:

| Seed | Arm | Proposed | Assisted | Short | Moved | Debited | Assistance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | paid | 761 | 0 | 356 | 405 | 937.2 | 0 |
| 2 | assisted | 962 | 31 | 458 | 504 | 1,148.0 | 36 |
| 2 | liquidity only | 828 | 0 | 359 | 469 | 0 | 0 |
| 3 | paid | 2,016 | 0 | 864 | 1,152 | 2,494.9 | 0 |
| 3 | assisted | 1,616 | 88 | 526 | 1,090 | 2,337.6 | 120.5 |
| 3 | liquidity only | 2,088 | 0 | 830 | 1,258 | 0 | 0 |

- **Accounting.** In every arm, fare debited plus residual plus assistance
  equals fare due. Every residual is a mover who died later in the turn of the
  move.
- **No natural refusals.** No assistance charge was refused in these runs: no
  controller changed between plan and settlement, and no treasury fell short.
- **Arrivals' rations.** With the L2 allocation (`floor_means`), last turn's
  arrivals received less food than residents of the same regions:
  - seed 1: 0.62 against 0.70 (1,381 arrival observations);
  - seed 2: 0.48 against 0.54;
  - seed 3: 0.63 against 0.71.

  Arrivals compete for the same food and come away poorer after paying the
  fare.
- **Congestion example** (seed 1, paid, turn 1). One arrival raised region 6
  from 1.27 to 1.30 people per unit of capacity.
- **Relief example** (same turn). A departure lowered region 3 from 2.00 to
  1.97.
- **What the gate does.** The fare blocks about 40–60 % of proposed
  households in these poor template worlds. That is a large behavioural
  change, and it is not a welfare claim. The held cohort was not run.

## Limits and open questions

- One adjacency move per household and turn. There is no travel duration
  and no remittances.
- Assistance is a flat per-person offer to households short of the fare,
  funded by the destination's ruler. Budgets use the interim pending-bills
  helper.
- Assistance is reserved before the agent tick but charged in Phase 10,
  after cities, movements, guilds and academy procurement have already spent
  from the same projected treasury. If they leave it short, the charge is
  refused (`treasury_short`), recorded, and the move stands with that share
  unfunded. A lead review on 2026-11-05 found this occurring in an
  all-switches procedural development world (2 units refused over 200 turns);
  the held screens count it. Charging right after the tick would close the
  gap, but the after-tick hook has no accumulator, so it is left as a declared
  limitation. With `--local-budgets`, L9 reserves the assistance ceiling as an
  obligation before any envelope, so its envelopes cannot claim the same coins.
- The receiving-pressure record reports crowding and food. Work, care and
  learning are what the existing consumers already apply to everyone; there
  is no separate arrival metric for them.
- The liquid-reserve gate and the fare cannot run together.
