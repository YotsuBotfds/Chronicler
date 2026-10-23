# Campaigns, battles and occupation (M60 production war layer)

Status: implemented in `src/chronicler/war/`, behind `WorldState.campaigns_enabled`
(CLI `--campaigns` / `--no-campaigns`; persisted in `state.json` so resume keeps
the setting). With the switch off, the instant `resolve_war` path in
`action_engine.py` runs exactly as before.

Default: new worlds created by the CLI, batch and live entry points enable
campaigns (`war.params.CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS`); `--no-campaigns`
restores instant wars. Resumed or supplied worlds keep their saved setting, and
`WorldState`'s own default stays off, so pre-M60 states and directly constructed
worlds (unit tests, frozen corrected-baseline workloads, which pin
`campaigns=False` in `scripts/benchmark_headless.py`) are unchanged. The flip is
a single commit and can be reverted alone.

This layer wires the detached M60a logistics kernel (`campaign_logistics.py`,
see `docs/experiments/campaign-logistics.md`) into the turn loop and adds the
planned M60b mechanics: battles, sieges and occupation, plus war aims and
negotiated peace. The simulation decides everything; the narrator only receives
the events listed at the end.

## Turn placement

```
Phase 5  actions        WAR  -> declare_or_press_war (declare, raise/reinforce)
                        DIPLOMACY toward a war enemy -> sue_for_peace
Phase 5b campaigns      tick_campaigns (below)
Phase 6-9               unchanged
agent tick              native pool applies queued war casualties first
post-tick               reconcile_rosters against the Phase 10 snapshot
Phase 10                unchanged
```

`tick_campaigns` (in `war/runtime.py`) runs, in order:

1. reconcile `WarRecord`s with `world.active_wars` (both directions);
2. drop armies of dead civs; rebind native rosters if the agent pool changed;
3. threat-driven mobilization (a civ at war raises an army when hostile
   armies are within three hops of its land or its land is occupied);
4. orders for every army (`war/ai.py`), deterministic, no RNG;
5. M60a logistics per army, then movement (`war/logistics.py`);
6. field battles where hostile armies share a region;
7. sieges, garrison fights and liberation of own occupied land;
8. occupation upkeep, revolts and annexation (`war/occupation.py`);
9. war score and peace evaluation (`war/peace.py`);
10. demobilization; per-civ military-stat losses flushed through the
    accumulator.

All stat changes go through the turn accumulator (`keep` for treasury,
`guard-action` for military losses, `guard-shock`/`signal` for stability), so
hybrid mode routes them to the native tick like the rest of the simulation.

## State

Persisted models (in `models.py`): `Army`, `WarRecord`, `Occupation`,
`BattleRecord`, `TreatyRecord`, all under `WorldState.war_state`, plus
`Region.occupied_by`. `Region.controller` remains the legal owner during an
occupation, so production, politics, secession and the native pool keep their
ownership semantics; the occupier is `occupied_by` plus the `Occupation`
record. `world.active_wars` stays the single source of truth for who is at
war; `WarRecord` holds the campaign bookkeeping and is reconciled every turn,
so wars started or ended elsewhere (federation defense, diplomacy, congress,
vassalization, extinction) are handled rather than duplicated.

## Armies and enlistment

`war/armies.py`. Muster size is drawn from the civ's controlled population:
`pop * (60 + 2.4 * military) / 1000`, at least 3 soldiers, capped so total
enlistment stays under 25% of the population. Raising costs treasury
(0.5 per soldier) and each army costs upkeep (0.3 per soldier per turn). At most
two armies per civ, three turns between musters. Armies carry full kits
(`POLICY.carried_limit` rations per soldier) and the civ's best free general.

* `--agents off`: the army is an aggregate head count; soldiers remain part of
  the population, and casualties permanently drain it (`distribute_pop_loss`).
* agent modes (demographics-only, shadow, hybrid): `select_recruits` reads the
  current snapshot and enlists real agents of the civ's polity in its
  unoccupied regions: soldiers first, then farmer levies, nearest to staging
  first, never named characters or agents already enlisted. The roster stores
  `(agent_id, region)` pairs and `soldiers == len(roster)` always holds.
  Casualties pick roster ids with a namespaced RNG, queue them on the native
  `AgentSimulator.queue_targeted_deaths` (killed at the start of the next tick
  in the same death batch as catastrophe deaths) and drain the Python region
  population so same-turn phases agree. After the tick, `reconcile_rosters`
  drops agents that died naturally (disease, plague, age) and refreshes their
  regions. After a resume the native pool is new, so `rebind_rosters` drafts
  the same head count afresh. Deserters and demobilized soldiers leave the
  roster alive.

## Logistics (M60a in production)

`war/logistics.py` applies the kernel's frozen order per army cohort
(orders -> replenish -> consume -> stress -> desert -> move -> settle) with the
kernel `Policy` record `war/params.POLICY` and the kernel's own arithmetic
(`supply_distance`, `stress_components`, `next_morale`, extracted from
`advance()` so the detached receipts are unchanged).

| Kernel input | Production source |
| --- | --- |
| topology | `world.regions` adjacency by region index, symmetrized, validated by the kernel |
| supply sources | regions the civ holds (owned and unoccupied, or occupied by it) |
| replenishment | 3/2/1/1 rations per soldier at supply distance 0/1/2/3, scaled by paid upkeep; foraging off non-friendly land by terrain and population |
| unmet needs | unpaid fraction of this turn's upkeep |
| information quality | `compute_accuracy` of the civ about its enemy |
| desertion draw | one namespaced draw on the cohort's expected deserters |

Production extensions: treasury upkeep; attrition deaths by terrain (plains 3,
forest 6, mountains 12, tundra 18, desert 20 per mille per turn) plus hunger,
distance beyond supply range, unreachable supply, winter in rough terrain and
siege disease (halved under shrewd generals); movement cost (two turns into
mountains or tundra). Armies move one edge per turn, an army sharing a region
with an enemy is engaged and holds, low morale stalls marching (but not
retreat).

## Battles and sieges

`war/battles.py`. Power = soldiers x quality, where quality multiplies tech era
(`1 + 0.12 * era`), morale (`0.5 + morale/1000`), supply (0.8 when out of food),
asabiya, the martial tradition and the commanding general (+15%, +10% more for
attack/defense traits). The relative-era `tech_war_multiplier` applies to both
sides. The side holding the ground multiplies by terrain and role defense,
rivers (+10%), fortifications (`K_FORT_DEFENSE_BONUS` x era fortification
multiplier) and home ground (+10%). Both sides draw noise in [0.85, 1.15] from
`random.Random(stable_hash_int("war", "battle", seed, turn, war, region, kind,
attacker))`. A 1.15 power ratio is decisive; losers lose 18-60% and winners
4-14%, scaled by the ratio; stalemates cost both 10%. Losers retreat one edge
toward held land (trapped armies lose another 20%); armies under three soldiers
break (survivors scatter, the victor may take a hostage). Generals may fall.
Hired mercenary companies march with the hirer's largest army and lose strength
with it.

Hostile armies in one region fight a field battle. An army alone in an enemy
region fights its militia garrison (6% of the population plus military/10),
or, when the region is fortified, its capital or settled, besieges it: each turn
costs the city 2% of its people and 15% of its food; after 2 turns (+2-3 for
fortifications, +1 capital, +1 settlement, -1 when overwhelming) it is
assaulted with fortifications at half weight. An army in its own occupied land
fights the occupation garrison to liberate it.

## Occupation

Winning a region starts an `Occupation` (unrest 150, more under a foreign
culture; plunder and food requisition; capital occupation shocks the owner).
Each turn the owner loses taxes and stability and gains war weariness, the
occupier gets requisitions, and unrest moves by +35, +40 under a foreign
culture, +30 when the occupier is the target of a proxy war, minus garrison
suppression (8 per soldier, at most 160). Above 500 unrest the region
depopulates; above 600 it may revolt: partisans (up to 20% of the population)
fight the garrison and either liberate the region or are crushed with
reprisals. A quiet occupation (unrest under 450, garrisoned) held 15 turns is
annexed through `action_engine.apply_region_conquest`, the same path the
aggregate WAR resolution uses (bridge realignment, conquest signals, scorched
earth, artifacts, conversion). An occupier that collapses frees the region; an
owner that vanishes cedes it.

## War aims, score and peace

`war/peace.py`. New wars pick an aim: liberation when the enemy holds regions
of the attacker's culture; vassalization when much stronger (perceived
military ratio at least 1.5, stable, leader-trait biased, seeded); tribute when
poor or for shrewd leaders; otherwise conquest of the most valuable frontier
region. Declaring war marks both sides hostile and triggers federation defense.
Attacking armies target the aim; defenders engage threats, liberate their land,
then counterattack once winning.

War score (attacker perspective, clamped to +/-100) = battle points (6 plus up
to 12 per victory by enemy losses, +5 per successful siege, fading one point
every third turn) + 12 per occupied region (+20 for a capital). Each turn after
the third:

* |score| >= 60: the loser capitulates with probability `0.25 + weariness/40`;
* |score| >= 20 and 8+ turns: negotiated peace with `0.04 + weariness/60 + turns/400`;
* 15+ turns: white peace with `0.02 + (both weariness)/100` (+0.15 with no armies).

A DIPLOMACY action toward a war enemy is a peace offer on the same terms: the
winning side offers a negotiated peace in its favour, the losing side offers to
accept the enemy's terms, and a near-parity white peace can only be agreed
after eight turns of war (earlier gate runs ended wars before armies arrived).
A treaty imposes a ten-turn truce on new wars between its parties. Terms
by aim: conquest cedes occupied regions (all on capitulation, one otherwise, and
only a capitulation can take the loser's last region); liberation cedes
culturally matching occupied regions; tribute and unrewarded wins transfer
treasury; a vassalization capitulation calls `politics.resolve_vassalization`
(existing tribute and rebellion systems take over). Remaining occupations are
returned, the war leaves `active_wars`, both sides become suspicious, the
treaty is named (`generate_treaty_name`) and recorded on both relationships.
Battle casualties and occupation feed `war_weariness`, which already damps WAR
weights. A WAR action from a civ that cannot muster an army (too small, broke,
cooling down) is a threat only: no phony war is declared.

## Narration and viewer

Events: `war_declared`, `army_raised`, `war` (one per battle, `actors =
[battle attacker, defender]`, description carries `attacker_wins` /
`defender_wins` / `stalemate` so traditions, factions and general generation
keep counting victories), `siege_begun`, `occupation`, `occupation_revolt`,
`liberation`, `annexation`, `civ_conquered`, `peace_treaty`, `war_ended`,
`army_destroyed`, `army_disbanded`, `general_fallen`, `hostage_taken`; DIPLOMACY
peace offers keep event type `diplomacy`. Named events: battles and sieges
(`generate_battle_name`), occupations ("The Fall of X" for capitals), uprisings,
annexations and treaties.

Viewer bundle: `world_state.war_state` (armies, wars, ended wars, occupations,
all battle and treaty records) and `history[n].campaign` with that turn's
armies, battles, occupations and war scores. `TurnSnapshot.campaign` is omitted
while `None`, so default-off snapshots keep their exact historical bytes; the
new `WorldState`/`Region` defaults are registered in
`scripts/third_wave_controls.py` like earlier dormant schema additions.

## Determinism

No module-level RNG is touched. Every draw comes from
`war_rng(ctx, namespace, *parts)`, i.e. `stable_hash_int("war", namespace,
seed, turn, ...)`; iteration is over lists or sorted keys only; ties break on
region index or army serial. Native casualties are explicit id lists. Tests
cover same-seed identity in off and hybrid modes and save/load continuation.

## Verification

`tests/test_war_logistics.py`, `test_war_armies.py`, `test_war_battles.py`,
`test_war_occupation.py`, `test_war_peace.py`, `test_war_integration.py`
(fixtures in `tests/war_fixtures.py`); Rust tests in `tick.rs` cover the
targeted-death queue and that an empty queue matches the plain tick. The M53b
runner forwards `--campaigns` to every run.

## Known gaps / follow-ups

* Enlisted native agents stay in their home region in the pool; the army's
  location is campaign state only (no native agent movement API).
* Naval movement, sea routes and coastal landings are not modeled; armies use
  land adjacency only.
* Vassal levies, allied joint armies and coalition battles beyond pairwise
  civ-vs-civ engagements are not modeled.
* Battle and logistics parameters are illustrative calibrations, not fitted
  against the 200-seed gate.
* The viewer renders the new bundle data only through its generic views; no
  dedicated army/battle map layer yet.
