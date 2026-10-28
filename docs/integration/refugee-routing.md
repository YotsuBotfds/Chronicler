# Capacity-aware macro refugee routing

`--capacity-aware-refugees` opts aggregate (`--agents off`) and shadow
worlds into capacity-aware destination allocation for famine refugees and
climate overflow migration. It is off by default. The switch is persisted
on `WorldState.capacity_aware_refugees`; false is omitted from world JSON,
so old saves and worlds without the switch retain their behavior.

## Behavior

The existing rules choose the source's migrant budget and permitted adjacent
destinations. `refugee_routing.apportion_refugees` distributes that budget
equally in integer shares, bounded by each destination's available effective
capacity. When a destination fills, its blocked share is redistributed to
the destinations that still have room. Remainders go to the lowest index in
`world.regions`. Adjacency ordering and duplicate adjacency entries cannot
change the opt-in allocation. No random draws are added.

For example, 13 departing people with one full neighboring region and one
empty neighbor that has room for all 13 now reach the empty neighbor. The
legacy equal split offers 6 or 7 people to the full neighbor and loses them
even though the other neighbor has space. With two open destinations of
equal capacity, 13 people split 7/6 in canonical region order. Available
capacities of 1, 3 and 20 receive 1, 3 and 9.

The source's toll or departure is unchanged. A famine still removes its
explicit graded toll; overflow still removes the entire surplus, including
when there is no permissible destination. If only two places exist for 13
departing people, two settle and 11 die in transit under the existing policy.
This feature improves destination allocation rather than changing that loss
policy. Regions already above capacity keep their existing residents. Only
destinations with positive arrivals receive the opt-in arrival's stability
penalty. Population flows continue through the existing debug ledger:
`immigrated <= emigrated`, with unplaced people represented by the difference.

Eligibility remains the caller's policy:

* Climate overflow can move to uncontrolled regions, its own realm, or a
  neighboring realm that the source does not regard as hostile. Hostile
  destinations are excluded as before.
* Famine refugees use foreign controlled neighbors with an existing realm,
  as before. This includes hostile neighbors; this slice does not add a new
  border policy to famine relief.
* Sources are processed in `world.regions` order. A later source uses the
  headroom remaining after earlier arrivals. World region order is identity,
  not an interchangeable input ordering.
* Hybrid and demographics-only worlds are dormant: the native agent pool
  owns population and these Python migration/toll paths remain inactive.

## Entry points and saved runs

The CLI and gate runner accept `--capacity-aware-refugees` and
`--no-capacity-aware-refugees`. Omission preserves a loaded world's saved
choice; new worlds default off. Single runs, supplied worlds, batches and
new live worlds use the same switch. Live Batch Lab accepts an optional
boolean `capacity_aware_refugees` in `batch_start.config`, inheriting the
CLI's choice when absent. Exact checkpoints save the flag, run configuration
and world; continuing one uses the checkpoint's configuration.

The batch manifest records it as a simulation argument, and checkpoint
headers record the actual world setting. Comparisons therefore cannot
silently treat on/off cohorts as identical configuration. These schema
descriptions gain the new argument even for an off run; simulation state,
history, narrative and sidecar output remain unchanged with the feature off.

Examples:

```sh
python -m chronicler.main --seed 42 --turns 50 --agents off --simulate-only --capacity-aware-refugees --checkpoint-every 10 --output output/refugees/chronicle.md
python scripts/m53b_run_validation.py --profile determinism-off --capacity-aware-refugees --output-root output/refugees-determinism
```

The usual full template and procedural hybrid gates check dormant behavior
for this feature. They do not measure its macro-population outcomes. Any
future default promotion needs aggregate/shadow before-and-after cohorts,
population-flow checks, and separate reporting of arrivals, transit losses,
receiving unrest, population and polity survival.

## Verification

`tests/test_refugee_routing.py` covers the 13-person full/empty case, bounded
redistribution and remainders, tiny capacity combinations, input-order and
duplicate invariance, shared capacity across sources, hostility, uncontrolled
destinations, famine's existing eligibility, insufficient/no room, unchanged
source tolls, actual receiving penalties, both macro modes, dormancy under
agent-owned modes, raw/world/exact checkpoint continuation, CLI/live/batch
wiring and gate forwarding. It has its own bounded offline oracle chunk.

The new chunk passed 23 tests under the offline guard (1.86 seconds against
the 110-second limit). The broader selection passed 229 tests in 40.50
seconds: routing, climate, ecology, population conservation, batch manifests,
procedural gate forwarding, exact run/live checkpoints, and the live server.

Default-output identity against the base `cb9fe70c`: template 8-region/4-civ
and procedural 32-region/10-civ worlds, seeds 7 and 42, 50 turns, Python
runtime. Each comparison covered 48 output files: no differences with the
new default or with explicit `--no-capacity-aware-refugees` (only the bundle
generation timestamp was ignored; all other files were compared as bytes).
The same four opt-in runs passed with `CHRONICLER_CHECK_POPULATION=1`.
Procedural final populations moved 906 to 935 and 1128 to 1143; the two
template populations were unchanged. These are smoke observations, not
population calibration or statistical qualification. No native schema changed,
and no full scientific gate or default promotion is claimed.
