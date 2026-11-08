# Core-Loop Depth — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** DEP-1, DEP-2, DEP-3, DEP-4, DEP-5
> **Depends on:** DEC-1 (pin policy, PIN-1) or reviewed inverse layers; CON-1 (switch registry) preferred; COR-6 (war casualty booking) before DEP-2 evaluation
> **Feeds:** DEP-8 (feature profiles), DEP-9 (validation hygiene)
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md; scout 28 (primary), 05, 08, 09, 12, 13, 15, 29

## 1. Goal and scope

Five default-off switches that give the aggregate loop more distinguishable outcomes. All are experimental: no default promotion is proposed here. With every switch off, output must stay byte-identical.

- DEP-1 `stat_saturation`: diminishing returns on positive gains to culture, economy and asabiya.
- DEP-2 `military_stock`: a muster/attrition stock so military 0 means "unmustered", not "permanently spent".
- DEP-3 `famine_episodes`: named famine episodes with a recorded peak.
- DEP-4 `named_event_balance`: a significance gate on `propaganda_campaign`.
- DEP-5 `regional_inequality`: a new snapshot metric for aggregate runs.

Not changed: action-weight caps (`K_WEIGHT_CAP`, grudge, M63b ceilings), accumulator categories, enum order, the Rust runtimes, agent-mode populations. No new CLI flag is removed. No simulation is run by this spec; section 6 designs the evaluation.

## 2. Current behaviour (verified)

- **Stats are int 0-100.** `StatAccumulator.apply` clamps to `[STAT_FLOOR, 100]` (`accumulator.py:145-159`); `UNBOUNDED_STATS` has `asabiya` (`accumulator.py:42`) but civ asabiya is a derived mean of region values (`simulation.py:819-836`). `acc.add` stores the raw delta (`accumulator.py:93-101`).
- **Culture/economy gains** come from DEVELOP (+10 to the lower of the two, cost `5 + economy//10`, `action_engine.py:160-183`), discovery +10/+10 (`simulation.py:1036-1040`), renaissance +20 (`:1054-1057`), cultural work +5 (`:1650-1653`), exile +3 (`succession.py:271-273`), exploration (`exploration.py:197`), leaders +10 (`leaders.py:410`). Production code always runs with an accumulator (`simulation.py:1951`); `acc=None` branches are legacy/test callers.
- **Hybrid mode:** `apply_keep` skips every non-`keep` change (`accumulator.py:164-187`, `simulation.py:2342`), and the bridge overwrites military, economy, culture from Rust aggregates (`agent_bridge.py:3137-3139`). So DEP-1 (culture/economy) and DEP-2 act only where Python owns the stat (agents off, shadow).
- **Asabiya** per region follows `s += 0.05 f s(1-s) - 0.02 (1-f) s` (`simulation.py:799-801`). The fixed point is below 1 for most frontier fractions; pinning at 1.0 comes from additive terms: folk-hero bonus `*0.1` every turn with no dependence on `s` (`:803-808`), and one-off boosts through `_apply_asabiya_to_regions` (`:753-759`; callers `leaders.py:345`, `politics.py:657`, `politics.py:1409`, `simulation.py:1655`, `emergence.py:585`).
- **Military has almost no positive source** in aggregate mode: era bonus (`tech.py:42-47`), leader event +10 (`leaders.py:333`), mercenary hire (`simulation.py:501`), restoration (`politics.py:1255`). Drains: expansion (`action_engine.py:235`), war losses (`:859-902`), war-camp losses (`war/common.py:226-235`), collapse halving (`simulation.py:1476-1486`). Maintenance only costs treasury above 30 (`simulation.py:314-321`). Scout 28's 39-68% zero share is therefore a one-way ratchet, not noise. WAR weight x2.5 needs military >= 70 (`action_engine.py:1387`); EXPAND needs >= 30 (`:213`). Campaign musters read `civ.military` (`war/armies.py:42-51`) and `CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS = True` (`war/params.py:32`).
- **Famine:** aggregate trigger when region food yield < `K_FAMINE_YIELD_THRESHOLD` (0.12) outside a 5-turn cooldown (`ecology.py:296-322, 358`); emits `famine` or `dearth` Events (`:384-395`). **Audit claim wrong:** episodes already exist. The provenance layer folds famine strikes into `ChronicEpisode` (onset, last_turn, count) and emits `famine_ended` (`provenance.py:835, 868-926`; `models.py:787-798`). What is missing is a peak/severity record and any NamedEvent; no famine NamedEvent site exists (grep of `NamedEvent(` sites).
- **Named events:** `propaganda_campaign` is appended on every successful INVEST_CULTURE with fixed name "Propaganda in {region}" (`culture.py:410-418`). **Finding:** `generate_propaganda_name` (`named_events.py:147`) has no callers.
- **Gini:** **audit location wrong.** `agent_bridge.py:1406, 1460` fill a wealth-stats dict. The snapshot value is `CivSnapshot.gini` (`models.py:1387`, a snapshot model never persisted to state.json), set at `main.py:980` from `agent_bridge._gini_by_civ` else 0.0. `validation_regression.py:453` averages snapshot `gini` for runs lacking agent aggregates, so writing aggregate values into `gini` would shift existing gate statistics.

## 3. Design

Common shell: one optional world field `core_depth: CoreDepthState | None = Field(default=None, exclude_if=_is_none)` on `WorldState` (pattern: `models.py:1225`), holding five booleans and a params dict. Logic lives in a new unpinned module `src/chronicler/core_depth.py` with `*_enabled(world)` readers. Switches: `--stat-saturation`, `--military-stock`, `--famine-episodes`, `--named-event-balance`, `--regional-inequality` (`BooleanOptionalAction`, default None, pattern `main.py:2270`, `_configure_run` `main.py:1624-1627`), plus `batch_manifest` `SIMULATION_ARG_KEYS`, `run_checkpoint`, `live.py` pass-through and a `FEATURE_GROUPS["Core depth"]` entry (`feature_catalog.py:85`). `--military-stock` refuses unless `agent_mode` is off/None/shadow (same refusal pattern as `expansion_features.py:101`).

No new RNG anywhere: every rule below is deterministic arithmetic on world state.

**DEP-1.** Let `K=60`, `C=100`, `p=1`. Gain factor for int stats: `g(s)=1` for `s<=K`, else `((C-s)/(C-K))^p`. For a positive net delta `d` on culture or economy, `eff=int(d*g(s))`, never above `C-s`. Negative deltas are untouched, so shocks keep their size. Applied in `StatAccumulator.apply` (which has `world`), so no `acc.add` signature change; shock normalisation still uses the raw `stat_at_time` delta (documented mismatch, small). `d=10` at 90 gives 2; `d=3` stalls above about 87: a soft ceiling that depends on the source, which is intended. Asabiya: `g_a(s)=min(1,(1-s)/(1-0.6))` applied to the folk-hero term and to `_apply_asabiya_to_regions` deltas. Optional upkeep arm: `upkeep` integer points per turn above 90, category `guard` (skipped in hybrid, correct because Python does not own the stat there), default 0. Tuning keys: `depth.saturation.knee`, `.power`, `.asabiya_knee`, `.upkeep`.

**DEP-2.** Per living civ with regions, once per turn after maintenance (`simulation.py:313-321`): `target = T_peace + T_war*[at war] + 0.1*floor(pop/10)` clamped 0-100 with `T_peace=15`, `T_war=45`; `at war` reads `world.war_state` (campaigns) or the active-war relationship. Muster `m = min(ceil(0.25*(target-M)), treasury//c)` with `c=1` treasury per point, positive only; attrition `a = floor(0.1*(M-target))` when `M>target`. Both go through `acc.add(..., "military", d, "keep")` (applies in all modes; wars already book `guard-action`). Zero then means broke and below target. Keys: `depth.military.{peace,war,pop_term,rate,cost,decay}`. Defeat/collapse halving and war losses are unchanged, so COR-6 must land first for a clean comparison.

**DEP-3.** Extend `ChronicEpisode` with `peak: float | None = Field(None, exclude_if=_is_none)` (written only when the switch is on). On each famine/dearth report `peak = max(peak, depth)` (aggregate: `1 - yield/threshold`; agent modes: the famine hunger component). At episode close (`provenance.py:_close_episodes`, `:900-926`) a `famine` episode with `duration >= 3` or `count >= 2` appends `NamedEvent(event_type="famine_episode", name="The {Adjective} Famine of {region}", importance 6 + (peak>0.5))`, using `named_events._seed_rng` with extra `"famine:"+region+onset`. Provenance never feeds the simulation, so this changes narration and analytics only. The trigger-rate audit is an evaluation, not code: sweep `K_FAMINE_YIELD_THRESHOLD` over {0.08, 0.10, 0.12} in tuning files (section 6); no threshold change ships in this task.

**DEP-4.** `named_event_gate(world, event_type, key)` in `named_events.py`. For `propaganda_campaign`: emit the NamedEvent only if `foreign_control_turns` crossed a multiple of 5 in this action, or no campaign by this civ on this region in the last 10 turns (`history_index`); the `invest_culture` Event still fires every time. When it emits, name it with `generate_propaganda_name` (deduplicated). Table-driven: other types get entries only if the section 6 entropy check shows a new dominant type. Keys `depth.named.propaganda_stride`, `.propaganda_window`.

**DEP-5.** `regional_inequality` is a new `CivSnapshot.regional_inequality: float | None = Field(None, exclude_if=_is_none)`; `gini` is left alone. Computed in `core_depth.py` from existing world data at snapshot time: population-weighted Gini of per-head food yield across a civ's regions (`aggregate_food_yield * aggregate_farm_productivity`, `ecology.py:105`; `economy.aggregate_farm_productivity`), None for a one-region civ. Read-only, no state. The name states it is a regional food measure, not wealth. Viewer: optional field in `viewer/src/types.ts`, shown only when present. Analytics: `extract_gini_trajectory` (`analytics.py:1799`) gains a sibling series; `validation_regression` is not changed.

## 4. Compatibility
Old bundles and checkpoints load unchanged (all new fields exclude-when-None/false). Pre-existing saves without `core_depth` run exactly as before. New fields are optional in the viewer; the viewer feature-catalog fixture (`viewer/src/__fixtures__/featureCatalog.json`, `tests/test_feature_catalog.py:756`) is regenerated additively, and `test_existing_catalog_output_is_byte_identical` (`tests/test_feature_matrix.py:96`) must pass untouched. No flags removed.

## 5. Pins and preflight
- Enforced: `simulation.py` (11 witnesses; DEP-1 asabiya wrap, DEP-2 turn hook), `models.py` (5; one field + two snapshot/episode fields), `main.py` (9), `batch_manifest.py` (31), `ecology.py` (2; not edited here).
- Unpinned: `accumulator.py`, `action_engine.py`, `culture.py`, `provenance.py`, `named_events.py`, `feature_catalog.py`, `war/armies.py`, new `core_depth.py`.
- Plan: depend on PIN-1; fallback is one reviewed exact-inverse layer per enforced file via `scripts/testing/reviewed_main_witness.py`. Keep enforced-file edits to one-line hooks. Never rewrite a hash.

## 6. Classification and evaluation
New default-off features, not corrections: baseline proof is `scripts/turn_speed_identity.py` off-mode byte identity. Any later default promotion is a correction needing the gate below.

Common design: aggregate (`--agents off`) 150 turns, 5 civs and 14 regions as scout 28; procedural 32x10 at 300 turns for DEP-1/3/4/5; hybrid 200 turns for DEP-1 asabiya, 3, 4, 5 only. Seeds: reserve new blocks above the registry maximum (4206, `scripts/seed_registry.json`) after re-checking it: development template 5001-5020, pilot 5021-5036, held template 5101-5148, held procedural 5201-5224; never 42-241/1000-1999 except for the final gate; append entries and run via `scripts/screen_runner.py` (pilot before held). Arms: off, each switch alone, all on.

| Item | Primary ("better") | Guards |
|---|---|---|
| DEP-1 | civ-turns at culture 100: 73-84% to <=30%; economy 100: <=15%; asabiya >=0.99: <=10% | survival, collapse count, action-share L1 shift <=0.10, `max_precap_weight` unchanged |
| DEP-2 | civ-turns with military 0: 39-68% to <=15%; P(mil>0 given at war) >=0.9; war share of actions from 0.6-1.5% toward 2-6% | war share <=10%, treasury floor, no extra extinction |
| DEP-3 | 3-12 named famines per 150 turns; every closed episode with duration >=3 named | starts/turn reported by terrain; threshold sweep as audit table only |
| DEP-4 | top named-type share <=25% (from 34-42%); normalised Shannon entropy up; no type below floor of 1.5 named events/10 turns total | importance distribution |
| DEP-5 | metric non-None for >=95% of multi-region civ-turns; Spearman with hybrid wealth gini on matched seeds reported | no change to `gini` |

Promotion gate: `scripts/m53b_run_validation.py --profile full` (template 200 seeds x 500 turns) and the procedural full profile (100 x 300, `docs/DEVELOPMENT.md:204-205`) with before/after baselines, plus CONTINUATION entry and its own PR. DEP-2 is aggregate-only, so its gate arm must run agents off; the standard gate profile's agent mode is unverified here. Passing bounded checks does not authorise promotion.

## 7. Tests
`tests/test_core_depth.py` (new): off-mode identity, per-rule arithmetic, clearing of nothing transient (no signals added), hybrid no-op for DEP-1 culture and DEP-2 refusal. Changed: `tests/test_feature_catalog.py`, `tests/test_batch_manifest*.py` key lists, viewer type test. Add to an oracle chunk with headroom, not a new limit.

## 8. Risks
Saturation changes tech-era and action thresholds' meaning (culture >= 60 gates INVEST_CULTURE; economy <= 30 boosts DEVELOP). Military stock may spawn war spam: guard cap 10%. Shock-normalisation mismatch under DEP-1. Open: asabiya knee 0.6 unverified against the 20-31% pinned share cause; the folk-hero term is the suspected driver. Rollback: leave switches off; delete the module.

## 9. Size
About 450 lines source, 400 lines tests, 60 lines docs/viewer; 5 PRs.
