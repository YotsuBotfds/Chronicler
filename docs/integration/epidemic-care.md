# Epidemic care capacity (connected-world C2)

`--epidemic-care` (default off) lets each ruler fund, from its L9 local budget, named
carers for a region with a reported outbreak. Their farm time leaves farming, their
ordinary income share is withheld and replaced by a wage from the treasury, and the
patients they can serve, recorded as dated capacity, lower case fatality at the **next**
epidemic tick. The epidemic model still draws every death. Source:
`src/chronicler/epidemic_care.py` (state `epidemic_care_state.py`; the shared labour query
`labour_reservations.py`). Design: audit C section 6.3; lead decisions in the
[plan](../superpowers/roadmaps/connected-world-program.md), section 5.3.

## Switch and modes

| Option | Values | Meaning |
| --- | --- | --- |
| `--epidemic-care` / `--no-epidemic-care` | omitted = off | Enables C2 on a new world; an omitted switch keeps a saved world's state; `--no-epidemic-care` ends it (pending capacity is dropped). |
| `--epidemic-care-mode` | `care` (default), `cost_only` | `care`: the capacity lowers the next tick's fatality. `cost_only`: the cost control, with the same carers, farm time, withheld income and wages and no effect on fatality. |

Requirements (`feature_catalog.REQUIREMENTS`, checked by the run in
`epidemic_care.check_request`): `--agents hybrid`; `--local-budgets` (which itself needs
`--grain-reserves`); epidemiology with the contact ledger (on by default for new worlds);
and **not** `--wealth-accounting`: the A1 ledger does not itemize care wages yet, so the two
switches exclude each other (declared on both sides; the catalog's first exclusion pair).
A mode needs the switch, and a world keeps the mode it ran with. A saved world resumed
outside hybrid, without L9, without epidemiology or the ledger, or with A1 is refused with
the hint `pass --no-epidemic-care to end it`.

The switch follows the livelihoods convention (a boolean switch with a mode), so it shares
the framework's forwarding, manifest, resume-conflict and catalog paths; the lead's
decision named it `--epidemic-care {care,cost_only}`. `--epidemic-care` alone is `care`.

## The chain and its dates

| When | What | Where |
| --- | --- | --- |
| Phase 1 of T | The epidemic tick; outbreaks are reported. | `epidemiology.tick_epidemics` |
| Phase 10 of T | L9 proposes one divisible envelope per ruler covering every region of it with a reported outbreak (open episode) at T's tick, for turn T + 1. | `epidemic_care.BUDGET_PROVIDER` (appended to `local_budgets.PROVIDERS`, group `relief`) |
| Phase 2 of T + 1 | Carers named within the envelope and reserved; their farm time leaves the region's native farm labour. | `epidemic_care.prepare_phase2` |
| Phase 2 of T + 1, after the economy tick and every earlier package's charges | Each civ's wage bill quoted; if it passes, income share withheld for the next wealth phase, wages paid, capacity dated T + 1; if not, nobody of that civ is paid or withheld and no capacity is dated. | `epidemic_care.finish_phase2` |
| Phase 1 of T + 2 | The tick consumes the capacity dated T + 1 and multiplies case fatality. | `epidemic_care.care_factors` |
| Phase 10 of T + 1 | L9 settles the envelope from the turn's frame. | `BUDGET_PROVIDER.settle` |

Care therefore first acts two ticks after the outbreak is reported (the budget is decided
on dated information). The carers are sized at Phase 2 from the tick of their own turn.

## Funding (one authority)

Every coin goes through an accepted L9 envelope: no treasury authority of its own and no
flat charge. **One proposal per civ** (claim `epidemic_care:<civ>`) covers every region of
the civ with a reported outbreak. Its cost is the wages of the care time their infectious
people need, `sum of ceil(infectious / PATIENTS_PER_CARER x WAGE_MILLI)` milli-units rounded
up **once** to whole coins, divisible (a partial award funds fewer carers). L9 counts whole
coins, so up to one coin per civ and turn is reserved beyond the need; the unspent part of an
award lapses at settlement, as every envelope's does, but while committed it is budget the
same decision could not give another service (the screen measures care coins awarded,
executed and paid, and other services' coins). An earlier version proposed one envelope per
region, each at least one coin (review m1: on one development world 390 coins awarded
against 74 paid). The **commons'** stake (the constituency whose unit is food) is
the deaths care would avert at full coverage, from a persistence forecast of T's tick:

    deaths averted = CARE_CFR_REDUCTION x sum over pathogens of burden x n x SUBSTEPS x recovery x cfr

valued at `DEATH_FOOD_EQUIVALENT` food units each: L9's `horizon` (10 turns) times one
person's food need (`economy.PER_CAPITA_FOOD`, 0.5), i.e. 5 food units per death averted -
one person's whole subsistence over the budget horizon. It is declared, not calibrated, and
a weak analogy (it values a life by its own food over the horizon), chosen to put the stake on
the commons' unit; cheap care proposals can therefore outrank relief per coin, which is why
displacement is measured. The same valuation is used in both modes, so `cost_only` makes the
same budget decisions. L9's settlement records `spent` as the wages paid, floored to whole
coins; the civ's exact charge (whole units with a prepaid carry) is C2's wage ledger.
Under `--local-budget-mode fixed_shares` care shares the `relief` group's share, after
granary relief (service order).

## Carers

For each open envelope (one per civ), its regions most infectious first:

- **Who.** Living adult (age >= 20) farmers resident in the region who hold no work this
  turn, in ascending stable id (no random draw). Excluded (`labour_reservations.booked`,
  first reason wins): rural health care's prepared patients and caregivers; every holder of
  the shared native work registry (L1 workshop crews, L5 learners, RS1 apprentices, RS2/PL3
  repair crews, PL1 woodcutters); people away on a merchant trip; the enlisted; the mentors
  RS1 seated. C2 runs after every other package's Phase 2 (inserted before D2 and the A1
  ledger; a test fails if a switch with Phase 2 work is added after it), so it never
  displaces another package's workers; the native registry also refuses anyone holding
  registry work, rural health work or a teaching plan.
- **How much.** Each gives at most their own farm time (1 for a rural farmer,
  `cities.URBAN_FARM_LABOR[rank]` for an urban one), until the care time covers
  `infectious / PATIENTS_PER_CARER`, within the envelope's wages and the payer's projected
  treasury (plus its prepaid carry). What stopped it is recorded (`LIMITS`: `need_met`,
  `envelope`, `treasury`, `labour`, `no_patients`, `recipient_lost`). The envelope is shared
  by the civ's regions.
- **Labour.** Reserved in the shared work registry (category `repair`, the registry's
  fixed native categories; PL1's woodcutters use it too; `labour_reservations.booked` gives
  them their own label `registry_care`), all or none; the region's `farm_labor_factor` falls
  so that farmers x factor loses the care time (`recovery_crews.remove_farm_time`); nobody's
  time is used twice.
- **Side effects (part of care's cost).** Registry holders are skipped by campaign drafting
  (`war/armies.py`, the enlisted pool excludes them) and by academy teaching
  (`simulation.py`, the teaching plan excludes them), so a carer is neither drafted nor
  taught that turn. This holds in `cost_only` and `care` alike (EF - EC stays clean); the
  cost comparison (EC - E0) includes it.
- **Pay.** After the economy tick, once every earlier package has charged the treasury,
  each paying civ's bill is **quoted first**. A bill that passes: the same share of each
  carer's ordinary income is withheld by the next wealth phase (`extend_paid_work`), and the
  wage, `round(share x WAGE_MILLI)` milli-units, is paid by stable id through the shared
  payment seam: one bill per paying civ, purpose `care_wage`, batch `CARE_WAGE_BATCH + civ`,
  validated whole and settled exactly once per (turn, purpose, batch). A bill that would be
  refused pays and withholds nobody of that civ, its carers give no capacity, and L9 settles
  the envelope as a treasury shortfall (`unpaid_reason`, `refused:<reason>`,
  `unpaid_bills`). Their booking and farm time came before the economy tick and cannot be
  undone: that farm time is lost, recorded as `farm_time_unpaid`. The prepare-time quote
  against the projected treasury makes this rare (none in any run so far).

### The payment seam (`money.py`)

C2 appends purpose `care_wage`, the first a treasury may pay agents with
(`TREASURY_AGENT_PURPOSES`). Lines may be sub-unit: the bill is paid from the book's
prepaid carry for (civ, `care_wage`) first and then in whole treasury units, and the unspent
rest of the last unit stays prepaid (`units x 1000 + carry before = paid + carry after`).
What a wealth ceiling refuses, or an absent id cannot take, is not debited
(`return_to_payer`). The lane is Python only, so `care_wage` rides the native purpose
`repair_wage` (`money.NATIVE_ALIASES`), as PL1's and PL3's wages do; its batches start at
`0xC2000` and never meet RS2's (0), PL3's (1) or PL1's (2). Each flow carries its share of
the bill's treasury units (by what its agent took), so per-region totals add up; the carry
is the bill's. The prepaid carry (under one unit per civ) stays in C2's book if the switch is
ended (`--no-epidemic-care`); it is never returned to the treasury. The ledger registries
(`wealth_accounting_state`) register the purpose, a `care_wage` channel (listed in the A1
record's `parameters.channels`), the withheld channel `withheld_care` and the payer path; A1
does not itemize them (excluded).

## Capacity and the effect

`care_capacity[region] = (source_turn T, carers, care_time, patients = care_time x 5)` is
persisted on the state (checkpointed) and read by the tick of T + 1 only. The tick consumes
every row: one dated T is applied, any other date, or a region the world does not have, is
refused (`stale`, `future`, `out_of_range`) and recorded, never applied.

At the tick, before population change is absorbed:

- infectious people `I = sum over pathogens of burden x n` (the last tick's values);
- coverage `c = min(1, patients / I)` (0 without infectious people);
- `care` mode: factor `f = 1 - CARE_CFR_REDUCTION x c`, applied in the tick's modifier list
  exactly where practised medicine's factor is, with **one combined floor**:
  `max(techniques.CFR_FLOOR, techniques_factor x f)` (techniques off: `max(CFR_FLOOR, f)`, which
  never binds since `f >= 0.7`). A region with `f = 1` keeps the techniques factor exactly.
- `cost_only`: nothing is applied; the factor care would have applied is recorded.

Deaths are still drawn only in `epidemiology._apply_deaths` (no new mortality path); native
endemic (M35b) mortality, rural health care and injury episodes are untouched. A world
without the switch skips the tick hook and runs the tick unchanged; L9's provider list
imports the module in every L9 run, where the provider is inactive and proposes nothing.

## Constants (declared, not calibrated; none tuned on any run)

| Constant | Value | Why |
| --- | --- | --- |
| `CARE_CFR_REDUCTION` | 0.3 | Share of case fatality full coverage removes: the size of the strongest practised-medicine reduction already in the model (`techniques.CFR_REDUCTION`: vaccination 0.30; physicians 0.10; herbalism, lazarets 0.05). Basic nursing (water, food, warmth, cleaning) is the main pre-modern lever on dehydrating and wasting disease (flux, fever, pox) and weak against plague; one value for every pathogen (generous for plague and pestilence, arguably small for flux: per-pathogen values are an open item). |
| `PATIENTS_PER_CARER` | 5 per worker-turn | Rural health care's full care effect needs 0.2 worker-turn per patient (`HealthCareState.care_fraction`; recovery `1 + min(1, 5 x care)`), so one worker-turn serves 5 (an injury-nursing analogy). The need is sized with the same constant, so it sets care's labour and wage cost, not its effect: coverage is about 1 either way. |
| `WAGE_MILLI` | 500 per worker-turn | RS2's `WAGE_PER_WORK`, which PL1 woodcutters are paid. |
| `DEATH_FOOD_EQUIVALENT` | L9 horizon x per-capita food = 5 | The commons' unit is food; a death averted counts as one person's subsistence over the budget horizon. |
| `MIN_SHARE` | 0.001 | Least care time one person is named for (PL3's value). |
| `CARE_WAGE_BATCH` | `0xC2000` + civ | Keeps the native key log disjoint from other `repair_wage` users. |

## Records

`snapshot.livelihoods.epidemic_care` (stage `C2`, `source_turn` = the snapshot turn - 1):

- `tick`: the source turn's epidemic tick - `applied` per region (`source_turn` of the
  capacity, `patients`, `infectious`, `coverage`, `care_factor` applied, `would_be`,
  `techniques_factor`, `combined_factor`, `floored`, and after the tick `deaths`, `cases`,
  `infectious_after`), `refused` capacity, and `regions`: every infected region after the tick
  (`deaths`, `infectious_pt`, the tick's infectious person-turns `burden x n`, `cases`), in
  every care arm whether covered or not; None when no tick was observed;
- `frame`: the source turn's carers per envelope (`region`, `civ`, `commitment`, `envelope`,
  `infectious`, `need`, `eligible`, `carers` by stable id with `share`, wages due, paid and
  refused, `income_withheld`; `care_time`, `patients`, `farm_time_removed`, `limit`, `paid`,
  `unpaid_reason`);
  None when the turn's Phase 2 was not observed, `[]` a recorded zero;
- `ledger`: one row per civ that executed an envelope (`envelope_coins`, `due`, `paid`,
  `residual`, `treasury_units`, carries, `status`: `paid`, `nothing_due` or
  `refused:<reason>`);
- `capacity`: what the next tick will read; `counters` (`COUNTERS`); `parameters`.

The viewer's Epidemics panel shows it (`EpidemicCare.tsx`, reader `lib/epidemicCare.ts`
through `recordReading.ts`): off in the run, absent, malformed, not observed, a recorded
zero and the record are named apart, never shown as 0.

## C3 invariants (tested)

`tests/test_epidemic_care.py`: epidemic code never creates or closes an `InjuryEpisode`;
health care never reads or writes epidemic rows or fatality; care changes a parameter and
never deaths (no drain, staged death or population write in C2); carers are never injury
patients or caregivers in the same turn; endemic severity and population are unchanged by C2.

## Deferred, with disposition

- **Supplies (C2b, patient rations from market grain).** Deferred: a real food cost through
  the existing food and market authorities needs its own receipts and a buyer (household
  retail or the commons); not small. Recorded in the plan.
- **Sanitation (C2c).** Waits for B3's infrastructure service level (B3 owns condition,
  workers, materials and budgets); C2 invents no infrastructure.
- **Crowding and displacement.** Waits for the lead's displacement contract (shared with D3
  and A6): the hybrid displaced share is a transient bridge attribute that would first need
  a dated, persisted copy.
- **A1 itemization.** `care_wage` and `withheld_care` are registered; itemizing them in the
  ledger changes A1 frames (a withheld package row), so the switches exclude each other
  until the lead integrates it.

## Verification

See the C2 section of
[`connected-world-screens-cw5c.md`](../superpowers/progress/connected-world-screens-cw5c.md)
for the commands and results (focused tests, the offline lane, witness suites, feature-off
identity, enabled exact resume, viewer) and the CW5c preregistration.
