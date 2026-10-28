# Public production: source audit and activation blockers

Audit date: 2026-10-28. Source base: `c1a9844bbd2bb67bca598b1d67c5e6da9e2a583d`.
This is a source audit, not a measured production study. The accompanying
[preregistration](craft-work-cap-preregistration.md) authorizes only a capacity
consumer in the existing city-economy input path. No workshop, mill, wage,
private business, energy good or runtime planner is activated.

## Existing physical and work boundaries

| Boundary | Source at the audited base | Consequence |
| --- | --- | --- |
| Occupations | `chronicler-agents/src/agent.rs:7`, `:28` | Farmer, soldier, merchant, scholar and priest exist; artisan does not. Native adulthood starts at 20. |
| City farming time | `src/chronicler/cities.py:191`, `:1025` | Urban farmers retain 0.8/0.7/0.6 of farming time in towns/cities/great cities. The region factor weights that diversion by its actual farmer counts. |
| Legacy craft capacity | `src/chronicler/cities.py:194`, `:1072` | Capacity is 0.1 raw loads per city civilian, including non-farmers and without an adult filter. This is not a roster of employed artisans. |
| Guild craftworkers | `src/chronicler/guilds.py:236` | `masters` estimates merchants plus the diverted share of farmers from a city's aggregate mix and size; it does not reserve individual work. |
| Finite extraction labor | `chronicler-agents/src/economy.rs:1007` | The farmer headcount, after the city factor, is split among farm/resource slots and foraging. A second subtraction for the same diverted city work would charge farming twice. |
| Physical craft conversion | `chronicler-agents/src/economy.rs:1072`, `:1545` | Native crafts consume timber/ore-category goods on hand, excluding committed merchant departures, and produce wares one for one. Consumption occurs inside the existing economy tick. |
| Demand coupling | `chronicler-agents/src/economy.rs:1110` | The craft ceiling is also raw-market demand. Reducing it can change prices, trade, subsequent income and welfare. Unchanged income formulas do not imply unchanged income values. |
| Result exposure | `src/chronicler/economy.py:1568` | Python receives region-total craft output/sufficiency. Per-good craft inputs remain in native `RegionWorkState.craft_input` (`economy.rs:430`), not a site-level receipt. |
| Rural health work | `chronicler-agents/src/health_care.rs:22`, `:74`; `ffi/mod.rs:2874` | Current health eligibility explicitly excludes city settlement IDs, armies and trips. It cannot be treated as an available urban-work roster. |
| Live agent rows | `chronicler-agents/src/pool.rs:711` | Snapshots contain living IDs, age, occupation, region and settlement, but do not expose `is_on_trip`. A Python headcount cannot prove all native availability predicates. |
| Phase boundary | `src/chronicler/simulation.py:2010`, `:2039`, `:2061` | Existing city columns use the beginning-of-turn native snapshot before Phase 2 `tick_economy`. Phase 10 cannot retrospectively supply work to that completed output. |

For a region, let `L` be its existing craft raw-demand ceiling and let
`A_g = max(stock_g + current_output_g - merchant_departures_g, 0)` for each
raw-material good. The existing native conversion is:

```
Q = min(L, sum_g A_g)
I_g = (A_g / sum_g A_g) * Q      when sum_g A_g > 0, otherwise 0
sum_g I_g = Q                  within native floating-point tolerance
raw_stock_g loses I_g; wares gain Q
```

Native conservation records both the raw consumption and wares production.
Storage wear, consumption, trade, caps and losses then follow their existing
rules. The cap consumer changes `L` to `min(L, C)` in specified regions; it
does not add another conversion or modify stocks itself. It also changes the
raw demand term by that same amount. A zero cap must remain zero rather than
fall back to legacy capacity.

The active cap's raw-load unit is a consumer contract. It is not yet a
worker-turn, joule, measured horsepower or forecast of realized output.

## Cash and ownership are separate from this conversion

Craft stock is shared regional inventory, not an artisan's private stock.
Farmer income is a scarcity signal weighted by resource production
(`economy.rs:1635`); merchant income follows regional delivered margins
(`:1653`). Neither is an actual workshop purchase, wage or private sale.
Public procurement's domestic producer sink is likewise not a private wallet;
see [the public purchase receipts](public-purchase-receipts.md) and
[the cash/trade audit](../roadmap/public-trade-accounting-seams.md).

For a later public operation, an honest public budget would have to close as:

```
treasury_close = treasury_open - committed_public_expenditure + explicit_public_credits
public_expenditure = named_sink + actual_credited_receivers
private_wages = 0 unless an explicit payer-to-agent-wealth transfer is implemented
```

An upkeep debit may be a named public expenditure sink; it cannot be narrated
as a worker's wage or seller's receipt. A physical requisition must explicitly
debit shared stocks, obey existing commitments, and name that ownership regime.
There is no current basis for a private firm balance sheet or insurance claim.

## Water and energy do not yet close

`River` stores only a name and ordered region path (`models.py:374`).
`RegionGeography.elevation` is normalized 0..1, not head in meters (`:381`).
`RegionEcology.water` is dimensionless (`:304`), influences crops/capacity and
changes in Phase 9 (`ecology.py:785`); it is not available discharge or a
spendable energy stock. Thus `rho * g * Q * H` cannot be evaluated honestly.

The existing roadmap's usable-work slice already acknowledges this proxy
boundary, and its employer slice already requires replacing income rather
than adding wages: [system expansion sections 4–5](../superpowers/roadmaps/system-expansion-2026-10.md#4-usable-work-and-prime-movers).
This work supplies a consumer boundary for that plan, not a second system.
Legacy `Resource.FUEL`/EXOTIC is food in the goods economy; it cannot become
coal by relabeling. Timber extraction's forest-cover debt also remains open
([production ledger](production-ledger.md)). No water, fuel or technique
multiplier is added in this slice.

## Smallest defensible public pilot, still blocked

Prefer a manually worked public craft operation before a watermill. Use at
most four selected regions and one selected city in each, with at most eight
named adult city farmers per site. Those are proposed hard state/work bounds,
not evidence that the workforce is available. In a selected region the public
operation must replace its entire legacy craft ceiling; adding an operation
alongside that ceiling would duplicate the same unallocated work. Regions with
multiple cities need either this explicit regional replacement or new native
per-site allocation; no inferred share of region-total output is acceptable.

For eligible worker `i`, let `d_i = 1 - URBAN_FARM_LABOR[city.rank]`, and let
`a_i` be the authoritative fraction of that already-diverted time available
after all other assignments. A future planner must prove:

```
0 <= a_i <= d_i
W = sum_i a_i
C = min(L, k * W)               if funded and open; otherwise 0
Q <= C;  work_used = Q / k <= W  for preregistered k > 0
```

This consumes only diverted time and leaves the current farm factor intact.
Rural health labor is not added to `W`; merchants/scholars/priests and children
do not become free artisans. Unused diverted time is not silently returned to
farms. `k`, construction costs, upkeep, condition and any reliability rule need
their own preregistration before planner implementation or parameter tuning.

Activation blockers:

1. Native-authoritative current eligibility must resolve living stable ID,
   age >= 20, farmer occupation, correct city/region, no army duty/trip and no
   competing assignment. Reuse the existing snapshot/ID lookup; do not scan
   the pool once per worker or infer availability from city mix. Current
   aggregate city diversion is not that proof.
2. Define one work reservation/consumption authority shared with subsequent
   work consumers. The current rural health contract is disjoint, not general.
   The consumer cap alone must never claim that an allocation was made.
3. Define paid construction/upkeep, protected regional inputs and successful
   commit settlement. Use actual projected treasury and physical stocks;
   commit once after a successful Phase 2 result, with no payment/output on a
   failed or unavailable tick. Do not invent a private recipient.
4. Expose actual native raw input use if claiming per-good public receipts.
   Current output is regional; site-specific inputs/cash cannot be inferred
   from proportional output after the fact.
5. Define conquest, city fall, repair and reopening with dated asset history;
   an unfunded/invalid selected site remains capped at zero for that operation.
   Ownership changes must not silently rebuild it or erase arrears.

## Clock, persistence, evidence and runtime budget

The implemented consumer is a pure call argument. It has no saved state,
event, RNG, cache, planner or simulation hook. Each call recomputes base city
columns; a cap from turn T cannot leak into T+1. Existing callers pass no cap.
Its only extra active work is O(K) validation/clamping for K supplied regions;
it reuses the existing O(agent rows + cities + regions) city column builder.
No additional all-agent pass or per-receipt scan is introduced. There is no
measured runtime claim.

A future planner should have bounded site state (<=4), bounded current crew
IDs (<=8/site) and one completed-turn frame, plus scalar counters; no lifetime
employee or output history in every snapshot. Source turn T means successful
Phase 2 production in T, exported only after that phase completes. Preparing a
plan is not output; a missing phase is unknown rather than observed zero.
Exact checkpoints are supported only at the existing completed-turn boundary.
Saved assets can survive exact resume, but native ID continuity requires the
native checkpoint; raw JSON with a fresh pool cannot continue old employment
claims. New fields missing from old Pydantic pickles must explicitly migrate
to unknown rather than fabricated empty observations.

The consumer's checks are preregistered separately. A future pilot also needs
work-only, cost-only, zero-input, zero-work, idle/unfunded and ownership-loss
controls; half-work monotonicity; worker exclusion/double-booking tests;
success/retry/pay-once and exact-resume identity. Power reliability, conversion
and upkeep ablations belong only to a later declared power mechanism. Causal
studies must distinguish intended craft-market effects from generic income or
technique changes, retain failure artifacts, and choose holdout seeds before
tuning. No such study or activation is claimed here.
