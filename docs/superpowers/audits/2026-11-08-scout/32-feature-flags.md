## 32 Feature flags and switch combinatorics
**Map**
- Livelihood switch modules are `chronicler.<switch>` (`livelihoods_state.py` docstring; `_module(name)`).
- CLI: `main._build_parser` (`main.py:2052-2350`, 167 parser actions: 68 BooleanOptionalAction, 8 store_true, 48 choice-valued). Default-on/off systems are wired in `main._configure_run` (`main.py:1576-1660`) and, for live worlds, `live._live_world` (`live.py:1290-1440`).
- Livelihoods registry: `livelihoods_state.LIVELIHOODS_SWITCHES` (36 switches), `livelihoods.LIVELIHOODS_ARG_KEYS` (75 keys incl. 39 mode keys), `LIVELIHOODS_CHOICES` (`livelihoods.py:132`), `add_livelihoods_arguments` (`livelihoods.py:~596`), `configure_livelihoods` (`livelihoods.py:961`), `_check_prerequisites` (`livelihoods.py:707`).
- Expansion switches: `expansion_features.py` (EXPANSION_FEATURES, 6 incl. scientific_research_agendas; `configure_expansion_features` at line 82; quarantine via `quarantine_rules`).
- Served catalog: `feature_catalog.py` (REQUIREMENTS line ~150-210, `validate_features`, `lobby_feature_catalog`): 84 entries = 42 boolean + 42 choice keys (123 values). Viewer: `viewer/src/lib/featureCatalog.ts` (generic reader, no hard-coded flags), `FeatureOptions.tsx` (renders the served catalog).
- Batch: `batch_manifest.SIMULATION_ARG_KEYS` (133 keys; covers all 84 experimental destinations, verified) plus a hand-kept exclusion tuple (`batch_manifest.py:~269`).
- New-world defaults: 17 `DEFAULT_ENABLED_FOR_NEW_WORLDS = True` (plus `CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS`, `war/params.py:32`) and 9 default-off modules (`community_anchoring`, `domestic_credit`, `grain_reserves`, `harvest_forecasts`, `health_care`, `refugee_routing`, `ritual_gatherings`, `scholarship`, `scientific_claims`).

**Flag table** (catalog = served by `feature_catalog`; tests = test files naming the flag, from grep; "unverified" = not read; default-on rows are off in the table's "off" sense only when `--no-` is passed)

| Flag | Module | Modes | Default | Requires / conflicts | Tests | Documented result (progress docs) | Viewer catalog |
|---|---|---|---|---|---|---|---|
| workshops | workshops.py | operate/observe/cost_only | off | hybrid; cities | 49 | positive-narrow (+5-12% crafts, input-bound) | Y |
| food_allocation | food_allocation.py | floor_means/equal/targeted_relief | off | hybrid | 31 | mixed: floor_means worse 12/12; targeted_relief reverses | Y |
| timber_stock | timber_stock.py | - | off | econ agents | 28 | mixed (cap binds 10/12; cover loss dominates) | Y |
| grain_convoys | grain_convoys.py | adaptive/cheapest/safest | off | public_grain_shipments | 19 | null (63 dispatches, almost no risk outcomes) | Y |
| commons_rules | commons_rules.py | enforced/cost_only | off | timber_stock | 17 | positive-narrow (extraction cut 5/6); clearing still 10-20x harvest | Y |
| learning_cohorts | learning_cohorts.py | learn/no_learning | off | hybrid, academy_services | 16 | null-ish (completions rare) | Y |
| workshop_payroll | workshop_payroll.py | paid/unpaid_labor/no_customer | off | hybrid, workshops operate | 25 | positive for crew (template worlds) | Y |
| relocation_costs | relocation_costs.py | paid/assisted/liquidity_only | off | hybrid; no mobility requirement | 18 | positive-narrow (assistance cuts blocked fares 11/12) | Y |
| local_budgets | local_budgets.py | bargained/fixed_shares | off | hybrid, grain_reserves | 28 | adverse (workshop output down 12/12; relief ~null) | Y |
| apprenticeship (RS1) | apprenticeship.py | train/no_qualification; rules 2/1 | off | hybrid, workshops operate | 33 | adverse-leaning (lump repairs, forgone income) | Y |
| repair_projects (RS2) | repair_projects.py | repair/cost_only | off | hybrid + workshops or grain_storage | 32 | unverified (result not extracted) | Y |
| veteran_reintegration (RS3) | veteran_reintegration.py | priority/record_only | off | hybrid + workshops/apprenticeship/repair | 19 | unverified | Y |
| remittances (RS4) | remittances.py | send/record_only | off | hybrid | 23 | unverified | Y |
| clearing_protection (RS5) | clearing_protection.py | enforced/cost_only | off | none | 20 | unverified | Y |
| operating_wear (PL2) | operating_wear.py | - | off | hybrid, workshops operate | 18 | assumption-by-design (+14.7 t lump repairs); covered share null | Y |
| timber_supply (PL1) | timber_supply.py | supply/cost_only | off | hybrid, repair, timber_stock | 24 | positive (granary +0.051 t/+0.094 p; no food cost) | Y |
| recovery_crews (PL3) | recovery_crews.py | paid/unpaid | off | hybrid, repair_projects | 28 | mixed (wages +132 t; workshop -0.35 t) | Y |
| maintenance_obligation (PL3) | maintenance_obligation.py | reserve/reserve_only | off | local_budgets, repair_projects | 20 | positive-narrow (granary +0.03; workshop null) | Y |
| household_retail (PL4) | household_retail.py | retail/no_relief/free_exchange/record_only; boundary; rules | off | hybrid, food_allocation | 42 | adverse (priced-out +452 t/+339 p person-turns) | Y |
| watershed (B1) | watershed.py | record_only/flow | off | procedural world (>12 regions) | 23 | mixed (CW3) | Y |
| workshop_economics (A3) | workshop_economics.py | market/free_inputs/academy_only | off | workshop_payroll | 22 | unverified (CW2 not read) | Y |
| titled_trade (A4) | titled_trade.py | - | off | household_retail retail, rules 2 | 18 | positive-narrow (procedural shortfall lower 5/6) | Y |
| infrastructure_condition (B3) | infrastructure_condition.py | repair/record_only/wear_only/cost_only | off | hybrid; repair needs repair_projects | 16 | unverified alone; CW6 combined adverse | Y |
| harvest_cover | harvest_cover.py | loss/record_only | off | hybrid, timber_stock | 11 | unverified | Y |
| epidemic_care (C2) | epidemic_care.py | care/cost_only | off | hybrid, local_budgets, epidemiology; excludes wealth_accounting | 24 | positive-narrow (deaths lower 6/6 template; procedural mixed) | Y |
| guild_leagues (D1b) | guild_leagues.py | mutual/dues_only | off | hybrid, cities, guilds | 13 | mixed (league results mixed; relief sparse) | Y |
| war_requisition | war_requisition.py | transfer/cost_only | off | hybrid, campaigns, household_retail rules 2 | 18 | unverified alone; CW6 combined adverse | Y |
| war_consequences | war_consequences.py | active/record_only | off | hybrid, war_requisition, health_care, residence_ledger | 18 | unverified | Y |
| adaptive_livelihoods | adaptive_livelihoods.py | adapt/record_only/shuffled; rules; decision channels | off | hybrid, residence_ledger | 22 | unverified; CW6 combined adverse | Y |
| public_health (C1) | public_health.py | active/cost_only; crowding; policy; report delay | off | hybrid, epidemic_care, infrastructure_condition, residence_ledger, quarantine | 22 | null (CW4 quarantine primaries null) | Y |
| quarantine_mode / _channels | quarantine_rules.py | legacy/closure/cost_only; trade | legacy | epidemiology or legacy; closure | 18 / 15 | null (CW4); channels unverified | Y |
| movement_branches | movement_branches.py | funded/record_only/cost_only | off | hybrid, agent_movements | 15 | unverified | Y |
| reform_services (D1a) | reform_services.py | service/cost_only | off | hybrid, household_retail retail, agent_movements | 11 | unverified | Y |
| timber_orders | timber_orders.py | - | off | hybrid, timber_supply, local_budgets | 14 | unverified | Y |
| residence_ledger (X1) | residence_ledger.py | - | off | hybrid | 27 | observation-only | Y |
| attribution_records (D2) | attribution_records.py | - | off | hybrid | 17 | observation-only | Y |
| wealth_accounting (A1) | wealth_accounting.py | observe/strict | off | hybrid; excludes epidemic_care | 39 | observation-only | Y |
| grain_reserves | grain_reserves.py | - | off | econ agents | 64 | positive gate (PASS, no regression); outcome not extracted | Y (prereq) |
| public_grain_shipments | (prereq) | - | off | grain_reserves, econ | 28 | unverified | Y (prereq) |
| grain_storage | (prereq) | policy neglect/maintain/expand | off | hybrid, grain_reserves | 37 | unverified | Y (prereq) |
| scholarship | scholarship.py | - | off | none | 62 | none | Y (prereq) |
| academy_services | (prereq) | - | off | hybrid, scholarship, techniques | 14 | none | Y (prereq) |
| health_care | health_care.py | - | off | hybrid | 39 | mixed (lower death rate vs cost-only; procedural raw deaths +2.8) | Y (prereq; docs say N) |
| harvest_forecasts | harvest_forecasts.py | - | off | grain_reserves, contact_ledger, econ | 14 | none extracted | N |
| ritual_gatherings | ritual_gatherings.py | - | off | hybrid | 9 | none extracted | N |
| scientific_claims | scientific_claims.py | - | off | scholarship, techniques | 25 | none extracted | N |
| scientific_research_agendas | scientific_research.py | - | off | scientific_claims | 17 | none (no ledger entry) | N |
| transaction_receipts | transaction_receipts.py | - | off | econ agents | 28 | none extracted | N |
| community_anchoring | community_anchoring.py | - | off | agent pool | 10 | ledger mixed; not extracted | N |
| domestic_credit | domestic_credit.py | - | off | finance, agent pool | 8 | ledger mixed; not extracted | N |
| capacity_aware_refugees | refugee_routing.py | - | off | none | 6 | none extracted | N |
| campaigns, cities, techniques, epidemiology (+contact_ledger), finance, diplomacy, maritime, gp_agendas, nomads, guilds, agent_movements, historiography, languages, fisheries, mutual_aid, governance (17 default-on) | respective modules | - | ON (new worlds) | - | 10-83 each | promoted on subset/no-regression gates; no held outcome verdict | N (cities, techniques, epidemiology, agent_movements, guilds appear as read-only settings) |

Counts: 84 served entries; 42 boolean and 42 choice keys with 123 values; 25 non-catalog booleans (17 default-on, 8 off).

**Findings**

1. **Live new worlds do not get the governance default.** CLI new worlds get governance on (`main.py:1650-1652`, `governance_runtime.py:87`), but that branch needs `fresh_world`. A lobby world is supplied, so `fresh_world` is False, and `live._live_world` (`live.py:1290-1440`) never sets governance. Probe: `live._live_world` with `--live --agents hybrid` gives `world.governance = None`. Tests cover only the CLI path (`test_governance_runtime.py:495`). [high bug] Action: apply the same default in `_live_world`, recorded as a deliberate correction (it changes live outcomes).

2. **Mode flags without their switch are silently accepted and dropped.** `--workshop-mode cost_only` (and `--repair-mode`, `--commons-rule-mode` and others) pass `configure_expansion_features` on a fresh world with no workshops; `configure_livelihoods` (`livelihoods.py:967-971`, `980`) skips the setter. Some modules refuse their own orphan mode (`livelihoods.py:~855`, infrastructure_condition, harvest_cover, epidemic_care); most do not. Argparse has no dependency checks at all. The served catalog refuses these (`feature_catalog` parent requirement), so the gap is CLI only. [med bug] Action: one generic orphan-mode check driven by the catalog's `parent`/`requires`.

3. **Resume can silently change a saved mode.** On a saved world with workshops in `operate`, `--workshops --workshop-mode cost_only` was accepted and the saved mode became `cost_only` (probe; `workshops.py:122-132` assigns `state.mode`). `_check_prerequisites` compares saved values for only six keys (`livelihoods.py:713-722`). [med bug, resume] Action: compare saved values for every `_CHOICE_FIELDS` key (line 993) before any setter runs. The probe ran `configure_expansion_features`; the full `execute_run` resume path was not probed (unverified).

4. **Test gaps.** Every experimental dest is named by at least 6 test files, so none is wholly untested. The thin ones: `capacity_aware_refugees` (6), `adaptive_livelihoods_rules` (6), `ritual_gatherings` (9), `community_anchoring` (10), `gp_agendas` (10). The only combinatorial test is the all-enabled matrix (`test_feature_matrix.py`); no test covers orphan modes or resume-mode conflicts (finding 2 and 3). Individual mode values are not tested by name (unverified).

5. **Drift between catalog, viewer and docs.**
   - `docs/integration/feature-options.md:260` says health care is not in the catalog. It is served (group `Prerequisites`, `feature_catalog.py` PREREQUISITES). The doc's prerequisite list (~line 40) also omits it.
   - Line 93 says "No exclusion is declared yet". `epidemic_care` and `wealth_accounting` declare one. The same paragraph says older viewers refuse a `not` kind and suggests bumping `CATALOG_SCHEMA_VERSION`; it is still 1 (`feature_catalog.py:62`), and the viewer accepts only schema 1 (`featureCatalog.ts:191`). So an older viewer shows its malformed-catalog notice for any catalog with a `not` kind; the version number is the only signal, and it did not change.
   - Lines 106 and 110 say "25 switches, 300 pairs" (2026-11-06). The registry now has 36 livelihoods switches and 42 boolean entries.
   - The viewer fixture matches the served catalog exactly (84 keys, settings and surfaces equal). `batch_manifest` covers all 84 experimental destinations.
   - Two encodings of a delay: `--harvest-report-delay` is an int 0-12, `--public-health-report-delay` is a 21-value string choice list (`livelihoods.py:~150`).

6. **Combinatorial explosion.** 42 served booleans give 2^42 (about 4.4e12) raw subsets, and 67 booleans across all surfaces give about 1.5e20, each times 4 agent modes and 2 world kinds. The documented matrix (`scripts/feature_matrix.py`) enumerates pairs only: C(42,2) = 861 pairs, times 8 contexts. Ablation controls are production modes: 11 keys have `cost_only`, 9 `record_only`, 2 `shuffled`. A `--preset` already exists but only sets tuning (`tuning.py:461`), so a new name is needed.

7. **Promotion and removal candidates.**
   - Promotion (narrow positive, held, 200-seed gate not run): `epidemic_care`, `timber_supply`, `workshop_payroll`, `commons_rules`, `relocation_costs`, `maintenance_obligation`, `titled_trade`. These are candidates for qualification, not default-on.
   - Adverse, keep as ablation evidence, not as defaults: `household_retail`, `local_budgets`, `apprenticeship`, `food_allocation` (floor_means regime).
   - Merge or hide: `scientific_research_agendas` (sub-switch of `scientific_claims`, no ledger evaluation) could become a mode. Its CLI flag, saved field and batch key make deletion breaking; hide with `argparse.SUPPRESS` instead.
   - Do not delete any CLI flag: batch manifests, `test_existing_catalog_output_is_byte_identical` and saved bundles pin them.

8. **Named profiles could replace most flags.** Add `--feature-profile NAME` (not `--preset`, which is tuning) that expands to a feature dict checked by the existing `feature_catalog.validate_features`. Candidate profiles: `classic` (all experimental off, the identity reference); `new-world` (the 17 default-on, what the CLI gives now); `agent-economy` (hybrid plus the positive-narrow livelihoods chain: timber_supply, commons_rules, workshop_payroll, maintenance_obligation, grain_reserves); `connected-full` (the documented adverse stress set, never a default); `controls` (cost_only/record_only arms). The batch config stores the profile name plus the expanded explicit features, so old manifests keep their shape.

**Simulation depth**
- Profiles over the existing registry would let grand runs compare explicit stacks (economy, health, governance) rather than tens of toggles, while keeping every expansion explicit in the manifest.
- The 17 default-on systems are the main unmodelled-choice surface: they change outcomes for every new world, yet only CLI/`--no-` flags control them. Exposing them as profile members would make grand runs reproducible.
- The adverse household_retail and local_budgets results point to missing mechanisms (affordability, relief targeting), not to flag tuning.

**Confidence** Verified by probe and grep: governance-on-live gap, orphan mode acceptance, resume mode overwrite, catalog/fixture/batch coverage, docs drift lines, counts. Documented results are from ledger and screen summaries; the per-flag verdicts marked "unverified" were not read. The `live` probe used `_live_world` directly, not the lobby server.

**Streamlining candidates**

| Candidate (path or symbol) | Action (delete / merge into X / extract / rewrite) | Lines saved (approx) | Breaks or blocks (tests, pins, CLI flags, saved-bundle compat) | Risk (low/med/high) |
|---|---|---|---|---|
| `live.py` `_live_world` lines ~1300-1440 (17 near-identical default blocks) | extract a table-driven loop of (module, setter, default) | ~110 | live parity tests; governance fix changes it anyway; batch/CLI order pinned by test_fisheries_mutual_aid_promotion | med |
| `feature_catalog.py` `_cities_default`, `_techniques_default`, `_guilds_default`, `_movements_default` (lines ~332-352) | merge into one `_default_for(module, name)` | ~15 | none (private) | low |
| `batch_manifest.py` exclusion tuple (~line 269) | derive from `LIVELIHOODS_ARG_KEYS` + `EXPANSION_SWITCHES` instead of hand-listing ~45 keys | ~45 | legacy manifest shape (keys omitted when unset) must stay; test-pinned | med |
| `livelihoods._CHOICE_FIELDS` vs `_check_prerequisites` six-key loop (livelihoods.py:707-722, 993) | merge into one generic saved-vs-requested and orphan-mode check | ~30 | resume refusals pinned by tests; error text changes | med |
| `public_health_report_delay` (21-string choice) vs `harvest_report_delay` (int) | rewrite as int 0-20 | ~1 line | CLI value type and catalog choices change; viewer fixture regen | med |
| `expansion_features.py` `scientific_research_agendas` | merge into `scientific_claims` as a mode or hide | ~20 | CLI flag, saved field, batch key, expansion_features tests | high |
| `docs/integration/feature-options.md` lines 40, 93, 106, 260 | rewrite (stale counts, health_care, exclusions) | 0 (docs) | none | low |
