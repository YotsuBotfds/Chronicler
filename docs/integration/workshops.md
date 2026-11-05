# Staffed public workshops (L1, `--workshops`, default off)

Sprint 1 of the livelihoods/commons plan
([plan](../superpowers/roadmaps/livelihoods-commons-sprint1.md)). The package
lands in two steps. This page records what each step implements and what it
does not.

## L1A: payer-independent contract (this landing)

`--workshops --workshop-mode observe` requires `--agents hybrid` and cities.
It resolves crews and reports actual native craft inputs. It employs nobody,
changes no craft ceiling, charges nothing, and leaves the trajectory
unchanged. `--workshop-mode operate` is refused until L1B.

The landing closes three of the five activation blockers in
[the public workshop source audit](public-workshop-source-audit.md):

1. **Eligibility (native).** `AgentSimulator.plan_workshop_crews`
   (`chronicler-agents/src/workshop_work.rs`) makes one read-only pass over
   the live pool. It selects living agents aged at least `AGE_ADULT` (20) with
   `Occupation::Farmer` who reside in the site's settlement and region. It
   excludes agents on a merchant trip and enlisted army members (ids from
   `world.war_state.armies`, as health care does), and anyone already
   reserved by `health_work_loss` or a pending teaching plan. Selection is by
   ascending stable id, up to eight per site. Each excluded agent is counted
   under its reason. No RNG is used and the pool is not mutated.
2. **One reservation authority.** The planner is the single allocator of
   workshop time. It also treats existing health and teaching reservations
   as taken. In the current model those consumers are disjoint by predicate:
   health care is rural-only and teaching is Scholar-only. An agent can be
   claimed by at most one site. A crew member's available time is the city's
   already-diverted farm share, `1 - URBAN_FARM_LABOR[rank]`. The economy's
   `farm_labor_factor` already removed that share from farming, so nothing is
   subtracted twice.
3. **Actual raw-input exposure (blocker 4).** `EconomyRegionResult` now
   carries `craft_input` (`RegionWorkState::craft_input`).
   `AgentSimulator.take_craft_inputs()` returns the last tick's per-good input
   by region exactly once. Receipts copy the region's timber and ore input,
   its actual craft output and its legacy craft ceiling (`craft_raw_demand`).
   These are region totals, never a site share. When the native observation
   is missing, the receipt records unknown (`None`), not zero.

Sites: at most four open cities of rank ≥ 1, one per region, admitted in a
deterministic order (rank, size, settlement id) once cities exist. A site
whose city falls or vanishes is closed with its date and reason, and a closed
city is never readmitted. Receipts cover the last completed Phase 2 only.

### Evidence (L1A source)

- `tests/test_workshops.py` (offline): site order and cap, closure, refusal
  of `operate`, stale-input drop, unknown versus zero, and rollback.
- `tests/test_workshops_native.py` (real extension): in a 40-turn hybrid run
  every crew id is checked against the live native snapshot (age, farmer,
  settlement, region, uniqueness). The sum of each region's inputs equals its
  craft output. Observe mode reproduces the off run's history and world state
  exactly, apart from the new observation key.
- `cargo test`: `workshop_work` unit tests, and 1,207 passed / 0 failed for
  the whole crate.
- Development run (template seed 7, 150 turns, observe): four sites were
  selected and one closed when its city fell. 366 site-turns showed regional
  crafting, and input equalled output in every one. A feature-off run on the
  new extension is byte-identical to the baseline extension's.

## L1B: funded operation

Not yet landed. The selected route, the public treasury of the region's
controller, is recorded in the plan's funding comparison.
