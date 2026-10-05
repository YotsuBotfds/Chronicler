# Adjacent mutual aid prototype

Base: public main `edf7299` (includes PR13 terminal living-population validation).
Branch: `experiment/social-aid`. This patch is unrelated to private frozen
candidate `b665e198`; experiments across those baselines are not comparable.

## Source findings and scope

`traditions.py` already counts famines and awards `food_stockpiling`, whose
`apply_soil_floor()` raises soil to 0.25. Stockpiles, trade, decay, and conservation
are implemented by the goods economy. There is no repeated-stress coordination
rule that moves existing regional food with a fiscal cost. The Phase 8 governance
roadmap proposes treasury-constrained institutions, but does not implement the
institution lifecycle. This prototype models one local coordination response;
it does not claim to implement M63 or Ostrom governance.

`run_turn()` currently runs goods economy only with an agent-backed snapshot.
The patch therefore operates in hybrid, demographics-only, and shadow modes;
shadow remains experimental and is not an aggregate control for this feature.
The CLI rejects enabled aid with agents off. The only native change is a read-only
stock commitment query; no native kernel, ecology, fertility, migration, merchant
planning, trade route, or existing tradition changes occur.
Existing agent behavior can react indirectly to changed food sufficiency.

## Mechanism and tradeoffs

Phase 2 observations at N affect dispatch before input packing at N+1. Three
consecutive observations below food sufficiency 0.8 activate eligibility. At 0.8
or above the stress streak resets. Missing observations, absent inhabitants,
ownership changes, and gaps in observed turns break continuity. Social state and
the once-per-turn dispatch guard serialize deterministically. Python saves do
not serialize the native agent pool, merchant cargo, RNG state or delivery buffers;
this patch does not establish full hybrid checkpoint continuation.

Eligibility requires both `region.controller` and the controller's region list
to agree, occupied regions, fresh prior-turn observations, finite nonnegative
food stocks, and mutual physical adjacency inside the same polity. A donor must
have prior-turn sufficiency at least 1.0. It retains two current turns of food
demand in **uncommitted stocks**, and can send at most 25% of its current one-turn
demand across all edges. Demand uses agent snapshot counts and the native
`economy.per_capita_food` tuning override.

Recipient delivered need is the smallest of prior-turn shortfall scaled to
current demand, current uncommitted-stock shortfall below one demand, and 50% of one-turn
demand. Recipients sort by prior sufficiency then name; donors sort by name.
This deterministic priority can disadvantage later tied recipients; it does not
provide equitable pro-rata allocation. Received food cannot be forwarded in the
same dispatch. Existing goods are sent in the donor's uncommitted composition.
Hybrid dispatch excludes per-good Loading reservations and departures not yet
debited by the next economy tick. It does not count pending returns or arrivals
as available and does not subtract older already-debited in-transit cargo twice.
Enabled hybrid aid fails before mutation when this accounting is unavailable or
incomplete. Abstract economy modes ignore virtual shadow-cargo reservations.

Treasury pays `ceil(sent_units * 0.1)` for every edge, with minimum cost 1.
Spending respects existing queued treasury `keep` mutations and cannot use
same-turn future tax receipts. Small deliveries are fiscally inefficient.
Transport capacity represents a capped public logistics effort; it is not
merchant labor or labor removed from production. The cost is a sink representing
coordination and transport overhead; it is not paid to agent wallets. Sending
can reduce donor reserves and future resilience; scarcity or fiscal exhaustion can
leave activated recipients unaided. This is not a universally beneficial bonus.

Transit uses existing per-good one-edge decay (grain 5%, fish 8%, botanicals 4%,
exotic 6%, salt 0%). Salt counts as food because the existing economy does so.
No goods are created. `mutual_aid_last_transfers` records per-good sent/received,
lost goods, costs, and controller. `mutual_aid` events enter the existing timeline.
The native economy conservation ledger begins **after** aid changes its inputs.
For a whole Phase 2 balance, include aid transit losses separately; adding them
to native counters would double-count the wrong accounting boundary. Full stock
balance is `old + production + clamp_floor_loss = new + consumption + losses +
overflow + in_transit_delta`, where clamp-floor corrections add mass by raising
negative intermediate stocks to zero. A nonzero correction must be reported,
not interpreted as food saved by coordination. Aid itself cannot overspend free
stocks. Cargo reservations remain in stock; pending departure/arrival/return
flows cross the economy's stock accounting boundary through `in_transit_delta`.

Stockpile food sufficiency and ecology's yield-triggered famine checks are
separate mechanisms. Aid changes the former without changing effective resource
yields or yield-triggered famine events. Food relief does not prove famine
suppression; no claim about birth rates or demographic stabilization is made.

## Run and verify

```bash
uv sync --python 3.13 --group dev
.venv/bin/python -m pytest -q tests/test_mutual_aid.py
.venv/bin/python scripts/mutual_aid_example.py --backend python
# After building chronicler-agents with maturin:
.venv/bin/python scripts/mutual_aid_example.py --backend native
chronicler --agents hybrid --mutual-aid --simulate-only --seed 42 --turns 5
```

The flag defaults off for new worlds. Saved enabled state survives resume unless
explicitly overridden with `--no-mutual-aid`. Functions are strict no-ops while
disabled, including when saved institution memory exists. There is no external
service in the paired example. Its five economy steps keep population and agent
occupations fixed to isolate food flows. Python and native fixtures are evaluated
within their own backend; different population/occupation initialization means
their outputs should not be compared as matched treatments.

The bounded native adversarial follow-up is runnable with:

```bash
.venv/bin/python scripts/mutual_aid_adversarial.py --enabled --treasury 2
.venv/bin/python scripts/mutual_aid_adversarial.py --enabled --treasury 20
.venv/bin/python scripts/mutual_aid_adversarial.py --disabled --treasury 2
CHRONICLER_UNTOUCHED_SOURCE=/path/to/edf7299-export \
CHRONICLER_UNTOUCHED_NATIVE=/path/to/edf7299-native-package \
  .venv/bin/python -m pytest -q tests/test_mutual_aid_adversarial.py
```

It runs exactly 15 economy/agent-behavior turns per case. Cargo reservations and
pending departures arise from the existing native merchant pipeline; no native
ledger injection is used. Population, occupation and merchant trips may evolve
through unmodified agent behavior. There is no ecology tick or macro fiscal
income in this fixture. The native economy's tax outputs are recorded but not
credited: initial treasury 2 or 20 represents a finite earmarked relief budget,
not ordinary full-world treasury dynamics. Aid transport still incurs every
rounded treasury debit. No stock or money is injected between turns.

Initial donor grain is 35. Explicit scenario changes raise donor effective yield
from 0.5 to 4 at turn 3, change recipient primary resource from ore to grain with
yield 2 at turn 5, then set recipient grain yield 0 at turn 6. Every produced unit
remains in the native production ledger. These interventions exercise the social
response; they are not changes to ecology, fertility or merchant planning.

The recipient records stress streaks 1/2/3 on turns 0/1/2. Turn 3 aid is blocked by
the donor reserve. At turn 4, real reserved plus pending-departure grain limits
delivery to the exact remaining surplus above two current demand turns. Aid at
turns 4 and 5 pays one treasury unit each and loses grain in transit. Treasury 2
then exhausts. Recovery resets the streak on turn 5; a later recovery resets it
again on turn 10. Fresh stresses on turns 11/12/13 reestablish eligibility, and
turn 14 dispatch is blocked by the exhausted budget. With treasury 20, recovery
still prevents aid despite available funds and aid resumes on turn 14. The two
funding cases have identical physical histories through turn 13.

There is no fixed timed cooldown: recovery clears the streak and three new
consecutive stressed observations are required. A crop shock can make aid paid
on turn 5 redundant before same-turn production; the fixture includes this lagged
allocation tradeoff. Tests require actual cargo commitments, protect them and
the donor reserve at dispatch, prove query state is unchanged by aid, verify
integer funding/transit costs, and assert zero clamp-floor corrections and a
whole stock/cargo residual below 5e-5 each turn. The reserve claim applies before
ordinary consumption/storage loss, not to final post-economy stocks.

The disabled 15-turn trajectory additionally compares untouched public Python
source and its original native build against this feature build. Complete
normalized worlds, full native snapshots, regional stocks/sufficiency, all
native conservation counters, cumulative delivery diagnostics and trip stats
must match. Only four new default metadata fields and the new read-only cargo
diagnostic unavailable on the old native build are excluded. Full hybrid
checkpoint continuation remains untested and is not implied by this uninterrupted
evolving-pool trajectory.
Adjacent trips yield zero net `in_transit_delta` at settled turns in this replay;
nonzero long-lived cargo deltas and multi-edge trips are not covered by it. The
existing Rust query fixture separately covers pending arrivals/returns and older
in-transit cargo without double subtraction, but is not a whole transport replay.

Deterministic tests cover activation timing, threshold recovery, discontinuity,
ownership reset, insufficient funds and donor reserves, shared donor capacity,
recipient bounds, sorted allocation, per-good losses, queued fiscal costs,
observation/dispatch idempotence, social-state save/load, disabled no-op, CLI
tristate behavior, unmodified Python economy consumption and conservation, and
native input packing plus consumption and conservation. The native query has a
Rust fixture proving read-only handling of reserved cargo, pending departures,
older in-transit cargo, pending arrivals, returns, and mode-specific zero outputs.

## Evaluable experiment design

First use the committed five-step two-region fixture, paired off/on from identical
initial state on this exact public baseline. Do not run a broad seed sweep. Its
mine has no food production; its granary has real existing stores and food
production. Verify no dispatch at turns 0–2, first dispatch at turn 3, improved
recipient food sufficiency, reduced donor stocks, paid treasury, and per-step
goods balance including transit losses. Repeat with treasury 0 to establish no
effect, then treasury 1 to show spending exhausts and later relief stops. The
default donor yield 0.5 exposes a final-stock tradeoff; `--donor-yield 1` is an
abundant-production variant where relief may instead reduce discarded overflow.
Neither outcome is assumed universally. Change
recipient production to restore sufficiency at least 0.8 and verify the next
turn has no dispatch. Remove adjacency or donor surplus to verify activation
alone does not guarantee relief.

Record dispatch count, food sent/arrived/lost, fiscal expenditure, donor reserve
floor, each region's sufficiency/stress streak, unmet recipient demand, and
conservation residual. Pass conservation and cost gates before judging benefit.
Any off/on physical economy change before eligibility, transfer without a debit, negative stock,
aid across ownership/adjacency boundaries, or unexplained goods balance fails.

After those gates, use one short hand-authored hybrid replay with two freshly
initialized native pools from identical Python initial state and seed, with only
the flag differing, on the same build. Do not call this full native continuation
from a Python checkpoint. Record indirect behavior and fiscal effects alongside food relief. Do not
infer population stabilization, collapse prevention, calibrated institutional
learning, or cross-baseline improvement from the economy fixture. The prior-turn
rule cannot anticipate current production or new disasters; it may misallocate
aid that a recovering recipient would not need. The reserve protects present
demand, not future crop failure. Parameters remain hypotheses requiring later
calibration, and resource stress other than food is outside this patch. Repeated
threshold cycling and persistent name-priority starvation are possible harms.

Disabled-feature regression controls must additionally use untouched `edf7299`
Python source and its untouched native build. Compare complete normalized world
state (excluding only the four newly introduced default metadata fields), events,
and native agent snapshots after the same small seeded run. Comparing only off
and on variants of this patched checkout cannot establish baseline preservation.
