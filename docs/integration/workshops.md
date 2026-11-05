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

## L1B: funded operation (landed)

`--workshops` now defaults to `--workshop-mode operate`. All five blockers
of the source audit are addressed. Blockers 1, 2 and 4 are covered by L1A
above; the rest are below.

- **Payer and settlement (blocker 3).** The payer is the civilization that
  controls the site's region at Phase 2, as chosen in the plan's funding
  comparison. Each turn's bill is planned against the projected treasury
  (`_treasury_budget`), with one budget per civilization shared by all its
  sites in site order. A bill is either one construction installment, or
  upkeep plus any arrears plus any needed repair. It is charged once, as a
  `keep` treasury debit, after the native tick succeeds. A failed tick
  charges nothing (`rollback_phase2`). If the controller changes between
  plan and settlement, settlement refuses. Every payment is a disclosed
  public expenditure sink: no wage, no private recipient, no payroll (L6
  stays deferred).
- **Work and output.** A funded site that is built, in condition and has
  crew operates. It allocates its crew's diverted time `W` and replaces the
  region's craft ceiling with `K_RAW_PER_WORK × W` (2 raw loads per unit of
  work); this is a replacement, not an addition. A selected site that is
  building, unfunded, in need of repair or without crew sets the ceiling to
  zero. Realized work is `min(allocated, region craft output / K)`. The
  crew's ordinary income share is unaffected (0): the time was already
  diverted from farming, which keeps its own factor.
- **Inputs (blocker 4, with protection by phase order).** The conversion
  uses only raw goods on hand after merchant departures, and after grain
  storage has already taken the timber it holds. The receipts report the
  region's actual native per-good input.
- **Asset lifecycle (blocker 5).** The site is building until 60 treasury
  units are paid, in installments of 10. When built, it costs 3 upkeep per
  turn. Unpaid upkeep becomes arrears (capped at 15) and wears condition by
  0.05. Below 0.5 condition the asset needs a repair of 20 before it
  reopens. Arrears, construction progress and condition belong to the asset.
  A conqueror inherits them and pays them before the site reopens; nothing
  is rebuilt for free. If the city falls, the site closes with a dated
  record and its arrears are written off and counted. Each site keeps a
  bounded dated history (16 events).
- **Ablation.** `--workshop-mode cost_only` builds and pays exactly as
  operate mode does, but leaves the legacy ceiling in force.

All parameters are declared modeling choices, not calibrated:
`K_RAW_PER_WORK`, `CONSTRUCTION_COST`, `INSTALLMENT`, `UPKEEP`,
`ARREARS_CAP`, `CONDITION_WEAR`, `OPERATE_CONDITION` and `REPAIR_COST`.

### Evidence (L1B source)

- `tests/test_workshops.py` (offline) covers:
  - installments, then upkeep;
  - a ceiling bounded by crew work (half crew gives half the ceiling; no
    crew gives zero);
  - one budget shared across sites;
  - insufficient funds charge nothing;
  - arrears and wear when unfunded, and a conqueror paying arrears and
    repair before reopening;
  - a failed tick charges nothing;
  - cost-only keeps the legacy ceiling;
  - a city fall writes off arrears and stops the ceiling replacement.
- `tests/test_workshops_native.py` (real extension) covers:
  - every operating receipt has ceiling = `K × W` and output ≤ ceiling;
  - realized work = `min(allocated, output / K)`;
  - every non-operating selected site has a zero ceiling and zero output;
  - payments occur;
  - the operate trajectory differs from off;
  - cost-only charges without replacing the ceiling.
- Development runs (template seed 7, 150 turns; a single world, not
  evidence of an effect):

  | Arm | Site-turns | Operating | Crew work allocated / realized | Site-region craft output | Paid (construction / upkeep / arrears) |
  | --- | --- | --- | --- | --- | --- |
  | observe | 492 | 0 | 0 / 0 | 237.1 | none |
  | operate | 432 | 370 | 450.4 / 102.5 | 205.1 | 240 / 1203 / 6 |
  | cost_only | 492 | 0 | 0 / 0 | 243.6 | 240 / 1386 / 0 |

  Operating crews' ceilings (900.8 raw loads in total, against the legacy
  433.9) did not raise output: the region's raw inputs bound it. Realized
  work is about a quarter of allocated, and construction turns cost output.
  This is a working mechanism with a mixed result. Timber availability (L3)
  is the natural next constraint; the screens test that interaction.
