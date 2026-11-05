# L8: commons rules with enforceable costs (2026-11-05)

Sprint 2 lane L8 ([plan](../superpowers/roadmaps/livelihoods-commons-sprint2.md)), on top of
the L3 timber stock ([timber-stock.md](timber-stock.md)). `--commons-rules` (default off;
requires `--timber-stock`) lets the controller of a region adopt one explicit rule on a
harvested timber slot: a **harvest quota with a rest period**, enforced by wardens it pays for.
The rule changes the actual harvest permission (the native `timber_harvest_cap_{slot}`), and
unpaid enforcement shrinks the share of the stand it covers. `--commons-rule-mode cost_only` is
the cost-retaining control: everything is adopted, paid and recorded identically, but no cap is
lowered.

Code: `src/chronicler/commons_rules.py`, `src/chronicler/commons_rules_state.py`, and two
functions added to `src/chronicler/timber_stock.py` (section 6). Viewer:
`viewer/src/lib/commonsRules.ts`, `viewer/src/components/systems/CommonsRules.tsx` (not
mounted). Tests: `tests/test_commons_rules.py` (offline), `tests/test_commons_rules_native.py`
(real extension), `viewer/src/lib/__tests__/commonsRules.test.ts`,
`viewer/src/components/systems/__tests__/CommonsRules.test.tsx`.

Nothing here claims that a commons rule is better than open access. The rule can protect a
stand while costing its region harvest, wares and money, and the evidence (section 10) shows
both sides.

## 1. Actor and stake

The actor is the region's **controller**, the civilization at index `owner` in
`world.civilizations`. Its near-term stakes in the harvest already exist in the model:

- the region's city crafts turn raw materials into wares;
- wares raise the city's commerce, and commerce pays the lord's dues (`cities.py`);
- workshops (L1, when enabled) need timber as an input;
- it pays the wardens from its own treasury.

The rule also feeds the existing **Commons Management** institution (governance runtime).
Before L8 that institution's only material effect was a soil bonus. Now its funded enforcement
also staffs the timber wardens (section 3).

## 2. Knowledge, adoption and the rule

**Knowledge is local and dated.** Every decision reads only the timber account settled in the
previous turn's Phase 2, `StockObservation(turn, stock, capacity, extraction,
water_gate_open)`. It never reads the current opening stock, cover lost since then or a future
yield. A rule without a fresh account keeps its last one; receipts show the observation's turn.

**Adoption.** Adoption happens in Phase 2, before the native economy tick, in (region, slot)
order. The controller adopts a rule on a timber slot when all of these hold:

- the slot has no rule and is not in a repeal cooldown;
- the observation shows a harvest (`extraction > 0`), so somebody's livelihood is at stake;
- the stand is depleted: stock below `ADOPT_BELOW` (0.5) of the cover-implied capacity;
- the projected treasury can pay the first turn's wardens in full.

**Rule.** The stand **rests** (quota 0) while the observed stock is below `REST_BELOW` (0.25) of
capacity, until it is back at `REOPEN_AT` (0.4) (hysteresis). Otherwise the **quota** is
`QUOTA_SHARE` (1.0) times the stand's logistic regrowth at the observed stock, taken at most at
the stock of maximum growth `K (1 - a) / 2`: harvest no more than the stand grows. The quota is
zero while the observed water gate is closed.

## 3. Enforcement, money and coverage

- **Bill.** A rule needs `ADMIN_COST` (2) coins of wardens per turn.
- **Commons Management.** A controller holding a Commons Management institution enacted before
  this turn supplies the share `legitimacy x this turn's institution funding ratio` of the
  wardens from the enforcement governance already paid in Phase 2. With governance off, or no
  such institution, the share is 0.
- **Treasury.** The treasury is billed `ceil((1 - share) x ADMIN_COST)` whole coins.
- **Planning.** The bill is planned before the native tick against the projected treasury
  (`mutual_aid._treasury_budget`, which replays queued `keep` changes). It first leaves room for
  every other pending Phase 2 bill, `pending_phase2_bills(world)`: grain storage's pending plan
  (its upper bound) and the workshops' funded bills. Existing rules are funded before new
  adoptions.
- **Charge.** The bill is charged **once** after the native tick succeeded, as a disclosed
  public cost (accumulator `keep`, never a wage or a private payment). Settlement runs after
  storage and workshops have charged, and re-checks the treasury; a shortfall raises instead of
  recording an unpaid payment. A failed tick charges nothing (`rollback_phase2`).
- **Coverage.** A short treasury pays what it can, and `coverage = min(1, share + paid /
  ADMIN_COST)`.
- **Limit.** The limit offered to the economy is the float32 floor of `coverage x quota + (1 -
  coverage) x stock_cap`. The covered share of the stand is held to the quota; **the uncovered
  share is open access** up to the standing stock (the L3 cap). A limit below the stock cap is
  `applied`.

## 4. Repeal, lapse and ownership change

A rule is **repealed** (decisions log; cooldown of `COOLDOWN_TURNS` (12) on the slot) when:

- `recovered`: the observed stock is at `REPEAL_AT` (0.8) of capacity;
- `unfunded`: there were `UNFUNDED_LIMIT` (3) consecutive turns with zero coverage;
- `idle`: nobody could harvest for `IDLE_LIMIT` (12) consecutive turns (no farmers in the region
  or no timber yield: the timber stock's `possible` flag);
- `unrest`: the region's carrier city reached the revolt threshold (`cities.REVOLT_UNREST`,
  0.6) after the rule had added grievance there. The lord concedes.

A rule **lapses** (no cooldown) when:

- `owner_changed`: the region's controller differs from the owner. This includes conquest,
  secession and loss of control. The rule belonged to the old controller. The new controller
  inherits no bill, no arrears and no rule. It decides afresh from its own dated observation and
  treasury. Because a resting stand records no harvest, it adopts only after open access has
  shown one.
- `slot_removed`: the slot is no longer timber.

`--no-commons-rules` freezes the rules (no caps, no bills, no record); re-enabling resumes them.

## 5. Conflict: one existing channel, capped

When an **enforced** rule binds, the region's largest open city (rank, size, then lowest
settlement id) gains `RULE_GRIEVANCE` (0.02) of grievance. "Binds" means the harvest reached an
applied limit; a zero limit binds where farmers and a timber yield could have harvested. This
channel never raises the city's grievance above `GRIEVANCE_CEILING` (0.25).

City grievance is the existing carrier of local conflict. It decays at 0.96 a turn and enters
the city's unrest target. Unrest, revolts, concessions and free cities then follow the existing
mechanism in `cities.py`. Nothing else is touched (stability, factions, movements, action
weights). Hunger keeps its own city channel (`HUNGER_UNREST`), so a hungry region is not
counted twice.

A cost_only rule never binds, so it adds no grievance. A protected region without a city
records `city: null` and adds nothing.

## 6. Phase hooks and the timber stock interface

`commons_rules` is the last of the livelihoods switches, so its hooks run after the timber
stock's and the workshops'.

- **`prepare_phase2`**
  - Reads `timber_stock.offered_caps(world)`: this turn's stock caps and whether a harvest was
    possible. It requires the timber stock's prepare to have run.
  - Reads the dated ledger and plans every decision, bill and limit.
  - In enforced mode, calls `timber_stock.tighten_harvest_caps(world, region_input, limits)`.
- **`tighten_harvest_caps`** (new, in `timber_stock.py`)
  - Lowers a column value to the float32 floor of `min(value, limit)`; a null value under the
    L3 ablation becomes the limit.
  - Never raises a cap and validates the slot and the limit.
  - Changes no state. The stock's own ledger still records and checks the stock cap it offered.
- **No commits at prepare.** Nothing persisted changes until finish.
- **`finish_phase2`**
  - Validates first: the payer is still the civ, the treasury covers the bill, and the
    extraction is at most every applied limit. An extension that ignores the column raises.
  - Then commits: charges, rule updates, city grievance and the receipts.
- **`rollback_phase2`** drops the plan.

The transient plan is never serialized: it is excluded from pickles and JSON.

## 7. Observation

`snapshot.livelihoods.commons_rules`, only while active:

- **Header:** `schema_version` 1, `units` (`timber_goods`, `treasury`), `mode`, `source_turn`,
  `completed_turn` (= snapshot turn = source + 1), `parameters`, `observed`.
- **`receipts`:** one per rule in force this turn:
  - identity and decision state: owner, `new`, status, the dated `observation`;
  - rule and money: `quota`, `stock_cap`, `required`, `institution_share`, `bill`, `paid`,
    `coverage`, `limit`, `applied`, `possible`;
  - outcome: `extraction`, `binding` (enforced; null in cost_only), `excess` (cost_only: harvest
    above the limit the rule would have applied);
  - conflict: `city`, `grievance_added`;
  - displacement and welfare observations: `neighbour_slots`, `neighbour_open_extraction`,
    `raw_imports`, `craft_output`, `farmer_income_modifier`, `food_sufficiency`.
- **`decisions`:** this turn's adoptions, repeals and lapses.
- **`rules`:** the rules in force after the turn.
- **`counters`:** the cumulative funnel.

When no Phase 2 was settled in the source turn, `observed` is false and receipts and decisions
are null (unknown, not empty).

The viewer reader `commonsRulesAt(snapshot, regionCount)` returns null for any record that is:

- absent, from a foreign schema or misdated;
- an observation not older than its turn;
- inconsistent in its money: coverage, bill or payment;
- a rest with a nonzero quota;
- a limit above the stock cap, or an `applied` flag that does not match the limit;
- enforced extraction above an applied limit;
- a cost-only record with binding or grievance;
- grievance without a city;
- a duplicate row.

It accepted all 600 snapshots (466 receipts) of three of the runs in section 10 (seed 1
enforced, seed 3 cost_only, seed 3 workshops + enforced), rerun on `ddd8b111` with their
bundles kept.

## 8. Displacement

The roadmap asks whether extraction shifts to neighbouring unprotected stands. In this economy
it cannot shift through production.

- A slot's harvest is its farmers' labour split (food first, then equal shares) times the
  yield. It does not respond to prices or demand
  ([timber-stock.md](timber-stock.md) section 8).
- A lowered cap wastes the protected slot's timber labour. That labour is not reallocated, and
  no neighbour's labour moves.

What can move:

- **Trade.** Raw materials can come in from other regions; receipts record the protected
  region's `raw_imports`.
- **Migration.** Over longer horizons people can move, which changes labour everywhere. Only
  paired runs can show this.

Receipts record the extraction of every adjacent timber slot outside an applied rule
(`neighbour_open_extraction`). The offline test `test_neighbouring_open_extraction_is_observed_not_shifted`
constructs an adjacency and shows the neighbour's harvest stays its own labour's output, with
and without the rule. In the template worlds no protected region has a neighbouring timber slot
(0 in every receipt), so the development cohort cannot show displacement at all (section 10).

## 9. Clearing: assessment and proposal (not built)

The sprint-1 screens found that cover loss from clearing, cooling, wildfire and succession
removes about 9-14 times the timber harvest. A rule acting only on extraction therefore has
little leverage.

**What the cohort shows** (the three kept runs of section 10). While a rule is in force, the
stand is already well below its capacity: cover loss had earlier cut it to capacity, and since
then cover has regrown faster than the stock. So cover lost during rule turns cleared little
standing timber:

| Run | Timber cleared during rule turns | Extraction during rule turns | Rule slot-turns with population above half capacity (clearing active) |
| --- | --- | --- | --- |
| Seed 1 enforced | 3.1 | 1.9 | 0 of 96 |
| Seed 3 cost_only | 2.0 | 12.4 | 66 of 124 |
| Seed 3 workshops + enforced | 34.4 | 7.8 | 17 of 246 |

The column of clearing turns is approximate: snapshot population against final carrying
capacity. Clearing does its damage before a rule exists, and it caps the regrowth the rule
waits for.

**Feasibility.** A land-use clause would suspend population-driven clearing in a protected
region at an explicit cost. Population clearing is computed in two runtimes:

- Python `ecology._tick_forest`;
- native `ecology.rs::tick_forest_controlled`, called at line 1088 and in the parity harness at
  lines 1175-1181.

The native ecology state is rebuilt from Python each turn (`set_region_state`). A Python-only
moratorium would have to undo the native clearing after the tick, for example in Phase 10. By
then the soil cross-effect, the deforestation cascade, succession and the ecology counters have
already read the uncorrected cover. That would break ecology's single authority, so it is
rejected. A faithful clause needs Python and native changes with parity. Per the lane
instruction it was **not built**. Proposal:

1. `RegionState` (ecology.rs) gains `clearing_suspended: bool`, read from an optional Boolean
   region-batch column `clearing_suspended`. The column is absent by default; absent means
   false.
2. `tick_forest_controlled` skips `forest_cover -= forest_clearing` when the flag is set.
   Cooling and wildfire are untouched. Python `_tick_forest` reads the same flag through one
   helper (`commons_rules.clearing_suspended(world, rid)`).
3. Lead-owned hunks:
   - `agent_bridge.build_region_batch` appends the column only when commons rules are active;
   - the ecology FFI parses it;
   - parity and identity tests run with the flag absent and present.
4. **Cost.** Clearing has no modelled benefit in this economy: cover lost to clearing does not
   become farmland or yield. A moratorium would be a free gain unless its cost is declared.
   Candidates: a larger warden bill per suspended clearing turn, or an explicit food-yield
   penalty on the pressured region. Without one of these the clause should not be built.
5. **Evidence.** The same funnel, plus cover and capacity retained in protected regions against
   cost_only.

## 10. Evidence (development cohort only)

**Setup.**

- Linux container, Python 3.13, `PYTHONHASHSEED=0`, `RAYON_NUM_THREADS=1`.
- Native venv `~/.venvs/chronicler-native`, used read-only. Extension SHA-256 `3cb5b1f9...a483d4aa`,
  built by the lead from the base's native source. This lane changes no Rust.
- Source: commit `3cc18d2b`. Later commits change only docs and viewer files. A first run on
  `ddd8b111` gave the same metrics in all 18 rows.
- Template seeds 1-3, 200 turns, `--agents hybrid --simulate-only`.
- Arms, all with `--timber-stock`:
  - `timber`: open access;
  - `enforced` (`--commons-rules`);
  - `cost_only` (adds `--commons-rule-mode cost_only`);
  - each again with `--workshops` (`ws_*`).
- 18 runs, 0 failed, 69 s wall, 2 at a time.

Driver, per-run metrics and source identity:
[commons-rules-evidence/](commons-rules-evidence/) (`driver.py`, `metrics.jsonl`,
`source.txt`). The held cohorts 301-306 and 401-406 were not run.

**Funnel (enforced arms).** Seed 2's only stand (Mistwood) has no people in 200 turns. It is
eligible on every observed turn, but it never shows a harvest, so no rule is adopted. All three
seed-2 arms are identical: null activation.

| Stage | Seed 1 | Seed 3 | Seed 1 + workshops | Seed 3 + workshops |
| --- | --- | --- | --- | --- |
| Eligible slot-turns (dated, controlled) | 199 | 398 | 199 | 398 |
| Adoption opportunities (harvested, below half capacity) | 3 | 3 | 2 | 2 |
| Rules adopted (none unaffordable) | 3 | 3 | 2 | 2 |
| Rule slot-turns (rest / quota) | 96 (96 / 0) | 138 (138 / 0) | 35 (35 / 0) | 246 (219 / 27) |
| Wardens paid / required (coins) | 176 / 192 | 276 / 276 | 57 / 70 | 492 / 492 |
| Coverage turns full / partial / zero | 87 / 2 / 7 | 138 / 0 / 0 | 28 / 1 / 6 | 246 / 0 / 0 |
| Commons Management share | 0 | 0 | 0 | 0 |
| Turns the cap was lowered | 87 | 51 | 29 | 230 |
| Turns the harvest reached the limit | 67 | 39 | 16 | 204 |
| Harvest under the rule | 1.86 | 0 | 0.45 | 7.76 |
| Withheld, measured in cost_only (excess over the limit) | 63.3 | 12.4 | 1.5 | 22.9 |
| City grievance added (turns) | 0.39 (23) | 0.64 (39) | 0 | 0.71 (54) |
| Repeals | unfunded 2, idle 1 | idle 2 | unfunded 1, idle 1 | recovered 1 |

Notes on the funnel:

- **Rest dominates.** Rules mostly rest because the stock lags its cover-driven capacity (L3
  section 6).
- **Unfunded repeals.** Seed 1's owner (one region) ran its treasury down twice.
- **Commons Management.** No protected stand's owner held the institution. Its share is shown
  only by `test_commons_management_supplies_wardens`.

**Conservation and its costs (enforced against cost_only, same world).** Cost_only pays the
same bills, so the difference isolates the cap. The trajectories are identical until the first
binding turn and diverge afterwards; these are total model effects of one world each, not
estimates.

| World | Total extraction | Mean stock | Closing stock | Regrowth | City wares (protected regions) | Workshop output | Population, treasury at 199 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Seed 3 | 284.0 vs 295.9 (-4%) | 570.5 vs 569.2 | 8.9 vs 9.0 | 339.9 vs 333.8 | 34.9 vs 39.1 (-11%) | — | 163 vs 167; 2484 vs 2360 |
| Seed 3 + workshops | 284.0 vs 299.2 (-5%) | 617.1 vs 564.0 (+9%) | 680 vs 591 (+15%) | 857 vs 656 (+31%) | 29.7 vs 39.8 (-25%) | 167.2 vs 177.8 (-6%) | 167 vs 178; 1902 vs 2136 |
| Seed 1 | 62.3 vs 119.2 | 204.6 vs 191.3 | 325 vs 205 | 344 vs 280 | 16.9 vs 17.2 | — | 104 vs 133; 2113 vs 1394 |
| Seed 1 + workshops | 53.5 vs 55.1 (-3%) | 224.0 vs 223.5 | 388 vs 387 | 399 vs 398 | 0 vs 0 | 126.7 vs 126.7 | 108 vs 108; 2130 vs 2129 |

What each row shows:

- **Withheld harvest.** The cost_only excess agrees with the paired extraction difference where
  the worlds stay close: seed 3 12.4 against 11.9; seed 1 with workshops 1.5 against 1.6. Seed
  3 with workshops: 22.9 against 15.2.
- **Seed 1 diverges.** Its population and treasury paths separate within a few dozen turns of
  the first binding; its extraction difference is not attributable to the rule.
- **Where the rule conserved.** Only in seed 3 with workshops did the stock gain materially.
  Mistwood was protected until its recovery repeal at turn 161, and Thornwood's mean stock rose.
- **What it cost.** The protected regions lost wares (-11% and -25% of city crafts in seed 3)
  and workshop output (-6%). The owners paid 57-492 coins per world.
- **Little leverage.** Without workshops, seed 3's stock gain is negligible (+0.2% mean): cover
  loss (4,431 cleared against 296 extracted) dominates, as the screens predicted.

Welfare observations over rule turns (protected region, means; different turn sets per arm, so
descriptive only):

| World | Farmer income modifier | Food sufficiency | Raw-material imports into the protected region |
| --- | --- | --- | --- |
| Seed 3 | 1.092 vs 1.134 | 1.235 vs 1.245 | 2.54 vs 0.00 |
| Seed 3 + workshops | 1.677 vs 1.582 | 0.835 vs 0.885 | 0.32 vs 1.35 |
| Seed 1 | 1.979 vs 2.066 | 0.445 vs 0.457 | 0.79 vs 0.68 |

- **Displacement.** There was no neighbouring timber slot anywhere (0 in every receipt). The
  raw-material imports show no consistent shift.
- **City conflict.** No city reached the revolt threshold, so no rule was repealed for unrest.

## 11. Checks run

- `tests/test_commons_rules.py`: 33 passed (offline, under 1 s).
- `tests/test_commons_rules_native.py`: 3 passed, on the native venv above, about 5 s.
  `tests/test_timber_stock_native.py` still passes (3).
- Related suites: 109 passed (`test_timber_stock.py`, `test_livelihoods_wiring.py`,
  `test_batch_manifest.py`, `test_workshops.py`, `test_food_allocation.py`,
  `test_grain_convoys.py`).
- The five source-scanning tests that walk `src/` pass with the new modules.
- **Bounded offline lane.** The lane itself cannot pass until the lead's witness layer lands
  (section 12), because its witness chunks come first and it stops at the first failing chunk.
  Instead, every node the lane selects, plus `tests/test_commons_rules.py`, was run in one
  no-native pytest process without the lane's guard. Result: 6,034 passed, 69 skipped, 0
  failed, 184 s. The seven expected witness rejections were deselected. This ran on `ddd8b111`
  plus the test module; the later commit changes only `commons_rules.py` and its tests.
- **Feature-off identity.** `scripts/turn_speed_identity.py` cases `hybrid_s42`, `hybrid_s7`
  and `off_s42` were run on the sprint base (`0cc62442`, `src` extracted with `git archive`) and
  on this branch (`3cc18d2b`), each through `--source-root` on the same extension: 231 files, 0
  differences.
- **Enabled exact resume** on `3cc18d2b`: PASS with 0 differences.
  - Command: `scripts/checkpoint_identity.py run OUT --case hybrid_s42 --ks
    10,30,52,53,54,55,56,58,59 --jobs 2 --cli-arg=--seed=1 --cli-arg=--timber-stock
    --cli-arg=--commons-rules`.
  - Seed 1, 60 turns: plain against checkpointing, then nine resume points.
  - A rule is adopted at turn 53 and rests, paid and binding, through turn 59, so seven resume
    points fall inside a live rule.
- Viewer:
  - the two new test files: 8 passed;
  - the full suite: 118 files, 1,226 tests;
  - `npm run lint` and `npm run build` pass;
  - real records accepted (section 7).

Not run: the 200-seed gate, held or procedural cohorts, shadow and demographics-only modes, a
browser journey (the panel is not mounted), PR CI, other platforms.

## 12. Open items

**Lead patches (witness-pinned or shared files):**

- **Witness layer.** `src/chronicler/batch_manifest.py` and `tests/test_batch_manifest.py` are
  pinned by `livelihoods_l0_source_inverse.json` and older chains. Their hunks (two keys added
  to `SIMULATION_ARG_KEYS` and to the omit-when-None tuple, and its mirror in the test) need a
  reviewed exact-inverse layer. Until then seven witness tests reject them:
  - `test_livelihoods_sprint_witness` (2);
  - the academy, crisis, household and information candidate witnesses (1 each);
  - `test_public_grain_shipments::test_composition_inverse_is_literal_complete_and_refuses_unrelated_edits`.
- **Test enrollment.** `tests/test_commons_rules.py` and `tests/test_commons_rules_native.py`
  go in `native_shards_manifest.json`, the `additions` map in `tests/test_native_ci_shards.py`
  and an offline `CHUNKS` slot (the offline module takes under a second).
- **Viewer.** Mount `CommonsRules`, and add the record type to `viewer/src/types.ts` if wanted.
- **Screens.** Fold the arms into `scripts/livelihoods_screens.py` for the held screens; the
  interaction listed in the plan is commons × workshop timber demand.

**Model limits:**

- **Clearing.** The clearing clause (section 9) needs Python and native ecology changes and a
  declared cost.
- **Quota rarely matters.** Rules almost always rest. The quota binds rarely because template
  timber harvests are small (L3 section 6). The rule's leverage comes from rest periods during
  cover regrowth.
- **Commons Management.** The institution did not occur in a protected region of the
  development cohort.
- **Displacement.** It needs procedural worlds, which have adjacent timber regions, and a labour
  or demand channel that does not exist yet.
