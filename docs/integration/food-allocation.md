# Household food allocation (L2, `--food-allocation`, default off)

Sprint 1 of the livelihoods/commons plan
([plan](../superpowers/roadmaps/livelihoods-commons-sprint1.md)). Requires
`--agents hybrid`. The regional economy is unchanged. It withdraws the same
food as before (see [food accounting](food-accounting.md)). This package
decides **who eats it**, and routes each person's own ration into the
consumers that previously read the region's sufficiency.

## Mechanism

1. Phase 2, before the economy tick. Each region's native alive count
   (`N2`) is taken from the snapshot Phase 2 already holds. No second
   snapshot is requested.
2. Phase 2, after the tick and before public granaries open. Each region's
   pre-release food sufficiency is recorded.
3. Before the native agent tick, `AgentSimulator.set_food_allocation`
   installs a one-tick request. At phase 0.7 the tick takes it. That is after
   this turn's catastrophe and targeted deaths, and before needs. The tick
   allocates the region's post-release rations,
   `sufficiency × N2` (1 ration = the per-capita food demand). The living's
   share, `T = sufficiency × N` (N living, at most N2), goes to the people
   alive there (`chronicler-agents/src/provisioning.rs`). The share of anyone
   who died after Phase 2 is recorded as unallocated. It is not shared out.
   - **equal**: `min(1, T/N)` each, which is exactly the regional signal.
     This is the identity control: an equal-regime run reproduces the
     feature-off trajectory.
   - **floor_means** (default): an equal floor of `min(floor, T/N)`, then the
     scarce remainder shared by household means: per-capita adult wealth plus
     a declared base weight of 1. Shares are water-filled up to one ration
     each. This is a stated market-access rule, not a hidden wealth formula.
   - **targeted_relief**: the living's market food is shared equally. The
     living's share of the public release
     (`(sufficiency − pre-release) × N`) goes first to the poorest
     `target_share` of households, then to everyone else.
   No region allocates more than `T`. The dead's share, and anything left
   once everyone has a full ration, is recorded as `unallocated`.
   On the current turn order nobody can arrive in a region between Phase 2
   and the allocation. If someone did, the region's withdrawal would be
   shared among more people (never invented), and `equal` would then fall
   below the regional signal.
   When the pre-release sufficiency is unknown, the release share is
   recorded as unknown (`null`), not zero. Targeted relief then treats all
   food as market food, and `relief_unknown_regions` counts such regions. Regions with sufficiency ≥ 1 keep the regional
   signal, including its abundance.
4. Households are derived from existing identities, not a new registry. A
   married adult is keyed by the couple's smaller id when the spouse is alive
   in the same region. A child (under 20) joins a living adult parent's
   household in the same region. Anyone else is a household of one.
5. A person's ration replaces the regional sufficiency in these consumers:
   the safety food term, the material food and wealth-shortage terms,
   dearth/famine material pressure, satisfaction's food penalty, and hunger
   mortality and fertility. The ration counts only while the person is
   still in the region it was allocated in. A merchant who left on a trip, or
   a migrant who moved after phase 0.7, reads the current region's signal,
   as before. Migration choices, occupation targets and famine memories
   still read the regional signal. The severe-hunger run (`food_severe_turns`)
   stays regional; a per-person run would need persisted per-agent state.
6. After the tick, Python takes the receipts once and checks that
   `allocated + unallocated = rations available` in every scarce region.
   Receipts give, per scarce region: shortfall person-turns overall, for the
   poorer and richer halves of households by means, and for children; relief
   reaching targeted households; the range of rations; and a bounded person
   sample (24 people: id, household, ration, targeted). Nothing is recorded
   for a turn without an allocation (unknown, not zero).

Parameters are declared modeling choices, not calibrated:
`livelihoods.food.floor` (0.5 rations) and `livelihoods.food.target_share`
(0.5 of households), both overridable through `--tuning`.

## Evidence

Results and scope are recorded in the sprint board and in the L2 landing
commit. Lifecycle cases have Rust unit tests in `provisioning.rs`:
- deaths after Phase 2;
- a child joining a parent's household;
- marriage merging households, and remarriage or a spouse's death splitting
  them;
- a migrant after the allocation, and a newborn in a reused slot (both read
  their current region's signal);
- empty and zero-food regions.

Python tests cover missing native data and unknown relief.
