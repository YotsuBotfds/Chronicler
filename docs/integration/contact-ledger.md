# Contact and trade-flow ledger

Status: implemented in `src/chronicler/contact_ledger.py`, behind
`WorldState.contact_ledger` (CLI `--contact-ledger` / `--no-contact-ledger`;
persisted in `state.json`, so resume keeps the setting). With the switch off no
ledger code runs and every output is byte-identical to the base branch.

## Why

`Relationship.trade_volume` only grew when a civ-level TRADE action succeeded
and never decayed, while agent merchants made thousands of real deliveries that
nothing outside the goods economy could see. Everything gated on it (movement
spread, the merchant great-person trigger) measured "ever traded once" rather
than live commerce. Several systems also re-derive "who is in contact with
whom" on their own (pandemic spread over trade adjacency, route-based partner
counts). The ledger is one shared, decayed contact substrate those consumers,
and future ones (epidemics, technique diffusion, languages, diasporas), read.

## State and update

A sparse, directed region x region matrix with four channels, stored as rows
`(src_region_idx, dst_region_idx, trade, people, soldiers, pilgrims)` sorted by
`(src, dst)` (region identity is its index in `world.regions`):

| Channel | Source | Unit |
| --- | --- | --- |
| trade | agent modes: every merchant delivery the next economy tick consumes, read without draining through the new native `AgentSimulator.get_pending_arrivals()` (`source_region`, `dest_region`, `good_slot`, `qty`), so each delivery is counted exactly once; `--agents off`: a route proxy, `OFF_ROUTE_FLOW * (0.5 + (economy_a + economy_b)/200)` per boundary pair of each goods trade route (`decompose_trade_routes`, both directions), plus `OFF_INTERNAL_FLOW` per intra-civ adjacency (internal commerce, dependence denominator only); every mode: `TRADE_ACTION_VALUE` on the capital-to-capital edge per successful TRADE action | goods units (merchant cargo is at most 1.0 per trip) |
| people | agent migration events of the turn (`region -> target_region`, via `history_index`), plus one per held hostage (origin capital -> captor capital) | persons |
| soldiers | campaign armies in the field (`home_region -> region`) | soldiers |
| pilgrims | great persons on pilgrimage (current region -> shrine) | persons |

Once per turn, after every phase (just before narration), `update_contact_ledger`:

1. multiplies every edge by its channel retention `DECAY = (0.9, 0.9, 0.8, 0.9)`
   (trade/people/pilgrims half-life about 6.6 turns; soldiers 3.1);
2. adds the turn's inputs (Phase 2 inputs and TRADE bumps were queued on the
   private `world._contact_pending`; migrations, armies, pilgrims and hostages
   are read from state now) and clears the transient queue;
3. rounds to 1e-6 and drops edges whose channels are all below 0.01;
4. aggregates civ pairs with the region controllers of that moment (undirected
   `pairs` rows `(civ_a, civ_b, trade, people, soldiers, pilgrims)` with
   `civ_a < civ_b`) and each civ's recorded commerce (internal plus external
   goods flow), and saves them, so consumers next turn and a resumed run see
   exactly the same aggregates;
5. sets `trade_volume = round(F_ab)` on every relationship (both directions).

Cost is O(edges + inputs + civ pairs) per turn; nothing region x region dense is
ever built. Everything iterates in sorted order and uses no RNG.

## Civ aggregates

* `F_ab = civ_flow(world, a, b)`: decayed goods value crossing a <-> b.
  `trade_volume` keeps its field and int type but now means `round(F_ab)`;
  a TRADE action adds `TRADE_ACTION_VALUE` (1.0) instead of `+1` forever, so
  real merchant/route flows dominate.
* `D_ab = dependence(world, a, b) = min(1, F_ab / max(COMMERCE_FLOOR, commerce_a))`:
  the share of a's recorded commerce that crosses to b. Commerce stands in for
  economic output: the goods economy exposes no per-civ production, and the
  recorded flow is in the same units as `F_ab`.

## Query API

```python
from chronicler import contact_ledger as cl
cl.ledger_enabled(world)
cl.flow(world, region_a, region_b, "trade", directed=False)   # names or indices
cl.region_contact(world, a_idx, b_idx)          # weighted, all channels
cl.region_partners(world, region_idx)            # regions with any contact
cl.civ_flow(world, civ_a, civ_b, "people")
cl.civ_contact(world, civ_a, civ_b)              # weighted, all channels
cl.dependence(world, civ_a, civ_b)
cl.top_partners(world, civ, "trade", n=5)
cl.trade_partner_count(world, civ)               # living partners with F >= 1.0
```

`CONTACT_WEIGHTS = (1.0, 1.0, 0.25, 2.0)` (trade, people, soldiers, pilgrims)
define the generic contact intensity. All queries return 0 / empty with the
ledger off.

## Consumers changed (each guarded by `ledger_enabled`)

| Consumer | Before | With the ledger |
| --- | --- | --- |
| `action_engine.resolve_trade` | `trade_volume += 1` both ways, forever | queues `TRADE_ACTION_VALUE` on the capital edge; `trade_volume` is derived at turn end |
| `movements._process_spread` | needs `trade_volume > 0`; chance `trade_volume * compat / 100` percent | needs any recorded contact; chance `min(20, 0.5 * civ_contact) * compat / 100` percent (ideas travel with goods, migrants, soldiers and pilgrims); same hash roll. The cap keeps the legacy per-pair magnitude: at `min(50, 1.0 * contact)` almost every contact adopted at once, and the late adopters revived the dormant schism/co-adoption drift (variant counters lag the origin's, -5 drift per turn per schismatic pair) strongly enough to double federation churn |
| `traditions.update_event_counts` (merchant great person, `high_trade_route_turns`) | counts relationships with `trade_volume > 0` (ever traded, dead partners included), needs 4 | counts living partners with `F_ab >= 1.0`, needs `MERCHANT_HUB_PARTNERS = 3`; the consecutive-turn rule in `great_persons.py` is unchanged. Neither the legacy rule nor a live 4-partner rule ever fired in the 20-seed hybrid subset (worlds hold two or three living civs for most of the run) |
| disposition drift (`apply_trade_warmth`, Phase 10 right after `apply_value_drift`) | none | partners with `F_ab >= 1.0` add +1 drift per turn (+2 when either side's dependence is at least 0.25) in both directions; crossing the usual 10 upgrades one step; trade never lifts a pair above FRIENDLY |
| embargo (`_resolve_embargo`) | target loses 5 (2 with banking) stability | target loses `round(10 * D_target,imposer)` more; the imposer loses `round(10 * D_imposer,target)` (signal category under hybrid) |
| war declaration (campaign `declare_or_press_war` and the instant WAR path) | none | each side loses `round(8 * D)` stability by its dependence on the other: the severed trade shock |
| pandemic spread (`emergence.tick_pandemic`) | every adjacent region whose controller is a trade-route partner of the source's controller, deterministically | every region with recorded contact (any channel, either direction, adjacent or not) under a different controller, with probability `1 - exp(-contact / 5)` (one draw from the existing spread stream per exposed pair); severity, duration and scientist rules unchanged; spread stays between controllers because the per-civ damage model has no per-region scaling for intra-civ chains |

Religion and culture diffusion needed no change: conversion signals are
region-local (priests present in the region) and the native culture/knowledge
ticks do not read adjacency or `trade_volume`. They are follow-up consumers.
Pandemic origin eligibility and the TRADE action's partner search still use the
route graph (unchanged).

## Switch, defaults, persistence

| Surface | Value |
| --- | --- |
| CLI | `--contact-ledger` / `--no-contact-ledger` (`BooleanOptionalAction`) |
| World field | `WorldState.contact_ledger: ContactLedgerState \| None` (presence = on) |
| Default | `contact_ledger.DEFAULT_ENABLED_FOR_NEW_WORLDS` for worlds created by `execute_run` and the live server; resumed, forked and caller-supplied worlds keep their own setting; `WorldState`'s own default stays off |
| Gate runner | `scripts/m53b_run_validation.py --contact-ledger` forwards the flag to every run |

`None` is omitted from serialized output (`state.json`, bundle `world_state`)
and `TurnSnapshot.contact` is omitted while `None`, so feature-off artifacts
keep their exact bytes and pre-ledger saves load unchanged. The derived lookup
caches on `ContactLedgerState` and the transient input queue never affect
equality or serialization. A save/load round trip continues bit-identically
(off mode tested; hybrid resumes rebuild the agent pool, as for every other
system).

## Viewer bundle and analytics

`history[n].contact` (only with the ledger on): `edges`, `contact_pairs`
(living civ pairs with any contact), `trade_pairs` (living pairs with
`F_ab >= 1.0`), `inflow` (this turn's additions per channel), `stock` (decayed
totals per channel) and `top_trade_pairs` (top 5 by `F_ab` with both
dependences). `world_state.contact_ledger` carries the full matrix and civ
aggregates. `analytics.generate_report` adds a `contact_ledger` section
(`extract_contact_metrics`) when bundles carry the summaries.

## Native change

One additive, read-only PyO3 method, `AgentSimulator.get_pending_arrivals()`,
returning the delivery buffer's arrival records without draining them. Nothing
else in Rust changed; calling it never changes a simulation result (Rust unit
test `test_pending_arrivals_read_only`).

## Verification

`tests/test_contact_ledger.py`: decay/fold/prune and civ aggregates, dependence
and partner queries, end-of-turn inputs, TRADE bump semantics (and unchanged
off semantics), each consumer (movement spread, merchant trigger, warmth cap,
embargo/war shocks, pandemic spread), off-mode determinism, save/load
continuation, a monkeypatched feature-off run that forbids every ledger entry
point, dormant serialization and old-save load, the CLI flag and new-world
default, analytics, and native hybrid determinism with merchant and migrant
flows recorded.

### Feature-off identity

Base export (`1282630`, selected with `PYTHONPATH`) against this branch with
the default and with an explicit `--no-contact-ledger`, same virtualenv and
native build: `--agents off` 150 turns and `--agents hybrid` 120 turns for
seeds 42 and 7. Every output file (`state.json`, `chronicle.md`,
`memories_*.json`, `agent_events.arrow`, `chronicle_bundle.json` minus
`metadata.generated_at`) is byte-identical.

### Subset gate (20 hybrid seeds x 200 turns, `--parallel 2`)

| Run | Gate | vs base | satisfaction mean | latest satisfaction | migration rate | calibrated-floor failures |
| --- | --- | --- | --- | --- | --- | --- |
| base `1282630` | PASS | n/a | 0.4134 | 0.4596 | 0.0583 | occupation, living_population (pre-existing `terminal_population_extinction`) |
| ledger on, first calibration (movement 1%/50%) | PASS | NO REGRESSION | 0.3998 | 0.3982 | 0.0608 | + satisfaction_mean, latest_satisfaction_mean |
| ledger on, final (`--contact-ledger`) | PASS | NO REGRESSION | 0.4042 | 0.4344 | 0.0607 | occupation, living_population (same as base) |

Extinct worlds at turn 200: 15/20 base, 20/20 final. A second seed set
(62-81, same settings, no gate) moves the other way: 19/20 off, 16/20 on, with
satisfaction 0.4116 vs 0.4102 and mean last-agent turn 166.5 vs 170. Across
both sets the shift is within run-to-run divergence; the extinction failure
itself is pre-existing and owned separately.

### Consumer statistics (seeds 42-61 hybrid, then 62-81 hybrid)

| Metric | base / off | ledger on |
| --- | --- | --- |
| movement adoptions (all movements) | 32 / 24 | 71 / 77 |
| mean adherents per movement (120 movements per set) | 1.27 / 1.20 | 1.59 / 1.64 |
| movements with 2+ adherents | 27 / 23 | 39 / 32 |
| merchant great persons from the trade trigger | 0 / 0 | 37 / 43 |
| living civ pairs with live trade (`F_ab >= 1`), mean per turn | n/a (cumulative `trade_volume` only) | 1.11 / 1.07 |
| TRADE actions ok / no partner (seeds 42-61) | 376 / 44 | 277 / 71 |
| movement schisms (named) | 19 / 5 | 50 / 77 |
| federations formed | 152 / 120 | 189 / 185 |
| embargoes / wars declared (seeds 42-61) | 148 / 38 | 179 / 32 |
| disposition samples, every 10 turns, living pairs (allied/friendly/neutral/suspicious/hostile, seeds 42-61) | 453/56/41/47/136 | 464/60/59/49/141 |

Agent merchants completed about 2,100-2,200 trips per run in both modes;
with the ledger on their deliveries are what define `F_ab`.

`--agents off` (seeds 42-47, 200 turns, route proxy): mean adherents 1.53 ->
2.47, trade-trigger merchant great persons 0 -> 12, disposition samples
friendly 51 -> 92 and hostile 38 -> 31, wars declared 22 -> 20, living civ
pairs with live trade 1.65 per turn.

## Follow-ups

* Intra-civ plague chains (needs per-region pandemic damage).
* Religion and culture diffusion along pilgrim/people flows; technique and
  language diffusion; diasporas from the directed people channel.
* Destroyed armies and battles are only seen through surviving armies.
* Embassies are not modeled; hostages are the only diplomatic people flow.
* The parameters are illustrative calibrations, not fitted against the
  200-seed gate.
