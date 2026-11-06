# AUDIT-D — Program D (institutions, war, human consequences) and A5/D4 (owned stock through war, death, migration)

Audit lane, read only. Date 2026-11-06.

**Source audited.** Checkout `/home/user/Chronicler` at `a955e42` (`claude/connected-world`, the lead's S0
skeleton). `git diff --stat 8abc1acb a955e42 -- src chronicler-agents` is empty, so every line reference
below is also the original reference `8abc1acb`. Native extension used for the three small runs:
`~/.venvs/chronicler-native` (installed 15:59 today by the lead; not rebuilt or modified here).

**What was run.** Only read-only tools, plus:
- `scripts/refactor_preflight.py --json` on 61 candidate files (read only). Raw output and summary:
  `audit-d/preflight.json`, `audit-d/preflight-summary.txt`.
- Three tiny CLI runs on **development template seed 7** (one process at a time, `PYTHONHASHSEED=0
  RAYON_NUM_THREADS=1 CHRONICLER_QUIET=1`, `--simulate-only`, about 1 s each) to check recorded limit RL3.
  Outputs: `audit-d/rl3/{a,b,c,d,e}` with logs.
- No tests, no oracle lane, no native build, no other seeds.

Labels: **[verified]** read in code and/or reproduced; **[inferred]** follows from code read, not executed;
**[unverified]** stated by docs or plausible, not checked.

---

## 0. Summary of findings

1. **RL1 (two conquests in one turn destroy owned stock once)** is a real asymmetry. The commons and the
   granary are destroyed **per conquest call**, but owned stock only **once per turn**. The retail ledger
   detects conquests through `Region.last_conquered_turn`, an integer turn, not through the event. It is
   reachable only with **`--no-campaigns`** (instant wars). With campaigns on (the default for new worlds),
   one region cannot be conquered twice in one turn. The record also names whoever controls the region
   when the loss is applied, not the conqueror. Disposition: defect. Fix it behind a retail rules version
   by hooking `apply_region_conquest` itself, as RS2 and the granary already do.
2. **RL2 (occupation and siege do not requisition owned stock)** is a missing capability. In current code
   the commons "requisition" is **destruction**: the food is multiplied away and goes nowhere. The plunder
   and per-turn requisition paid to the occupier are **minted treasury**, not taken from anyone. A5 should
   take the same share from owned stock at the same events, label it honestly as war loss by cause, and
   record it exactly once per event. Turning requisition into a real transfer (to army rations, with
   restitution) is D4.
3. **RL3 (legacy JSON state-file resume runs neither L2 nor retail hooks)** **does not reproduce as
   stated.** With `--agents hybrid`, a legacy resume runs both L2 and retail. The pool reset closes the
   claims to the commons, dated, and retail settles every resumed turn **[verified, seed 7]**. The real gap
   appears when `--agents hybrid` is omitted:
   - a saved retail world is refused, but through an uncaught `ValueError` traceback (rc 1);
   - a saved L2-only world runs **silently in aggregate mode**, while `world.agent_mode` stays `"hybrid"`
     in `state.json` and the bundle. L2's frames are correctly null.
   Classification: a defect (silently inert switch, stale persisted mode) plus an intentional boundary
   (a legacy resume is inexact, and id-bound records close).
4. **Soldiers are counted at home.** Enlisted agents never move natively, so they keep counting in home
   **food demand**. Enlisted farmer levies also count in home **farm labour**, and retail **titles them
   for that labour**. Army rations are **minted** (refill and forage take no food from anyone). Health
   care already excludes enlisted people as patients and caregivers. D3 and D4 must not change one of
   these without the others.
5. **Two war-mortality authorities already exist:**
   - the campaign casualty path (targeted deaths);
   - native `mortality_rate`, which doubles the mortality of every Soldier-occupation agent of a civ at
     war, on a roster or not. `reconcile_rosters` then books those natural deaths as `army.casualties`.
   Combat injury must not add a third authority.
6. **Roster identity on non-exact resumes.** `rebind_rosters` **keeps** a roster whose ids all exist in
   the rebuilt pool. New pools reuse ids from 1, so the kept roster can name strangers, and later
   casualties kill them. This is pre-existing and documented in RS3, but it is a correctness defect for D3.
7. **No individual taxpayer exists.** Treasury tax is computed from merchant wealth without debiting
   anyone. City dues come from an abstract commerce term. So "grievances grounded in recorded taxes" can
   only be city-level or civ-level today. Several grievance-to-influence channels already exist:
   - native needs, which drive movements;
   - `city.grievance` (sacks, levies, L4 rules, L9 broken promises);
   - diplomacy grievances (war and occupation kinds);
   - finance creditor grievance;
   - governance PSI;
   - factions.
   D1 and D2 must reuse or replace them, not add parallel ones.
8. **Pins.** A Python-only first A5 slice touches only unpinned files: `household_retail*.py`,
   `action_engine.py`, `war/occupation.py`, `war/battles.py`, `livelihoods.py` and a new test file and
   chunk. A rules-version CLI key needs `batch_manifest.py`, which is pinned
   (`livelihoods_pl4_source_inverse.json`) and so needs a reviewed inverse layer from the lead.
   Pinned files:
   - D3 changes to `health_care.py`, `health_care_state.py` and `health_care.rs` (whole-file digests in
     `tests/test_health_care_policy.py:1017-1027`);
   - `simulation.py`, `main.py`, `models.py`, `agent_bridge.py`, `grain_reserves.py`;
   - native `pool.rs`, `tick.rs`, `economy.rs`, `ffi/mod.rs`.

---

## 1. Q1 — Owned-food lifecycle (A5/D4)

### 1.1 Where the ledger lives

- State: `world.livelihoods.household_retail` (`HouseholdRetailState`,
  `src/chronicler/household_retail_state.py:162-212`). One `RetailRegion` per open pilot region holds:
  - `goods`: milli-food per good, in grain/fish/salt/botanicals/exotic order;
  - `claims`: stable id → milli-food, with `sum(claims) == sum(goods)` always;
  - `war_loss_turn` (`:111-114`).
  Owned food is never in `region.stockpile`, which is the commons. Exactly-once guards: `last_title_turn`,
  `last_settled_turn` and `last_procured_turn`. The transient `_turn` (books per region) never pickles.
- Logic: `src/chronicler/household_retail.py`. `_debit` (`:341-363`) moves claims and goods by equal
  totals. `check_region` and `check_owner` (`:376-403`) enforce `close = open + Σ sign × flow` per good
  and per owner after each mutation. `FLOW_KINDS` (`state:47-54`) are titled, own_eaten, sold, procured,
  decay, overflow, war_loss, to_commons, inherited_in and inherited_out.
- Turn placement: Phase 2 `prepare_phase2` (`:714`) and `finish_phase2` (`:799`); Phase 5/5b war; then
  `before_agent_tick` (`:981`), the native tick (provisioning at 0.7), `after_agent_tick` (`:1304`), the
  Phase 10 procurement seam (`:1353`) and `phase10` (`:1455`).

### 1.2 Event-by-event lifecycle

| Event | What happens to owned stock | Kind | Exactly once? | Recorded | Evidence |
| --- | --- | --- | --- | --- | --- |
| **Conquest** (`apply_region_conquest`: instant WAR win, occupation annexed as consolidated, owner gone or by treaty) | `v − floor(v × 0.5)` per good, claims pro rata (largest remainder, ties by id) | **destruction** | Once per **turn**, not per event: guarded by `when <= reg.war_loss_turn` with `when = region.last_conquered_turn` | flow `war_loss`, counter `war_loss_milli`, record `war_loss` with note `"conquered by {region.controller} on turn {when}"` | `household_retail.py:493-515`; checked at `:723` (Phase 2) and `:989` (before tick); `action_engine.py:643` sets `last_conquered_turn` |
| Same turn, commons and granary (for comparison) | commons `*= 0.5` **per call** (`action_engine.py:633`); granary 50% "seized" per call (`:637`, `grain_reserves.py:384-401`, destroyed); RS2 damage once per asset per turn (`repair_projects.py:769`) | destruction | per call (commons, granary) / per turn (RS2) | granary flow `SEIZED` with `buyer=granary.owner` (the victim, in a field named "buyer") | as cited |
| **Two conquests in one turn** | owned ×0.5 once; commons ×0.25; granary ×0.25 | inconsistent | no (RL1) | one record naming the **last** controller | §1.3 |
| **Peaceful controller change** (secession, free city, twilight absorption, nomad abandonment, collapse) | nothing | — | — | — | test `test_a_controller_change_without_a_conquest_destroys_nothing` |
| **Region loses its controller** (collapse `simulation.py:1467`, nomad abandonment `nomads.py:873`, politics) | at the next Phase 2 the pilot region closes: **all** claims go to the region's commons, even when the owners are alive | **transfer** (owners → commons) | once (`_book` refuses re-entry the same turn) | flow `to_commons`, commons reason `pilot_closed`, record `pilot_closed` | `household_retail.py:421-439`, `:518-530` |
| **Occupation** (start: commons ×0.8 and granary 20%; then per turn: owner treasury −2 into nothing, occupier treasury +1 minted, unrest, depopulation above 500 unrest) | nothing (declared limit) | — | — | counter `requisition_exempt_region_turns`, once per region-turn with goods, occupied or besieged | `household_retail.py:990-998`; `war/occupation.py:36-49,67-70,198-203`; `war/params.py:94-107` |
| **Siege** (each siege turn: civilians −2%, commons ×0.85, granary 15%) | nothing (declared limit) | — | — | same counter | `war/battles.py:400-402` |
| **Region depopulation** (war drains, famine, migration) | no special path. Claims of the dead pass by inheritance. Claims of emigrants stay; they can be sold to the remaining buyers and decay | consumption / sale / decay | n/a | normal flows | inferred from `_settle_deaths`; no depopulation branch |
| **Owner death** | Dies at 0.0 before provisioning: the claim is **withheld whole** (neither sold nor eaten). After the tick: spouse (read before the tick, alive anywhere), else equal shares to living children **in the claim's region** (largest remainder), else escheat to the commons. An heir beyond the 4096-claim cap is refused and that share escheats | **transfer** (to heir or commons) | yes: owners absent from the post-tick snapshot, `last_settled_turn`, `t.spouses` read before the tick; inheritance conserves claims (`check_owner`) | flows `inherited_in`/`inherited_out` (claims only), `to_commons` with reason `escheat`; records `inherited` (owner, heir, spouse or child) and `escheat`; native `withheld_dead_claims` and `withheld_dead_milli` checked against the zero rows | `household_retail.py:1247-1301`, `:1304-1338` |
| Inheritance resolution | as above. The native estate order differs: dependants anywhere, then all children anywhere (`household.rs`); Python uses children in the region (lead decision 6) | transfer | yes | — | doc `household-retail.md:130-145` |
| **Owner migration or relocation** | the claim stays in the origin pool; sold there to local buyers and credited by id wherever the owner lives; eaten only when the owner is present | none until sale (remote title) | yes (sales go through the native frame, taken once) | normal sale and money rows | doc `household-retail.md:146-148`; native `provisioning.rs` presence by `pool.regions[s] == region` |
| **Merchant departures** | owned food is never loaded (merchants load commons only, lead decision 7) | — | — | `merchant_food_departing`, `owned_food_unloadable_milli` per frame | `household_retail.py:1438-1452` |
| **Granary procurement** (Phase 10) | the ruler's granary buys owners' grain first, pro rata; owners credited by id (purpose 6) | **transfer by sale** | yes (`last_procured_turn`; `_turn` refuses an uncredited earlier turn) | flow `procured`, money | `:1341-1436`, `grain_reserves.py:558` (pinned seam) |
| **Decay and cap** | native opening decay of the carried owned stock; one storage cap pro rata over commons plus owned, net of merchant departures; applied to claims pro rata | **destruction** (spoilage, overflow) | once per turn (Phase 2 native, `_title_region`) | flows `decay`, `overflow` | doc `household-retail.md:405-452`; RL4 (A's audit) |
| **Pool rebuilt** (legacy state-file resume, fork) | every claim goes to its region's commons, dated | transfer | once (`bind_native_pool` binds once per simulator) | reason `pool_reset`, record | `:1496-1510`, `livelihoods.py:571-594` |
| Switch off / `record_only` | every claim to commons | transfer | at configuration | `switch_off` | `:146-165` |

### 1.3 The code paths behind the recorded limits

**RL1. Same-turn conquest versus duplicate processing.**
- Path: `apply_region_conquest` (`action_engine.py:614-643`) mutates commons and granary immediately and
  per call, then sets `contested.last_conquered_turn = world.turn`. Retail does not observe the call. It
  infers the event from the turn in `_apply_conquests` (`household_retail.py:505-508`). That check exists
  for a legitimate reason: it runs twice per turn (Phase 2 and before the tick), and the second run must
  not reapply the same conquest (the duplicate-processing guard). Keying the guard by turn conflates "the
  same conquest seen twice" with "a second, distinct conquest".
- Reachability **[inferred]**:
  - `--no-campaigns`: `resolve_war` (`action_engine.py:730-848`) picks a random region of the defender.
    Civ A can take region X from B, then civ C (or B) acting later in Phase 5 can take X from A.
  - Campaigns on (default for new worlds, `war/params.py:32`): conquest happens only through
    `annex_occupation` (`war/occupation.py:114-129`). It removes the single occupation of the region, and
    occupations start before annexation inside `tick_campaigns`, so at most one conquest per region per
    tick. Nomad hordes and maritime do not call `apply_region_conquest`.
- Secondary defect: the record note uses `region.controller` at application time
  (`household_retail.py:515`), so after two conquests it credits only the second conqueror and never
  names the victim polity.
- Classification: **defect**. Consistency with the commons authority is the reference, so the
  owned-stock loss should not depend on how many conquests land in a turn. The alternative, "a second
  conquest in the same month finds nothing left to destroy", would also have to change the commons, a
  default-path change, so it is not recommended.
- Disposition: rules version 2 (§7.1). Hook the call: `household_retail.on_conquest(world, contested,
  attacker, defender)` from inside the existing `if getattr(world, "livelihoods", None) is not None:`
  block (`action_engine.py:638-642`). Apply the share at once and record the attacker and defender (index
  and name at the event). In v2 the turn-inferred path is disabled; it becomes an assertion that no
  `last_conquered_turn` advance went unobserved.
- Regression tests: §8.

**RL2. Occupation and siege of owned stock.**
- Path: `_requisition(region, factor, world)` (`war/occupation.py:36-49`) is called from
  `start_occupation` (`:67`, factor 0.8) and `siege_turn` (`battles.py:402`, 0.85 per siege turn). It
  multiplies the commons food goods and seizes the granary. Owned stock is only counted
  (`household_retail.py:990-998`).
- The "requisitioned" food goes nowhere: army rations come only from minted refill and forage
  (`war/logistics.py:86-94`). So requisition in current code is destruction.
- Classification: **missing capability**.
- A5 disposition (v2): add an optional `actor`/`cause` to `_requisition` (callers know the occupier or
  besieger and the war). Call `household_retail.on_war_loss(world, region, factor, cause, actor)`: take
  `v − floor(v × factor)` per good pro rata, as flow `war_loss` with cause `siege` or `occupation`, once
  per call. Two sieges by two wars in one turn mean two losses, matching the commons.
- D4 (later, own switch): make the requisition a real transfer into the army's rations, with the minted
  refill reduced by the same amount, for commons and owned stock alike, plus restitution (§7.2).

**RL3. Legacy JSON state-file resume.**
- **[verified]** On seed 7, a 6-turn run with `--food-allocation --household-retail
  --household-retail-boundary all`, resumed from `state.json` with `--agents hybrid` to turn 10:
  - both L2 and retail frames exist for source turns 6-9;
  - retail `turns_settled` goes 7 → 10;
  - `pool_resets: 1`, and `to_commons_milli` rises from 614 to 84,495 on the first resumed turn: the
    rebuilt pool closed every claim to the commons as designed;
  - the bundle is labelled `metadata.resume = {"kind": "legacy-state", "exact": false, "turn": 6}`.
  So the limit as written ("runs neither") does not hold for a correctly given resume.
- Without `--agents hybrid` (outputs `rl3/c` and `rl3/e`):
  - **retail saved on** → `ValueError` from `livelihoods._check_prerequisites` (`livelihoods.py:455-462`),
    raised as a traceback (rc 1), not a CLI error. The refusal is explicit but crude.
  - **L2 saved on, retail never on** → the run completes in aggregate mode, with no bridge and so no
    livelihoods hooks (`simulation.py:2110,2335`). `allocated_turns` stays 4, the L2 snapshot reports
    `totals/regions = None` (unknown, not zero, correct), and **`world.agent_mode` stays `"hybrid"`** in
    `state.json` and in bundle `world_state.agent_mode`. `_configure_run` only assigns
    `world.agent_mode` for agent modes (`main.py:1890-1892`), and `WorldState.agent_mode` is a persisted
    field (`models.py:1158`).
  - Why L2 is not refused: `_check_prerequisites` checks L2 only when the flag is given True
    (`livelihoods.py:385-386`), unlike retail and timber supply, which also check a saved switch.
- Classification: **defect** (silent inert switch, stale persisted agent mode) plus **intentional
  boundary** (an inexact resume closes id-bound records).
- Disposition:
  1. Treat a saved enabled L2 like retail: refuse it outside hybrid with a `--no-food-allocation` hint.
     This touches only opt-in worlds (`livelihoods.py`, unpinned).
  2. Optionally make every hybrid-only saved livelihoods switch follow the same rule.
  3. Leave the stale `world.agent_mode` on the default path, recorded for E/lead, because fixing it
     changes default output of agents-off resumes of hybrid saves.
  4. Replace the traceback with a clean error in `main.py`. That file is pinned, so it needs an inverse
     layer; it can be deferred.
- Tests: an offline `_check_prerequisites` test for saved L2 outside hybrid, and a native CLI test
  (legacy resume with hybrid gives a settled frame each resumed turn, `pool_resets == 1`, all claims to
  the commons on the first resumed turn).
- Update the board entry: "pending" → this disposition.

---

## 2. Q2 — Owned or earmarked cargo whose custody crosses regions

| Stock | Owner | Custody across regions | What war does | Evidence |
| --- | --- | --- | --- | --- |
| Retail owned food | persons by id | **Title** crosses regions (a migrant or heir lives elsewhere); the **food** never moves | conquest loss (once per turn, RL1); none for siege or occupation (RL2) | §1 |
| Native merchant cargo (`trip_cargo_qty`) | nobody (commons loads; the merchant earns a margin) | origin → destination over several turns | A controller change of the origin, destination or current region **unwinds** transit cargo to the origin (receipt `RETURNED_CONTROLLER_CHANGE`), and loading reservations are cancelled (`merchant.rs:1326-1372`, called `tick.rs:619`). Death in transit also unwinds to the origin (`merchant.rs:1300-1316`). Maritime raids seize (destroy) it (`merchant.rs:84-88`) | native |
| PL1 expedition timber cargo | the home region's RS2 earmark (public, not by id) | forest region → home store (`timber_supply.py:69-91`) | The home region changing hands **abandons** the expedition; its cargo is deposited in the **forest** region's commons, since no position is tracked. A forest lost to another civ stops cutting and the crew walks home | `timber_supply.py:83-91, 537-538, 594, 1116` |
| PL1 timber store | the region (not civ- or id-bound) | stays in the home region | **untouched** by conquest, occupation and siege (commons halved, store not). The new controller's RS2 uses it | `timber_supply.py:917-919, 1090-1127` |
| Grain convoys (`--grain-convoys`) | the buying civ (public) | multi-turn routes | each cargo ends in exactly one outcome: arrived, **captured** (captor's market, a real transfer), **lost** (sink), returned or stranded. Seeded per convoy and turn | `grain_convoys.py:30-58` (best precedent for owned cargo) |
| Public grain shipments | the buyer civ | origin → destination | captured on delivery counted when the controllers changed | `public_grain_shipments.py:200, 235-236` |
| Granary grain | the ruler (civ index) | in place | conquest: 50% destroyed, remainder **captured** by the new ruler in the next Phase 10; abandoned → commons | `grain_reserves.py:270-292` |

No owned cargo by stable id moves physically today. The precedent for A4/A5 cargo is grain convoys: a
named destination per outcome, exactly once, and capture (a transfer) kept distinct from loss
(destruction).

---

## 3. Q3 — What war takes or destroys, by which authority and budget

| Event | Treasury | Food | Infrastructure or assets | Population | Authority | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Raise army | −0.5 per soldier (spend, `keep`) | — | — | agents enlisted (stay home natively) | campaign | `war/armies.py:168-226` |
| Upkeep | −0.3 per soldier per turn | army rations **minted** (refill by supply distance × paid share; forage minted, not debited from the foraged region) | — | — | campaign logistics | `war/logistics.py:75-94` |
| Battle | — | — | generals may die | roster victims → `queue_targeted_deaths`; Python region drain (same-turn view, overwritten by native write-back `agent_bridge.py:3059-3066`) | campaign casualties | `war/armies.py:315-339`, `battles.py` |
| Siege turn | — | commons ×0.85 (destroyed); granary 15% (destroyed) + RS2 granary damage | — | civilians −2% (`SIEGE_CIVILIAN_LOSS_PERMILLE = 20`) as anonymous native catastrophe deaths | campaign | `battles.py:400-402`, `occupation.py:36-49` |
| Occupation start | occupier +pop//10 "plunder" (**minted**, not taken from the owner) | commons ×0.8; granary 20% | artifact sack intent | — | campaign | `occupation.py:52-81` |
| Occupation per turn | owner −2 (spent into nothing), occupier +1 (minted) | — | — | above 500 unrest −1%/turn; revolts kill partisans and garrison | campaign | `occupation.py:197-208` |
| Conquest | — | commons ×0.5 per call; granary 50% destroyed, remainder captured | RS2 granary and workshop damage (once per asset per turn); scorched earth (infrastructure inactive, by defender stability); temple destroyed by a militant conqueror; `pending_build` cleared | agents realigned to the new civ | `apply_region_conquest` | `action_engine.py:614-708`, `infrastructure.py:216-240` |
| City sack | sacker + int(loot) (a **real transfer** from the civic purse; fraction destroyed) | — | RS2 damage | — | cities | `cities.py:605-628` |
| Peace | loser → winner reparations or tribute (**real transfer**: spend then add) | — | regions ceded through `annex_occupation` (a conquest: commons and owned −50% again) | — | peace | `war/peace.py:251-261` |

**Where owned-stock requisition can plug in without fabricating damage.**
1. At the two `_requisition` call sites, with the same factor at the same event as the commons (A5 v2).
   No new damage is invented; the existing commons loss is applied to the other pool of food in the same
   region.
2. At `apply_region_conquest` (conquest share, A5 v2).
3. For a real **transfer** (D4), at `logistics_step`: requisitioned food can replace minted refill
   ration for ration, so the army eats real food instead of gaining it twice.

Restitution can be grounded in the existing real reparation transfer (`peace.py:259-261`) and in
recorded requisitions by id. Reconstruction of buildings already exists in RS2 (war damage → repair
projects with budgets).

---

## 4. Q4 — D2 attribution: actor, victim and cause

### 4.1 What is recorded, and in what identity

| Flow | Actor | Victim | Cause | Identity | Through conquest / civ death / secession / checkpoint |
| --- | --- | --- | --- | --- | --- |
| Treasury tax (native) | — (civ receives) | **nobody**: `tax_rate × civ merchant wealth`, merchants not debited | — | civ index | minted, so no grievance can be grounded in a payer (`economy.rs:2283`; `economy.py:2113`; `simulation.py:1801`) |
| City dues | lord (`city.lord` civ index) | the city purse (abstract commerce) | charter share, levy | civ index; owed per civ, paid next Phase 2 | dropped if the lord holds no region at payment (`cities.py:995-1012`); a city's lord changes on conquest (`cities.py:566-600`) |
| Guild levy | lord | city / guild | lord short of money or at war (`guilds.py:89`) | settlement id, civ index | city history tuple `levy` |
| Retail war loss | **controller at application** (free text) | owners (pro rata) | conquest | names in `note` | wrong after two conquests (RL1) |
| Granary seizure | **not recorded** | `buyer=granary.owner` (victim in a field named "buyer") | — | civ index | `grain_reserves.py:399` |
| RS2 war damage | `(war_key, start_turn)` (pair of names) | asset (index), region index | conquest, sack, seizure | index + war key | `repair_projects.py:700-788` |
| Occupation | occupier name | owner name | war_key | names | persisted in `war_state` |
| Diplomacy grievance | the other civ (name key) | the holder civ (name key) | kinds war, occupation, treaty, border, faith, embargo | `world.relationships[name][name].memory` (despite the "index" docstring in `diplomacy_state.py:1-9`) | a new breakaway civ starts with empty memory (`politics.py:463-468`), so victims' grievance stays with the old polity |
| Finance creditor grievance | debtor civ index | creditor | default | civ index | `finance.py:258, 1061, 1456-1462` |
| RS3 veteran record | served civ index, `army_id`, `(war_key, start)` | the person (stable id) | release cause | index + id | pool reset closes the records |
| Native memory | `source_civ` u8 index | the agent | Battle, Conquest, Persecution, DeathOfKin, Migration, ... | civ index | in the pool (exact checkpoint only) |
| Army casualties | — | roster ids | **natural deaths merged in** (`armies.py:420`) | ids | conflates battle, attrition and natural |
| Civilian war deaths | — | anonymous (catastrophe count per region) | — | region | no person-level cause |
| Provenance events | `actors` names, `region` name, `causes` ids | — | recorded at emission | names | persisted; documented as **never read by simulation decisions** (`causal-provenance.md:9-12`) |

**Civ identity.**
- `world.civilizations` is append-only: no remove or pop anywhere. Appends happen in
  `politics.py:469,1241` and `politics_bridge.py:929,1004`, so indices are stable and dead civs keep
  their index.
- **Restoration reuses the dead civ object** (same index, same name, `politics.py:1198-1203, 1226-1236`). Anything
  attributed to the old polity (diplomacy memory, RS3 "served civ", native `source_civ`, provenance keys)
  silently applies to the restored polity. That is acceptable if declared, but D2 must state it.
- Breakaway names are deduplicated (`politics.py:266-273`). `transfer_regions_to_new_civ` (`Free
  <region>`) name uniqueness **[unverified]**.
- Region identity is a stable index; `region.controller` and `civ.regions` are names.

**Checkpoints.** Exact checkpoints pickle everything, the native pool included (`run_checkpoint.py:1-28`).
Legacy JSON keeps Pydantic fields but rebuilds the pool: id-bound records close and rosters are redrafted
or kept stale (§6).

### 4.2 Who knows what (omniscience risks)

- Civ-level decision code reads true state:
  - diplomacy grievances know exactly who invaded;
  - peace uses true war score;
  - `select_recruits`, occupation and siege use true populations.
  War AI partly uses perceived stats (`compute_accuracy`, `war/logistics.py:55-63`).
- Non-omniscient carriers already exist:
  - native per-agent memories (event type, `source_civ`, turn, intensity);
  - knowledge packets (threat, trade, religious, movement news), carried by bond and adjacency, with
    hops, decay and `pkt_source_civ` at observation;
  - the city's own history and grievance.
  Person-level foreign grievance should be built only from these.
- **Do not read `WorldState.provenance` in any decision.** That would break its no-feedback contract and
  give agents omniscient causal links.

### 4.3 Existing grievance → influence channels (duplicate-influence map)

| Channel | Input | Output |
| --- | --- | --- |
| Native needs (material, autonomy, spiritual) | food and wealth, foreign rule, displacement, persecution, faith | satisfaction → migration and rebellion; movements' grievance |
| Movements (default on) | needs census; reform credit 0.3 (`movements.rs:102-104`) | demands, crackdowns, risings, secession, institutions |
| `city.grievance` (shared capped channel) | sack (`cities.py:618`), L4 enforced rule (`commons_rules.py:95-98`), L9 broken promise (`local_budgets.py:77-104`), levy | city unrest → urban revolt, free city |
| Diplomacy grievance (default on) | war declared, battles, occupied turns (1.5/turn), land lost (12), capital, breach, persecution, embargo, raids (`diplomacy.py:111-130`) | disposition ceilings, revanche in WAR scoring |
| Finance creditor grievance (default on) | defaults | WAR/EMBARGO weights (`finance.py:1456-1462`) |
| Governance PSI and legitimacy (default on) | famines (immiseration), elites, fiscal | revolts, civil wars |
| Factions | events | action weights, succession |

Every war harm (occupation, sack, food loss) already reaches at least two of these channels. A new D2
grievance from requisition must **replace a proxy** (for example, scale diplomacy's flat occupation
increment by recorded requisition value) or feed an existing channel, never stack.

---

## 5. Q5 — D1: movements, institutions, guilds, cities today

- **Movements** (`agent_movements.py`, `movements.rs`, default on for new worlds):
  - target civ index; founded from the needs census;
  - members lapse at 0.10/turn outside the target realm unless travelling, so **members do not cross
    borders**;
  - news packets reach adjacent regions at half intensity and travel on bonds
    (`agent-movements.md:537-588`).
  Costs:
  - a commons grant: treasury `8 + 40 × strength` (`keep`, sunk);
  - poor relief upkeep `ceil(0.75 × realm regions)` per turn (`agent_movements.py:183,1166-1172`), sunk
    and unpaid for 3 turns → lapse;
  - liberty: −3 stability;
  - secession splits military and economy (`guard`) and treasury by region share (a real split).
- **Reforms: label versus real.**
  - The **label** part is `REFORM_NEED_CREDIT`: Rust reads a covered agent's need as
    `need + 0.3(1−need)` for grievance only, and the needs themselves are untouched.
  - Real parts:
    - home rule: charter +1 → dues share, self-government, Written Law institution;
    - toleration: abolishes an active Inquisition (a decision change);
    - guild charter: dues ×0.75, monopoly, no levy;
    - poor relief: Commons Management institution (action weights, soil recovery).
  - **Poor relief buys no food.** Its upkeep is a sink and its relief is the credit plus a one-off
    relief. Movements roadmap item 3 ("reforms that change the needs themselves") is open
    (`agent-movements.md:1094-1096`).
  - The reform table is rebuilt in Python every tick (`agent_movements.py:1867-1892`), so a switch can
    withhold the label credit without native changes.
- **Institutions** (`institutions.py`, a standalone kernel; `governance_runtime.py` wires it, default
  on): funded per civ from the treasury; aggregate coverage below 1 erodes them. No cross-border reach.
- **Guilds** (`guilds.py`, default on):
  - one per city;
  - take 5% (monopoly 10%) of city commerce from the civic purse into their own (2% decay);
  - pay for walls when the purse is short;
  - threats: levy, charter loss, sack, occupation, repeal;
  - guild movements per city; burgher faction.
  - **No leagues**, and a guild movement stays in its city's realm (`guilds.md:558-572`).
- **Cities**:
  - dues to the lord (next Phase 2, `keep`), from commerce;
  - charters, unrest, free cities (a new civ through the transfer helper);
  - `city.grievance` is the shared local channel.
  - The city institution history viewer covers cities only (`city-institution-history.md`).

Cross-border transfers that exist: diaspora remittances by stable id through native
`wealth_transfer::remit`, purpose 4 (`remittances.py:1-60`; `wealth_transfer.rs:55-63`), and treaty
tribute. There is no institutional cross-border body.

---

## 6. Q6 — D3: armies, casualty authority, identity, home and location

**Who decides casualties.**
1. The campaign layer: battles (`fight`), attrition (`logistics_step`, including siege disease), revolts,
   generals (`kill_general` → queue). Victims are chosen with `war_rng(ctx, "casualty", army_id, cause)`
   = `stable_hash_int("war", ...)`, so no global stream (`armies.py:315-339`).
2. Native natural mortality, which doubles the rate for **every Soldier-occupation agent of a civ at
   war** (`demographics.rs:175-183`, `tick.rs:2028-2032`, `WAR_CASUALTY_MULTIPLIER = 2.0` at
   `agent.rs:165`), whether or not they are on a roster.
3. Civilian war deaths, as anonymous regional catastrophe counts (`armies.py:300-314` →
   `catastrophe_deaths_this_turn` → `demographics.rs:177`).

**How deaths reach agents (exactly once).** Phase 5b removes the victims from the roster at once and
queues `queue_targeted_deaths(sorted ids)`. The native tick of the **same turn** collects them with the
catastrophe deaths (`demographics.rs:515-516` dedups against catastrophe victims). Python's region drain
is a same-turn view; the post-tick write-back sets native counts (`agent_bridge.py:3059-3066`). Then
`reconcile_rosters` drops anyone dead after the tick and **adds them to `army.casualties`**
(`armies.py:393-425`). Each person dies once **[inferred]**, but the cause is conflated.

**Identity across roster rebuilds and checkpoints.**
- Exact checkpoints restore the pool, and `_rebind_markers` re-binds `_war_roster_sim`
  (`run_checkpoint.py:421-432, 646-652`), so rosters keep their ids. A test exists per
  `checkpoint-continuation.md:449-457`.
- Non-exact resumes (legacy state, fork): `rebind_rosters` keeps an army's roster **if every id is live
  in the new pool** (`armies.py:450`), otherwise it redrafts the same head count. New pools allocate ids
  from 1 (`pool.rs:296`). A kept roster can therefore bind strangers (another civ, region or occupation),
  and their battle deaths kill those strangers. RS3 documents this ("stale ids that now name strangers",
  `veteran-reintegration.md:161-170`) and guards only itself.

**Home versus physical location versus campaign attachment.**

| Concept | Where | Notes |
| --- | --- | --- |
| Physical native location | `pool.regions[slot]` | soldiers **never move natively** (`campaigns-battles-occupation.md`, Known gaps) |
| Birth or homeland | `pool.origin_regions[slot]` | used by bond formation and migration drivers |
| Merchant home (transient) | `pool.trip_home_region` | reset each turn |
| Campaign attachment | Python `Army.roster` `(id, region)` | region refreshed from the snapshot, i.e. the native home |
| Army location | Python `Army.region`, `Army.home_region` (staging) | campaign state only |

**What soldiers count in while away.**

| System | Enlisted counted? | Evidence |
| --- | --- | --- |
| Home farm labour (native `farmer_count`) | **yes**: levies keep occupation Farmer at home | `ffi/mod.rs:3553-3564` |
| Retail title | **yes**: `title_inputs` has no enlisted filter | `household_retail.py:575-598` |
| Home food demand | **yes** (alive in the home region) | — |
| Army rations | separate and minted | `war/logistics.py:86-94` |
| Health care (patients and caregivers) | **no**: enlisted excluded | `health_care.py:102-113`, `household_retail.py:557-569` |
| Workshop, learning, recovery and timber crews | **no** | `workshops.py:203-205`, `recovery_crews.py:240-247`, `timber_supply.py:317-371`, `simulation.py:2316` |
| Fertility, bonds, movements | **yes**: no native enlisted flag exists (pool field list `pool.rs:84-224`) | [inferred] |

**Can combat injury reuse the health-care episode store?** Yes, without editing pinned files:
- `InjuryEpisode(agent_id, onset_turn, remaining, origin_region)` (`health_care_state.py:10-14`) carries
  no cause.
- `finish_health_care` advances every episode generically (`health_care.py:142-163`), but it indexes
  `assignments[episode.agent_id]` built at prepare. An episode inserted between prepare (Phase 2) and
  finish (post-tick) would **KeyError**.
- So a D3 module would append combat episodes **after** finish, i.e. in a livelihoods `phase10` hook
  (`livelihoods.py:711`, after `simulation.py:2377`), to take effect from the next prepare. It
  would keep the combat cause in its own ledger keyed by (agent_id, onset_turn).
- An agent with an occupational episode already open needs a merge rule (max remaining), or the native
  side would see a duplicate id.
- Effects: a wounded levy released home loses farm work and draws spouse care through the existing
  authority. A wounded Soldier-occupation agent gets natural recovery only. No new mortality authority.
- Any change to the episode schema or summary labels touches the digest-pinned `health_care*.py`.

---

## 7. Q7 — Design proposals

Common rules for all of these:
- default off;
- registered in `feature_catalog.REQUIREMENTS`;
- hybrid only, with other modes refused at startup and resume;
- system-specific `stable_hash_int` namespaces only;
- every new persisted field excluded while default, so feature-off JSON and pickles are byte-identical;
- feature-off identity checked against `8abc1acb` and the preceding main;
- `refactor_preflight.py --git-diff origin/main` before each PR.

### 7.1 A5: exactly-once war lifecycle of owned stock (S2, first)

- **Switch:** retail **rules version 2** (`HouseholdRetailState.rules_version`, default 2 for new
  states). A saved v1 state keeps v1, and `--household-retail-rules 1` reproduces checkpoint-2/3
  behaviour byte for byte (precedent: `apprenticeship.py:151,271-314`). A rules change on resume is
  refused. The CLI key in `batch_manifest.SIMULATION_ARG_KEYS` touches pinned `batch_manifest.py` and
  needs a lead-owned inverse layer. If that is deferred, v2 can ship as the new-state default without the
  CLI, and reproduction of v1 from an old checkout.
- **State:** per pilot region, `war_events` (a monotone counter). `RetailRecord` gains optional `cause`,
  `actor` (civ index), `actor_name`, `victim` and `victim_name` (excluded if None, so v1 logs keep their
  bytes). Counters are appended: `war_loss_conquest_milli`, `war_loss_siege_milli`,
  `war_loss_occupation_milli`, `war_events`.
- **Hooks (Python only):**
  - `on_conquest(world, region, attacker, defender)` from `action_engine.py:638-642`;
  - `on_war_loss(world, region, factor, cause, actor)` from `war/occupation.py:_requisition`, with
    optional kwargs passed by `start_occupation` (`:67`) and `siege_turn` (`battles.py:402`).
  Each applies at once with `_debit(..., "war_loss", ...)` and `_check`. In v2, `_apply_conquests`
  becomes an assertion (`last_conquered_turn` newer than the last hook-applied turn → raise "conquest
  not observed").
- **Boundary decisions to make explicit:**
  - a region without a controller still confiscates every claim to the commons (keep, document as an
    intentional boundary, or decide otherwise, §11);
  - the timber store is untouched by war (record as a boundary or defer to B/A4);
  - rounding: owned takes `v − floor(v·f)`, so it can lose at most 1 milli per good per event more than
    the float commons.
- **RNG:** none (pro rata, largest remainder).
- **Checkpoint:** events land in Phase 5/5b inside the turn's books, and checkpoints are at turn
  boundaries. Exact resume inside an occupation or siege must match a straight run (new
  `checkpoint_identity` case, or a native CLI test with a constructed war).
- **Pins at risk:** none enforced for `household_retail*.py`, `action_engine.py` and `war/*.py`
  (preflight). `batch_manifest.py` only if the CLI key is added. Test path pins: add a **new** test
  module and a **new** oracle chunk in `scripts/run_python_oracle_checks.py` (the household-retail chunk
  already holds three modules), and register native tests in `scripts/testing/native_shards_manifest.json`.
- **Risk:** low (Python, default off, no native).

### 7.2 D4: requisition as transfer, restitution, reconstruction (S4)

- **Switch:** `--war-requisition` (modes `transfer` and `cost_only`; requires campaigns, hybrid,
  optionally retail).
- **Requisition:** at the same two events, the taken food (commons and owned, same factor) goes into the
  army's rations up to carried capacity, using a declared food→ration constant. The rest is destroyed
  and recorded. The army's minted refill that turn is reduced by the requisitioned rations (no
  stacking). Each event is recorded once: actor (civ index, army_id, war_key, start), victims (commons
  region; owners by id with milli amounts), destination (rations or destroyed).
- **Restitution:**
  - at a treaty that returns the region, or on liberation, the paid reparation (`peace.py:259-261`) is
    split, up to a share, to the recorded owner-victims by id, pro rata to the recorded requisition
    value;
  - this needs a native transfer purpose (`restitution`, appended to `wealth_transfer.rs:55`); a native
    change, but small;
  - otherwise there is no money, only a record.
- **Reconstruction:** RS2 already exists for buildings. Program B owns infrastructure condition. D4 does
  not invent repairs.
- **Placement:** Python (`war/logistics.py`, `war/occupation.py`, `war/peace.py`, `household_retail.py`),
  plus one native purpose append.
- **RNG:** none. **Pins:** none for the war files. Native extension identity changes with the purpose.
- **Risk:** medium (default-path code under a switch, army balance shifts).

### 7.3 D2: attribution fixes (S4, mostly record-only)

1. Retail records carry actor and victim at the event (in A5).
2. Granary `SEIZED` flows record the actor (the occupier or conqueror) in a new optional field. This
   touches pinned `grain_reserves.py`, so it needs an inverse layer or should be deferred.
3. Separate natural deaths from campaign casualties in a D3 ledger (avoid `models.Army`, pinned through
   `models.py`).
4. Declare restored-civ identity reuse.
5. Rosters on non-exact resume: under the D3 switch, **always redraft** (or refuse the resume) when the
   pool marker is unset. Default path unchanged and documented.
6. Saved L2 outside hybrid refused (RL3).
7. Never read provenance in decisions; add a test that greps decision modules for `provenance.keys`
   reads.

No new grievance channel. Where a recorded quantity is better than a proxy, replace the proxy behind a
switch (for example, diplomacy occupation grievance from recorded requisitions instead of 1.5 per turn).

### 7.4 D1: bounded cross-border organization (S5)

- **(a) Poor relief as a real service**, `--reform-services`. Python only and lowest risk:
  - `reform_table` omits RELIEF rows (no native credit);
  - RELIEF upkeep buys food that reaches people through an existing channel: owners' surplus through
    the retail procurement seam (paid by id, purpose 6) into the commons free pool, or a granary
    purchase and release under `--grain-reserves`;
  - grievance then responds through real needs;
  - depends on A1/A4 accounting.
- **(b) Guild leagues across borders**, `--guild-leagues`:
  - guilds of cities in different realms, linked by recorded merchant flows (native trip receipts or
    trade routes), form a league (ids never reused);
  - members pay capped dues from their purses into a league fund (a real purse transfer);
  - the fund pays a member's levy share, wall help or post-sack purse restoration only on that
    **member's recorded** levy, sack or occupation (city history tuples);
  - grievances stay in `city.grievance`;
  - RNG namespace `("guild_leagues", ...)`; Python only (`guilds.py`, `cities.py`, unpinned).
- **(c) Movement branches abroad:**
  - members abroad already exist briefly (they lapse at 0.10);
  - a branch needs native lapse or recruitment changes (`movements.rs`) and a transfer purpose;
  - **high risk, late**; record-only first (count members abroad from the snapshot `movement_id`).

### 7.5 D3: war's human consequences (S5, late)

- **(a) Record-only ledger** (low risk): per enlisted person, home region, army attachment and army
  location; separated spouse and children at home (from `get_agent_relationships`); release and return
  with cause; natural deaths versus campaign casualties.
- **(b) Wounded instead of killed**, `--combat-injury`, requires `--health-care` and campaigns:
  - a declared share of campaign casualties is drawn as wounded (`war_rng(ctx, "wounded", army_id,
    cause)`);
  - the wounded are released alive (RS3 cause `wounded`, appended) and get a health-care episode
    appended in Phase 10 (§6);
  - this changes casualty outputs under the switch only. The casualty authority still decides who is
    hit, and there is no new death path.
  - Optional: a rules flag that turns off the native soldier-at-war ×2 multiplier while the switch is
    on, so campaign casualties are the single authority. That is **native**.
- **(c) Labour away for enlisted levies:**
  - remove levies' farm work from the home economy as PL1 does with `woodcut_labor_away`;
  - stop titling it in retail;
  - pair it with D4 (soldiers eat requisitioned or home food instead of minted rations) so food demand
    is not double counted.
  - Needs a generic native labour-away column (`economy.rs` and `ffi/mod.rs`, both pinned) →
    **high risk**.
- **(d) Evacuation and family separation with real effects** (owners carrying claims, civilians fleeing
  sieges): native migration interplay → **high risk, last**.

| Proposal | Python / Rust | Pinned files | Risk | Slice |
| --- | --- | --- | --- | --- |
| A5 v2 war hooks | Python | `batch_manifest.py` only for the CLI key | low | S2 |
| RL3 saved-L2 refusal | Python | none | low | S1/S2 |
| D2 records | Python | `grain_reserves.py` (optional) | low | S4 |
| D4 requisition transfer | Python | none | medium | S4 |
| D4 restitution money | + Rust purpose | extension identity | medium | S4 |
| D1a reform services | Python | none | medium | S5 |
| D1b guild leagues | Python | none | medium | S5 |
| D1c branches | Rust | `movements.rs` (unpinned) | **high** | S5 late |
| D3a ledger | Python | none | low | S5 |
| D3b combat injury | Python (+ optional Rust) | none if episodes appended in Phase 10; `health_care*.py` if the schema changes | medium-high | S5 |
| D3c labour away | Rust | `economy.rs`, `ffi/mod.rs` | **high** | S5 late |
| D3d evacuation | Rust | `tick.rs`, `pool.rs` | **high** | last |

---

## 8. Q8 — Smallest first A5 slice and test plan

**Slice A5-1 "war reaches owned stock once per event"** (Python only, retail rules v2):
1. `household_retail_state.py`: `rules_version` (exclude while 1 for old states), the optional record
   fields, the counters.
2. `household_retail.py`: `on_conquest` and `on_war_loss`; in v2, `_apply_conquests` becomes an
   assertion; `requisition_exempt_region_turns` counts only in v1.
3. `action_engine.py:638-642`: one call next to RS2's `region_conquered`.
4. `war/occupation.py:36` (`_requisition(..., *, cause=None, actor=None)`), `:67`, and
   `war/battles.py:402`.
5. `livelihoods.py`: the rules choice, prerequisites, resume-conflict entry, and the saved-L2 refusal
   (RL3).
6. Docs: `household-retail.md` lifecycles, the connected-world board RL1-RL3 dispositions, the
   continuation ledger.

**Offline tests** (new `tests/test_household_retail_war.py` on the existing `Harness`,
`test_household_retail.py:351-480`, new oracle chunk):
- a. **Two conquests in one turn** (`between=` two `apply_region_conquest` calls with different
  attackers): owned per good equals the share applied twice, matching commons ×0.25; two records naming
  each attacker and defender; `war_events == 2`; `check_region` and `check_owner` hold.
- b. **Duplicate processing:** one conquest seen at Phase 2 and before the tick applies once; the next
  turn shows no `war_loss`; the v2 assertion fires if `last_conquered_turn` advances without the hook.
- c. **v1 reproduction:** with rules 1, every existing conquest test passes unchanged (note string, once
  per turn).
- d. **Siege and occupation:** `_requisition(region, 0.85, world, cause="siege", actor=...)` takes
  `v − floor(0.85v)` pro rata; two sieges in one turn take it twice; occupation start 0.8; a region with
  no claims is a no-op; the commons and owned shares come from the same event.
- e. **Death and war the same turn:** loss before settlement; heirs inherit the reduced claim;
  conservation holds.
- f. **Conquest then loss of controller the same turn:** war loss once, then `pilot_closed` once at the
  next Phase 2.
- g. **Feature-off and `record_only`:** hooks are no-ops (state absent or untouched, no RNG draw); an
  absent livelihoods container is a no-op.
- h. **Serialization:** a v1 state's JSON and model_dump are byte-identical to `8abc1acb`; a v2 state
  round-trips JSON and pickle (backfill); a rules change on resume is refused.
- i. **RL3:** saved L2 with agent mode off → refused with the `--no-food-allocation` hint.

**Native and integration tests** (shard manifest, `CHRONICLER_REQUIRE_RETAIL_NATIVE=1`):
- j. A CLI legacy resume with hybrid: frames settle every resumed turn, `pool_resets == 1`, and all
  claims go to the commons on the first resumed turn. This reproduces this audit's seed-7 observation.
- k. An exact resume inside a live siege or occupation of a pilot region (constructed with
  `tests/war_fixtures.py`, or a development world found to activate naturally) is byte-identical to the
  straight run.
- l. `CHRONICLER_CHECK_RESOURCES=1` with campaigns, retail boundary `all`, procedural development
  seed(s): no conservation failure.

**Identity:** feature-off `turn_speed_identity` (9 cases) against `8abc1acb` and the preceding main.
All-switch `checkpoint_identity` (`hybrid_s42_long`, `proc32_hybrid_s11`) with retail v2. Count how
often a pilot region is besieged or occupied on development worlds first; if never, say so and rely on
the constructed test.

**Screens (later):** a primary outcome of owned war loss by cause, and a harm panel (priced-out persons,
escheat), on a fresh reserved cohort. A v1 versus v2 arm is the identity control except where war
touches pilot regions.

---

## 9. Dependencies on other programs

- **A1 (accounting):** restitution payments and requisition-to-rations become new wealth and food
  sources or sinks and must enter A1's reconciliation. RL4 (storage-cap timing) bounds how much owned
  stock exists between close and opening when war takes a share.
- **A4 (merchants and owned cargo):** A5's hook API (`on_conquest`, `on_war_loss`, by event, with actor
  and victim) should be the one cargo ledgers use. Grain convoys are the capture-versus-loss precedent.
  Title transfer to merchants needs a new flow kind beside `sold` and `procured`.
- **B (infrastructure):** RS2 war damage and repair is the reconstruction authority. B's condition and
  service capacity must not double-damage on conquest (RS2 is once per asset per turn; conquest and
  scorched earth are separate).
- **C (health):** combat injury reuses health-care episodes and care capacity (C2). Health care must not
  become a mortality authority.
- **E:** viewer causes, actors and victims for war loss; distinguish recorded zero from absent; exact
  resume at war transitions; seed registry for war-heavy screens; the stale `agent_mode` default-path
  issue (RL3).
- **Lead (shared contracts):** turn-order rows for the hooks (Phase 5/5b; D3 episode append in Phase 10
  after `finish_health_care`); the `batch_manifest` inverse layer; native purpose appends; the
  roster-redraft rule.

---

## 10. Pins (preflight, read only)

Files with current enforced pins or digests relevant here (from `audit-d/preflight-summary.txt`):

| File | Pin |
| --- | --- |
| `grain_reserves.py` | `livelihoods_pl4_source_inverse.json` |
| `batch_manifest.py` | pl4 |
| `models.py` | l0 |
| `simulation.py` | rv2 |
| `main.py` | r3 |
| `agent_bridge.py` | rv1 |
| `run_checkpoint.py` | s2r |
| `pool.rs`, `tick.rs`, `economy.rs`, `ffi/mod.rs` | pl4 |
| `merchant.rs` | crisis_candidate |
| `household.rs` | household_candidate |
| `health_care.py`, `health_care_state.py`, `health_care.rs` | digest pins in `tests/test_health_care_policy.py:1017-1027` |

No enforced pins: `household_retail.py`, `household_retail_state.py`, `action_engine.py`,
`war/*.py` (all nine), `repair_projects.py`, `veteran_reintegration.py`, `agent_movements.py`,
`guilds.py`, `cities.py`, `diplomacy.py`, `livelihoods.py`, `politics.py`, `timber_supply.py`,
`remittances.py`, `grain_convoys.py`, `provenance.py`, `feature_catalog.py`, `factions.py`,
`governance_runtime.py`, `local_budgets.py`, `utils.py`, `movements.rs`, `demographics.rs`,
`provisioning.rs`, `wealth_transfer.rs`, `knowledge.rs`, `memory.rs`, `migration_drivers.rs`,
`relocation.rs`, `persist.rs`. Test modules `tests/test_household_retail.py` (shard 0, oracle chunk) pin
their **path**, not their content.

---

## 11. Open questions for the lead or owner

1. Owned stock destruction: follow the commons **per event** (recommended) or RS2's once per asset per
   turn? Should RS2 be aligned later?
2. Treaty cessions and consolidated annexations go through `apply_region_conquest`, so they destroy 50%
   of commons and owned stock even after siege and occupation losses. Keep, or mark as a D4 rules
   question?
3. A pilot region losing its controller confiscates living owners' claims to the commons. Is that an
   intentional boundary, or should claims survive without a market?
4. Is a retail rules-version CLI key (pinned `batch_manifest.py` inverse layer) wanted now, or v2 as the
   new-state default only?
5. Combat injury: are wounded released home or kept attached and recovering? Does the native
   soldier-at-war ×2 mortality stay as a second authority under D3?
6. Soldiers' food: accept the home-demand plus minted-ration double count as a documented boundary until
   D4, or block D3c until D4 lands?
7. Non-exact resume with live rosters: redraft always (an output change on labelled non-exact runs) or
   refuse explicitly?
8. The stale `world.agent_mode` after an agents-off legacy resume of a hybrid save (default path): fix
   behind a rules version, refuse, or document?

## 12. Unverified items

- That every person dies at most once through the targeted-plus-catastrophe dedup across all paths (read
  `demographics.rs:515-516`; the dedup body was not read).
- Natural activation of sieges or occupations of pilot regions on development worlds (not run).
- Fertility, bonding and movement recruitment of enlisted agents at home (inferred from the absence of
  any native enlisted flag).
- Name uniqueness of `Free <region>` civs (`transfer_regions_to_new_civ`).
- That RL1 cannot happen under campaigns (inferred from the code paths listed in §1.3; not exhaustively
  tested).
- That a stale roster binding strangers on a legacy resume actually happens at runtime (code path and
  RS3 doc agree; not reproduced; the seed-7 runs had no armies at turn 6).
