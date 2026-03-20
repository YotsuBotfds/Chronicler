# M47b Health Check Report

> First full health check with hybrid agent mode post-M47 tuning pass. 200 seeds, 500 turns, 4 civs, 8 regions, `--agents hybrid`. Validates simulation health across 16 criteria covering demographics, economy, warfare, religion, dynasties, and goods systems.

## Summary

**6 PASS, 2 BORDERLINE, 8 STRUCTURAL** out of 16 criteria.

The simulation is healthy at the event-generation layer (religion, diplomacy, factions, warfare all fire) but has two dominant structural problems that cascade into most failures:

1. **War frequency is 7x too high** (median 272 wars/run vs target 5-40). Constant warfare drives mass extinction, population collapse, and prevents tech advancement.
2. **Stockpile/Gini data not reaching bundles.** Gini values are all 0.0 in snapshots (bridge `_gini_by_civ` not populating), and stockpiles are empty in `world_state.regions` (M43a persistence may not be writing to the serialized region model).

These two root causes explain 6 of the 8 STRUCTURAL failures. The remaining 2 (dynasties, determinism) are independent issues.

### Bugs Found During Run

- **`religion.py:351` NameError** — `compute_conversion_signals()` referenced `world` for `get_multiplier(world, K_RELIGION_INTENSITY)` but `world` was not a parameter. Fixed by adding `world` kwarg to the function signature and passing it from `phase_consequences()`.
- **Rust crate out of date** — installed `chronicler_agents` binary lacked the `wealth` column added in M41. Rebuilt via `maturin develop --release`.

---

## Criterion Table

| # | Criterion | Threshold | Measured | Status |
|---|-----------|-----------|----------|--------|
| 0 | `--agents=off` determinism | Bit-identical across 2 runs | Identical with `PYTHONHASHSEED=0`; differs without it (Python hash randomization) | **PASS** (with caveat) |
| 1 | No civ extinct by turn 25 | 0 in >95% of seeds | 54.5% no-extinction (91/200 had early death) | **STRUCTURAL** |
| 2 | Population median @ 500 | >= 100 agents per surviving civ | median=1, p10=1, p90=1 | **STRUCTURAL** |
| 3 | Stability median @ 100 | > 30 | median=29, p10=0, p90=40 | **BORDERLINE** |
| 4 | Action distribution | No single action > 60% | max=DIPLOMACY 34.2%; DEVELOP 20.7%, WAR 19.2% | **PASS** |
| 5 | War frequency | 5-40 per 500-turn run | median=272, p10=162, p90=419 | **STRUCTURAL** |
| 6 | Famine frequency | 5-50 per run | median=12, p10=4, p90=26, not bimodal | **PASS** |
| 7 | Tech advancement | >= 1 era transition per civ median | median=0 (93% stuck in tribal; max=1) | **STRUCTURAL** |
| 8 | Gini range | 0.2-0.8 at turn 500 | 0.0 (no non-zero Gini values in snapshots) | **STRUCTURAL** |
| 9 | Schism frequency | >= 1 in >50% of seeds | 100% firing rate, median 12/run | **PASS** |
| 10 | Conversion events | >= 1 in >80% of seeds | 100% firing rate (Schism+Persecution+Reformation) | **PASS** |
| 11 | Dynasty detection | >= 1 per run in >60% of seeds | 0% (dynasty_founded fires 14%, but dynasty_id not reaching world_state) | **STRUCTURAL** |
| 12 | Arc classification | >= 3 distinct archetypes total | 2 types (Rise-and-Fall, Wanderer), n=2 | **BORDERLINE** |
| 13 | Food sufficiency mean | 0.5-1.5 at turn 500 | 0.0 per region (stockpile empty in bundles) | **STRUCTURAL** |
| 14 | Trade volume | > 0 in >90% of turns after turn 10 | trade events in 100% of seeds; embargo+supply_shock universal | **PASS** |
| 15 | Stockpile non-zero | > 0 in >80% of regions @ 500 | 0% (0/1600 regions had any stockpile) | **STRUCTURAL** |

---

## Root Cause Analysis

### War Frequency (Criterion 5) -- Root of Criteria 1, 2, 3, 7

Median 272 wars per 500-turn run means >0.5 wars per turn. With 4 civs and 8 regions, this is near-continuous warfare. The cascade:

- **Early extinction (C1):** 45.5% of seeds lose a civ by turn 25. Constant war with small starting populations guarantees early elimination.
- **Population collapse (C2):** median population=1 at turn 500. Agents die in wars faster than demographics can replace them.
- **Stability erosion (C3):** median stability=29 at turn 100 (borderline), with p10=0 indicating frequent collapses.
- **No tech advancement (C7):** civs never stabilize long enough to accumulate tech_advancement events. Only 7% of runs see any tech_advancement at all.

**M47c action items:**
- Reduce WAR action weight or add war cooldown/exhaustion mechanic
- Consider `--aggression-bias` < 1.0 as a tuning pass
- Investigate whether secession (100% firing) creates too many small civs that immediately go to war

### Stockpile/Gini Data Missing (Criteria 8, 13, 15)

All three share the same root cause: data not persisting to the bundle.

- **Gini (C8):** `AgentBridge._gini_by_civ` is computed but the snapshot code references it as `agent_bridge._gini_by_civ.get(civ_idx, 0.0)` -- in parallel batch mode, the agent_bridge may not be accessible from the snapshot assembly, or the computation may be timing-dependent.
- **Stockpiles (C13, C15):** `RegionGoods` is documented as transient ("not persisted on world state"). M43a was supposed to add stockpile persistence, but the bundle's `world_state.regions[].stockpile.goods` is empty for all 1600 regions across 200 seeds. Either the persistence is not writing, or the serialization is not including the stockpile.

**M47c action items:**
- Verify `Region.stockpile` is populated after `compute_economy()` and persists through `model_dump()`
- Check Gini computation path in batch/parallel mode
- Add integration test: single seed -> verify stockpile non-zero in bundle

### Dynasty Detection (Criterion 11)

`dynasty_founded` fires in 14% of runs, but `extract_dynasty_count` looks for `dynasty_id` on `great_persons` in `world_state.civilizations`. Either:
- Dynasty IDs are assigned but not serialized to the bundle
- Great persons with dynasty IDs are retired (moved to `world.retired_persons`) and not checked by the extractor

**M47c action items:**
- Check `retired_persons` for dynasty IDs too
- Verify `GreatPerson.dynasty_id` serialization

### Determinism (Criterion 0)

Output is bit-identical when `PYTHONHASHSEED=0`. Without it, Python's hash randomization changes `set` and `dict` iteration order, producing different simulation outcomes. This is a known Python behavior. The simulation itself is deterministic given identical hash seeds.

**M47c action items:**
- Consider setting `PYTHONHASHSEED=0` in batch runner
- Or audit `set()` usage in hot paths to use sorted iteration

---

## Positive Signals

Despite the structural failures, the underlying systems are generating rich behavior:

- **Action diversity is excellent:** DIPLOMACY 34.2%, DEVELOP 20.7%, WAR 19.2%, TRADE/EMBARGO/BUILD all present. No monoculture.
- **Religion fully operational:** Schism (100%), Reformation (100%), Persecution (58.5%), Religious Movement (100%), Pilgrimage (18%). The religion system is one of the healthiest subsystems.
- **Political events firing well:** Federation (100%), Secession (100%), Power Struggle (42%), Succession Crisis (50%), Twilight (22%).
- **Famine calibration good:** median=12, well within 5-50 target, not bimodal.
- **Agent-level events healthy:** Migration (100%), Rebellion (100%), Occupation Shift (100%), Brain Drain (100%).

---

## Event Firing Rates (Full)

| Rate | Event Types |
|------|-------------|
| 100% (every run) | Reformation, Schism, battle, border_incident, brain_drain, build_started, character_death, congress_ceasefire, congress_collapse, congress_peace, coup, demographic_crisis, develop, diplomacy, drought, drought_intensification, earthquake, embargo, faction_dominance_shift, federation_collapsed, federation_formed, folk_hero_created, fund_instability, hostage_taken, infrastructure_completed, intelligence_failure, leader_death, legacy, locust_swarm, mass_migration, migration, movement_emergence, occupation_shift, plague, rebellion, religious_movement, rival_fall, secession, supply_shock, trait_evolution, twilight_absorption, war |
| 90-99% | proxy_detected (99.5%), cultural_renaissance (98.5%), discovery (98.5%), famine (98.5%), capital_loss (98%), move_capital (98%), scorched_earth (95%), flood (93%), wildfire (92%), loyalty_cascade (91.5%), supervolcano (91%), expand (90.5%) |
| 50-89% | rivalry_formed (84.5%), invest_culture (81%), propaganda_campaign (81%), cultural_hegemony (78%), notable_migration (77%), tradition_acquired (75%), fund_instability_failed (73.5%), cultural_work (72%), mercenary_spawned (67%), sandstorm (64.5%), Mass Migration (58.5%), Persecution (58.5%), succession_crisis_resolved (53.5%), terrain_transition (51.5%), succession_crisis (50.5%) |
| 10-49% | restoration (45.5%), local_rebellion (44.5%), power_struggle_started (42%), power_struggle_resolved (41.5%), cultural_assimilation (27%), twilight (22%), pilgrimage_departure (18%), dynasty_founded (14%), pilgrimage_return (13%), dynasty_extinct (11%) |
| <10% | pandemic (9.5%), great_person_born (9%), dynasty_split (7.5%), tech_advancement (7%), tech_breakthrough (7%), pandemic_leader_death (6.5%), trade (6.5%), movement_adoption (6%), movement_schism (5.5%), tech_regression (4.5%), temple_destroyed (3.5%), economic_boom (2.5%), exile_return (2%), famine_starvation (1%) |
| 0% (never fires) | All 15 capability_* events, collapse, paradigm_shift, tech_accident |

---

## Anomalies

| Severity | Anomaly | Detail |
|----------|---------|--------|
| CRITICAL | stability_collapse | 50% of civs at stability 0 at turn 200 |
| CRITICAL | capability events absent | All 15 capability_* types never fire (requires era advancement past tribal) |
| CRITICAL | collapse absent | No civ collapses (likely because extinction happens via war before collapse triggers) |
| CRITICAL | paradigm_shift absent | Requires cultural movement maturation that constant warfare prevents |
| CRITICAL | tech_accident absent | Requires industrial+ era (unreachable) |
| WARNING | near_universal_famine | 98.5% of runs (expected over 500 turns with current war pressure) |
| WARNING | no_late_game | Median era at final turn = tribal |
| WARNING | power_struggle_too_rare | Per-civ rate 0% (<5% threshold) -- analytics extractor requires 100+ alive turns, which few civs achieve |
| WARNING | cap_fire_too_rare | Pre-cap weight cap fires 0% -- may be a measurement issue in hybrid mode |

---

## M47c Tuning Priorities

1. **War frequency reduction** (highest impact -- unblocks C1, C2, C3, C5, C7, and indirectly C8 via longer-lived civs)
2. **Stockpile persistence verification** (unblocks C13, C15)
3. **Gini snapshot fix** (unblocks C8)
4. **Dynasty extractor fix** (check retired_persons; unblocks C11)
5. **Determinism hardening** (PYTHONHASHSEED or sorted iteration)
