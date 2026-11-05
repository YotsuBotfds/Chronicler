# Public grain convoys under risk (L4, `--grain-convoys`)

Lane L4 of the [livelihoods sprint](../superpowers/roadmaps/livelihoods-commons-sprint1.md).
Default off. Requires `--grain-reserves --public-grain-shipments` (an
agent-backed goods economy). `--convoy-route-policy {adaptive,cheapest,safest}`
(default `adaptive`) is read when the switch is given. Source:
`src/chronicler/grain_convoys.py` (behavior) and
`src/chronicler/grain_convoys_state.py` (persisted data, under
`WorldState.livelihoods.grain_convoys`).

## Scope

The one-hop public grain shipments (`public_grain_shipments.py`, byte-pinned,
unchanged) buy foreign grain only from a market one merchant-route step from
the buyer's granary. The granary pass skips foreign markets two or three steps
away (`steps[src] != 1`). Convoys serve exactly those skipped sources, after
the granary pass, with what remains of the buyer's procurement budget for the
turn (`economy_result.food_procurement_budget`), in the granary pass's own
order (civilizations by index, granaries emptiest against target first, or the
shortfall-priority order when that tuning is set; sources by price, steps,
index). Direct sources and every shipment are untouched; convoy cargo already
on the road counts as inbound for the granary pass, so it is not bought twice.

Limits: at most 64 convoys on the road, two per destination granary, routes of
at most three edges at dispatch or per reroute, two reroutes per convoy.

## Timeline

| When | What |
| --- | --- |
| Phase 10 of T, after the granary pass | dispatch: buyer pays the seller's ruler (`finance.transfer`), pays any escort fee to the escort sink, the origin market loses the grain, transit decay (`TRANSIT_DECAY["grain"]`) is booked once |
| Phase 10 of each later turn, before the granary pass | movement: at most one edge per turn (two turns on an edge touching terrain costing at least 1.5: desert, mountains, tundra, jungle, marsh) |
| arrival turn, same phase | the destination granary is credited whoever keeps it; the reserve ledger records a `convoy_arrived` flow |
| next Phase 2 | the existing granary opening can release it; it is never eaten earlier |

A two-edge plains convoy dispatched at T arrives at T+2 and can first feed
people at T+3 (a one-hop shipment: T+1 and T+2).

## The choice at dispatch

Two plans are built from facts known at dispatch: the **exposed** plan (fastest
route, no escort) and the **escorted** plan (least exposed route, an escort that
musters for one turn before the first leg and beats off 75% of threats). The
escort fee is 1 treasury per route edge, a disclosed public expenditure sink
paid from the buyer's treasury (`keep`): no wage, no recipient, no refund.
`cheapest` never escorts, `safest` always does (skipping the source if the fee
leaves less than one coin of cargo), `adaptive` escorts only when
`fee + escorted_risk × 0.25 × value < exposed_risk × value`, with the cargo
valued at its price. Both plans are stored on the convoy
(`exposed_route/risk/turns`, `escorted_route/risk/turns`). An escort that
reaches its end without meeting any threat is counted as wasted
(`escort_wasted`, `escort_wasted_paid`).

## Movement and risk (then-current facts only)

At a node the convoy judges its next edge by this turn's facts. The edge is
**closed** when the next region has no ruler (`uncontrolled`), is held by or
belongs to a civilization at war with the buyer (`hostile_holder`; occupiers
count), hosts an army of such a civilization (`hostile_army`; sieges), is
under an embargo with the buyer (`embargo`), or the merchant route graph
(`grain_reserves._route_graph`: war, embargo, disposition, suspended routes,
blockaded sea lanes, cut-off cities) no longer carries it (`route_closed`).

A closed edge leads, in order, to a **reroute** (shortest open route of at
most three edges from where it stands; least exposed if escorted), else a
**wait** (two turns), else the convoy **turns back** along the road it
travelled. A returning convoy blocked beyond the wait is **stranded**. A
convoy blocked at a node for more than 24 turns since dispatch is stranded.

An open edge can hold **threats** (combined as independent chances, capped at
0.9): pirates on a sea lane (2 × the lane's `skim_rate`), an army of the
buyer's enemies at the edge's start or beside its end (0.25 per enemy), an
enemy holding a region beside its end (0.10 per enemy), brigands where the
edge ends outside the buyer's own land (0.02). One draw decides whether a
threat appears and which one (proportional slices); a second decides whether
an escort beats it off. Draws come from
`random.Random(stable_hash_int("grain_convoys", world.seed, convoy, dispatch
turn, turn, leg, direction))`; the global `random` stream and every existing
RNG are untouched. Entering a region that an enemy took while the convoy was
mid-edge also ends in capture.

## Where the grain goes (each cargo once)

| Outcome | Destination | Counter |
| --- | --- | --- |
| `arrived` | destination granary, kept by its recorded keeper (keeper ≠ buyer recorded as `captured_delivery`, no keeper as `unguarded_delivery`) | `delivered` |
| `captured` | market of the captor: where it struck (army region, the enemy region beside the edge, the edge's ends, their neighbours), else its capital, else its first region | `captured_grain` |
| `lost` | loss sink: `piracy`, `raid`, or `captor_without_market` | `lost_grain` |
| `returned` | origin market (the seller keeps the payment; nothing is refunded) | `returned_grain` |
| `stranded` | market of the region where it stands | `stranded_grain` |

Grain closure (checked with `CHRONICLER_CHECK_RESOURCES=1` after each pass):
`committed_net = delivered + captured_grain + lost_grain + returned_grain +
stranded_grain + cargo on the road`, and `sent = committed_net +
transit_loss`. Dispatch also adds `sent`, `transit_loss` and `paid_foreign` to
the reserve counters, as shipments do. Treasury moves only buyer → seller
(price) and buyer → escort sink (fee).

## Hooks in pinned files

The byte-pinned shipment modules are not edited. Four literal hunks in
`src/chronicler/grain_reserves.py` and one in `grain_reserves_state.py`
(the lead's reviewed inverse layer records them):

1. `grain_reserves_state.py`: `"convoy_arrived"` appended at the end of
   `FLOW_KINDS` and `CONVOY_ARRIVED` at the end of the unpacking line.
2. `grain_reserves.py` import: `CONVOY_ARRIVED` added to the state import.
3. `tick_grain_reserves`: after `inbound = inbound_by_destination(world)`,
   `add_convoy_inbound(world, inbound)` when `world.livelihoods` exists.
4. `ReserveLedger.finish`: `convoy_arrived` flows summed per granary and
   added to the expected granary balance (arrivals happen inside the ledger's
   Phase 2 → Phase 10 window). The sidecar Arrow schema is unchanged; its
   `grain_after` includes convoy arrivals without a separate column.

No change to `livelihoods.py`, `simulation.py` or `models.py` is needed.

## Observation

`snapshot.livelihoods.grain_convoys` (only while the switch is on, convoys are
draining, or the last turn's transitions are being reported): `source_turn`,
`enabled`, `route_policy`, `moved` / `dispatch_ran` (whether each pass ran in
the source turn), `active_count`, `in_transit_cargo`, `returning_cargo`,
`active` (at most 64 convoys with route and its names, leg, progress, status,
cargo, escort and dispatch plans), `transitions` (the source turn's frame;
`null` when no pass recorded it, `[]` when nothing happened) and cumulative
`counters`. Viewer: `viewer/src/lib/grainConvoys.ts` (strict reader, null on
absent, stale or malformed records) and
`viewer/src/components/systems/GrainConvoys.tsx` (not mounted; the lead
mounts it). Event types: `grain_convoy_dispatched`, `_turned_back`,
`_arrived`, `_captured`, `_lost`, `_returned`, `_stranded`.

## Known limits

- Convoy payments are made after the granary pass, so `--transaction-receipts`
  public purchase receipts and harvest-forecast procurement decisions observe
  the granary pass only; the convoy frame records price and fee. The reported
  procurement budget (`food_procurement_budget`) is reduced by convoy spending.
- Whole-cargo outcomes only (no partial raids, no spoilage on the road beyond
  the transit decay booked at dispatch).
- Removing granaries (`--no-grain-reserves`) while convoys are on the road is
  refused at the next convoy pass (the paid cargo has nowhere to go).
- The risk numbers above are uncalibrated development parameters.

## Evidence (2026-11-05, Linux, CPython 3.13.18, native extension SHA-256 `9e0434fd…5fe0`)

Natural development runs (template seeds 1–3, 150 turns, `--agents hybrid
--grain-reserves --public-grain-shipments --grain-convoys`) **never dispatch a
convoy**; one-hop shipments never dispatch either. A read-only probe of the
convoy pass found 593 / 889 / 733 granary-turns in deficit after the granary
pass, 0 / 398 / 436 of them with a foreign source two or three steps away, and
none whose source held a sellable surplus (grain beyond four turns of its own
demand, net of merchant commitments): only 26 / 9 / 8 region-turns of 1,200 had
any. The binding constraints are the shared surplus rule and, where surplus
exists, the whole-coin payment floor, not the convoy mechanism.

Constructed runs (labelled: an opening stock of 400 grain in each market of
civilization 0, seed 1, otherwise the real simulation): 13 eligible multi-hop
deficits → 11 worth less than one coin → 2 convoys dispatched → 2 arrived
(12.39 grain, `adaptive` and `cheapest`), at most 0.81 grain of it released at
the destination within five turns. With `safest` the same two convoys paid 4
treasury in escort fees, one arrived without meeting a threat (a wasted 2-coin
escort) and the other, held back one turn by its muster, was still one edge
short of its granary when the run ended, so only 5.96 grain arrived. A scan of 24 other constructed stocks (seeds 1–3, each
civilization, 250 or 600 grain) dispatched one more convoy. Every run above
had `CHRONICLER_CHECK_RESOURCES=1` on.

Offline tests (`tests/test_grain_convoys.py`) cover the acceptance cases with
the real granary, shipment, payment and ledger code; the constructed native
module (`tests/test_grain_convoys_native.py`) runs real hybrid turns to
delivery and an exact mid-leg checkpoint resume. Feature-off identity: the
switch omitted and `--no-grain-convoys` each reproduce all 45 output files of
the baseline source `050cfbe` (seeds 1–3, 60 turns, hybrid, reserves,
shipments, validation sidecar). `scripts/checkpoint_identity.py` (`hybrid_s42`,
30 turns, switch on, resumes at 5, 10, 15, 20, 25, 29) passes, with convoys
idle there. Not run: full offline/native suites, hosted CI, the 200-seed and
procedural gates, held cohorts, calibration or performance qualification.
