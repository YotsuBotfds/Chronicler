# Ecology / goods integration

This patch connects existing simulation systems without adding new resources,
consumption rules, agent needs, or external narration calls.

## Turn timing and accounting

1. After Phase 1 events and immediately before the agent-backed Phase 2 economy,
   `refresh_resource_yields` previews the current season/climate, ecology,
   suspensions and mineral reserve ramp. It publishes transient
   `resource_current_yields` and does not advance ecology or deplete reserves.
   This also initializes turn zero and restored saves.
2. One finite farmer workforce is split equally among occupied valid resource
   slots. A suspended or zero-yield slot retains its share, so a crop failure
   does not silently create spare labor for another resource. Outputs from
   duplicate goods are summed.
3. Available supply is starting inventory plus this harvest. Abstract trade
   reserves local category demand before allocating exports, decomposes category
   shipments proportionally over actual goods, and applies each good's transit
   decay once. Delivered imports are used consistently in stocks and signals.
4. Prices measure available inventory before consumption: starting stocks plus
   harvest, minus gross exports, plus delivered imports and returned cargo in
   the hybrid path. They are not computed from post-consumption leftovers.
   Cold-start hybrid turns use an empty physical-delivery ledger, rather than
   falling back to abstract imports before a merchant has traveled.
   Loading merchants revalidate reserved cargo against current inventory before
   departure, since intervening consumption/decay can exhaust a reservation.
5. The existing stock lifecycle consumes food, applies storage decay and caps
   storage once. Farmer income uses production-weighted category prices.
6. Phase 2’s harvest preview does not deplete reserves. The inherited native
   post-pass yield refresh can still deplete minerals again when ecology-affecting
   inputs change; exactly-once depletion across that native path remains a
   separate follow-up. Agent-backed famine uses this turn's pre-consumption food
   sufficiency, so reserves and delivered imports can prevent it. Aggregate
   mode retains the existing yield-based fallback. Hybrid/demographics-only
   leave population changes to the native pool; shadow/off retain their macro
   population/refugee effects.

The dedicated economy Arrow input now carries `resource_type_0/1/2` and
`resource_yield_0/1/2`. Rebuild the native extension alongside Python; an old wheel
is incompatible with the new input schema.

## Reproduction

Use the virtual environment's Python to avoid importing stale wheels:

```sh
python -m maturin develop --release --manifest-path chronicler-agents/Cargo.toml
python scripts/economy_coupling_experiment.py --backend python
python scripts/economy_coupling_experiment.py --backend rust --output /tmp/coupling.json
python scripts/economy_hybrid_smoke.py --output /tmp/hybrid-accounting.json
python -m pytest -q tests/test_economy_coupling.py tests/test_ecology_harvest_timing.py
cargo test --manifest-path chronicler-agents/Cargo.toml --quiet
```

The experiment is a controlled phase-level intervention. The native option uses
an actual Rust agent pool and compares its economy output with the Python oracle
using the same snapshot. Trade in this experiment is explicitly **abstract**;
it does not represent instant delivery by hybrid merchants. Its food-producing
fixtures are chosen to straddle the sufficiency threshold, not to tune generated
world balance. The repeated-harvest reserve experiment holds agents and ecology
fixed to isolate finite stock drawdown.

For full simulations, `--simulate-only` disables narration but does not enable
agents: use `--agents hybrid --simulate-only` to exercise the goods/merchant path.

## Deliberate limits

- The ecology yield formula still uses the existing base-yield definition;
  persistent effective-yield calibration is a separate issue.
- Salt retains its existing food/preservation classification. Nonfood stock
  consumption and material costs are unchanged.
- Direct starvation mortality is not introduced. Food availability already
  affects native satisfaction, occupation demand, memories, and downstream
  fertility/migration. Ecological stress remains separately modeled.
- Wiring real harvests and dividing labor can reduce food supply substantially
  relative to the old disconnected single-slot economy. This patch should be
  reviewed as a correctness foundation; broad balance sweeps remain necessary
  before choosing production or demand multipliers.

## Verified interventions

The actual native paired experiment uses the same live-pool snapshot for its
Python comparison (12 target farmers; 12 donor merchants). At turn 0:

| Intervention | Target harvest | Delivered food imports | Food sufficiency | Famine event |
|---|---:|---:|---:|---|
| Temperate, empty reserve | 11.0592 | 0 | 1.105920 | No |
| Drought, empty reserve | 5.5296 | 0 | 0.552960 | Yes |
| Same drought, 20 grain reserve | 5.5296 | 0 | 2.000000 | No |
| Same drought, trade route open | 5.5296 | 11.0400 | 1.656960 | No |
| Severe crop failure, empty reserve | 0.0864 | 0 | 0.008640 | Yes |
| Same crop failure, 20 grain reserve | 0.0864 | 0 | 2.000000 | No |
| Same crop failure, trade route open | 0.0864 | 11.0400 | 1.112640 | No |

The severe case has raw yield 0.0072, below the legacy 0.12 famine threshold,
so the reserve/import result specifically verifies that eating takes precedence
over local harvest failure. A fixed-agent repeated drought exhausts its finite
reserve and loses protection on the fifth harvest. Across the native phase
cases, maximum conservation residual was 0.0000153 goods and maximum
same-snapshot Python/Rust stock discrepancy was 0.0000114 goods.

A separate full-hybrid smoke test ran seeds 0, 1, and 42 for 30 complete turns,
then replayed seed 42 exactly. All runs had zero floor-clamp inventory creation,
finite nonnegative stocks, and maximum Phase 2 conservation error below 0.0000075
goods. Every tick, including cold start, used the physical-delivery ledger. The same diagnostic before cargo revalidation exposed up to 5.01 phantom
goods in a turn. These are correctness/regression checks, not evidence that
long-run population or food balance is calibrated.
