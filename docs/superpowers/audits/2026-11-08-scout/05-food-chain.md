## 05 Food chain (retail, trade, allocation, reserves, convoys, hunger)

**Map**
- Phase 2 (`simulation.py:2078-2150`): `livelihoods.prepare_phase2` (LIVELIHOODS_SWITCHES order, `livelihoods_state.py:76-84`) edits the native region batch, then native `tick_economy`, then `finish_phase2` hooks, then `open_granaries` (`grain_reserves.py:318` adds grain into `economy_result.food_sufficiency`), then `capture_food_accounting` (`food_accounting.py:85`).
- Agent tick wraps `before_agent_tick` / `after_agent_tick` hooks (`livelihoods.py:1192-1225`): food_allocation installs per-person rations, household_retail installs retail (`household_retail.py:1532-1590`).
- Phase 9/10: `ecology._update_severe_food_turns` (`ecology.py:210-236`) turns sufficiency into `food_shortfall` and the severe run; hunger mortality is native (`demographics.rs:80-121`).
- Phase 10: `phase10_before_reserves` (granary-cap cut, `household_retail.py:2162-2232`), `tick_grain_reserves`, then `household_retail.phase10` and `titled_trade.phase10`.
- The held "shortfall" metric is `sufficiency_after_relief` demand-weighted (`scripts/connected_world_screens.py:1030-1052`), so it is read after granary relief.
- Sizes: household_retail.py ~2600 lines; titled_trade.py ~900; food_allocation.py 204; food_accounting.py 129; the other grain/harvest modules not read in full.

**Findings**
1. [high] bug/fragile — Per-person hunger and the regional metric use different bases. The metric (`sufficiency_after_relief`) is regional, but mortality reads per-person rations when food allocation or retail is on (`food_allocation.py:19-20`, `provisioning.rs:7`, `provisioning.rs:36`). Redistribution that leaves the regional total unchanged can still raise deaths (the hazard is convex and vulnerable groups get less), and the metric cannot see it. Likely contributor to the connected-world result. Action: report per-person ration deficit and hunger deaths next to the metric, and test the convexity case.
2. [high] sim-depth/bug — Retail rations can fall below the regional average. Priced-out people and unsold owned food are not in the regional sufficiency (`household_retail.py:1565-1586`, `price_milli` 1507-1515, `_settle_frame` 1699-1708 records `priced_out_persons` and `offer_short_persons`). Owned food that goes unsold decays or overflows (`household_retail.py:1443-1451`). Action: count these losses as a named term in the food ledger.
3. [high] bug (likely) — Public-grain conquest capture breaks the public balance. `food_accounting.py:58-60` subtracts released, spoiled and abandoned but not captured, although `CAPTURED` is a flow that empties the granary (`grain_reserves.py:288`, `food_accounting.py:111`). Any captured granary should show a residual of about minus the captured amount. I read this but did not run it. Action: add captured to the residual and add a test that conquest balances.
4. [med] bug (inconsistent basis) — Storage cap has two population bases. `household_retail._storage_caps` (1220-1232) uses `storage_population`; the fallback `_storage_cap` (2246-2255) uses `world.regions[rid].population`. The cut in `phase10_before_reserves` (2203) can therefore differ from the native cap. Action: use one source.
5. [med] ordering (checked, sound) — Labour pulled off farms is removed before the native tick only for workshops, recovery crews, repairs and epidemic care (`livelihoods_state.py:76-84`, `recovery_crews.py:586-606`, `war_requisition.py:494`). Retail crew farm time is removed after the tick (`household_retail.py:1367-1369`), so it cannot cut this turn's production twice. Next-turn effects are not traced.
6. [med] bug risk — Released grain may enter retail's free rations twice. `household_retail.py:1579` adds `released` (granary RELEASED flows) to free rations, and `grain_reserves.py:318` also raises sufficiency with that grain. Within one turn the native `commons_consumed` is read before release, so there is no same-turn double count. Unverified: whether the released grain is later drawn from the commons.
7. [med] test-gap — Conservation gaps. `food_allocation.after_agent_tick` checks allocation closure only for scarce regions (`food_allocation.py:156`). It never ties `rations_available` to native consumption. Unknown `pre` zeroes relief silently (148-149). `_check_food_ledger` is skipped when the ledger is missing (`household_retail.py:1399-1401`).
8. [med] duplication — Hunger constants are mirrored by hand. Python `ecology.py:149,164-168` against Rust `demographics.rs:56-65` (`HUNGER_SEVERE_SUFFICIENCY` is imported from `agent.rs:282`). Turns are `FAMINE_SEVERE_TURNS=3` in Python and `HUNGER_FAMINE_TURNS=3` in Rust. Only the 0.6 threshold is asserted (`tests/test_hunger_mortality.py:111`). Python counts the current turn inside `food_severe_turns` (`ecology.py:225-226`), Rust takes the previous run and adds one (`demographics.rs:89`). Action: a parity test on a grid of sufficiency and run values.
9. [low] inconsistency — `food_shortfall` is stored rounded to 4 places (`ecology.py:230`) and `region_hunger` reconstructs `s` from it (`ecology.py:190`).
10. [low] bug — `food_accounting.py:103` takes the ledger by region id and sufficiency by region name. A name mismatch in `sufficiency` silently gives 0 for the ledger share.
11. [med] sim-depth — Retail `free_exchange` and `record_only` are reachable only by flag (`household_retail.py:1272`, `1373`, `1565`, `1588`; CLI through `livelihoods.py:818`). Their presence doubles several branches.

Not traced in this pass (unverified): titled_trade `_dispatch`/`_buy` draw order and its effect on commons; grain_convoys and grain_storage spoilage and cap; harvest_cover and harvest_forecasts; enforcement costs; the Rust provisioning arithmetic. The ranking above is by code shape, not measured effect.

**Simulation depth**
- Give the metric a per-person companion (ration deficit, priced-out share, unsold-spoiled share) so the connected-world evaluation can say why shortfall rose.
- Model the convex hazard explicitly in allocation, so the "floor_means" regime is judged on deaths and not only on totals.
- Let storage decay and overflow of owned stock respond to the retail offer (today it is fixed by the owner's stock).
- Let labour lost to crews change the next turn's workforce rather than only this turn's farm labour factor.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `household_retail._storage_cap` (2246-2255) and `_storage_caps` (1220-1232) | merge into one function | ~10 | Changes the population basis for regions without a recorded cap (finding 4). Behaviour change, not pure refactor. Tests on the cap cut would need updating. | med |
| `household_retail` `record_only` branches (1272-1273, 1373-1381, 1565-1569, 2188) | delete | ~40 | CLI value `--household-retail-mode record_only` (`livelihoods.py:818`, `NATIVE_MODES`), saved states with that mode, `tests/test_household_retail*.py`, `viewer/src/lib/householdRetail.ts`. Old bundles would need a migration to `retail`. | high |
| `household_retail` rules-version-1 branches (`_v2` at 450, 1268, 1542-1552, 1786, 2188) | delete | ~35 | Saved states and bundles recorded with `rules=1`; `rules_conflict` (204); `--household-retail-rules 1`. Historical import compatibility. | high |
| `food_accounting.public` residual (58-60) | fix, not delete (finding 3) | 0 | Changes the metric in saved `food_accounting` records that lack captured. | low |
| `food_allocation` regime `equal` | keep (it is the identity control) | 0 | CLI `--food-allocation-regime equal`; removing it breaks control runs. | high if removed |
| `ecology.py` hunger constants vs `demographics.rs` | rewrite as a single source exported to Python via FFI (or a parity test) | ~15 | Needs a native rebuild; `tests/test_hunger_mortality.py`; shadow and `--agents off` paths read the Python copy. | med |
| `household_retail.free_exchange` branches (`_credit_procurement` 2391-2394, 1670, 1588) | delete only with `record_only`-style migration | ~15 | Control arm named in CLI modes and the held evaluation. | high |

Confidence: verified by reading the cited lines and by grep for the flags and symbols named above (`record_only`/`free_exchange` counted across src, tests, scripts, viewer; CAPTURED usages). Inferred: the rank order of mechanisms 1-2 (they match the held result's direction but I did not run anything). Not verified: titled_trade, convoys, storage spoilage, harvest_cover, the Rust provisioning arithmetic, and any measured effect size.
