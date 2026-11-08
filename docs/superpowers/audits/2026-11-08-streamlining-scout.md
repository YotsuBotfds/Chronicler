# Repository scout and streamlining plan (2026-11-08)

**Source audited:** `main` at `c3d752fa`. Branch `claude/relaxed-brown-4ozgeg` was identical when the audit ran.
**Method:** 32 read-only scouts, each assigned one area, followed by lead spot-checks of the high-severity claims. The per-area reports are in [`2026-11-08-scout/`](2026-11-08-scout/), and their shared brief is [`BRIEF.md`](2026-11-08-scout/BRIEF.md).
**Runtime change:** none. This file and the scout reports are documentation only.

**Ran:**
- `pytest --collect-only`: 11,972 tests, no collection errors
- `cargo check -j 2`: exit 0, zero warnings
- `tsc --noEmit -p tsconfig.app.json`: exit 0
- four aggregate 150-turn runs (seeds 42, 7, 1234, plus one ablation) and one cProfile run
- `scripts/refactor_preflight.py` over every tracked source, script and viewer file
- read-only GitHub Actions history (the last 60 runs)

**Not run:**
- the bounded oracle lane
- the native build and native tests
- vitest, eslint and the viewer build
- `scripts/turn_speed_identity.py`
- the 200-seed gate

Nothing here qualifies a gate.

Tags used below:
- **[V]**: the lead verified the claim in this session.
- **[S]**: a scout reported it; the lead did not re-check it.
- **[S-NN]**: points to the scout report with that number.

---

## 1. Bottom line

1. **Size and bloat.** The repo is not bloated everywhere: about 10% of the production package and a few clusters of scripts, docs and viewer code carry most of the dead weight.
   - **Totals:** about 154k lines of Python package, 75k Rust, 64k TypeScript, 187k tests, 47k scripts, and 40 MB of docs in 1,519 files.
   - **Unreachable modules:** 29 modules (13,880 lines, 9% of `src/chronicler`) are unreachable from the CLI, live, validate and narration-audit entry points [V, S-27].
   - **Dead code:** about 530 lines of unpinned dead Python and Rust symbols, about 135 more in pinned files, 216 lines of test-only analytics extractors awaiting an owner call, and 2,096 lines of dead legacy viewer components [V; counts from the dead-code spec].
   - **Scripts and workflows:** about 8k lines of scripts are archived or doc-only and can be retired. Two workflows are byte-for-byte duplicates, but they are pinned and stay [S-26, spec repo-hygiene].
2. **The main cost of change is the pin tax, not dead code.**
   - Enforced source pins cover 37 `src/chronicler` modules (27,274 lines), 14 Rust files, 26 viewer files and 7 scripts [V, from preflight data]. They include `main.py`, `simulation.py`, `models.py`, `economy.py`, `agent_bridge.py`, `live.py`, `tuning.py`, `ffi/mod.rs`, `tick.rs` and `economy.rs`.
   - Every byte change to one of these needs a reviewed exact-inverse layer added to a witness fixture (54 fixtures, 1.1 MB, 13 witness scripts).
   - This is decision D1. Most consolidation that would help expansion goes through these files.
3. **Correctness comes before expansion.** Ten bugs or contract breaches are lead-verified (section 4). Two affect every new world:
   - The EXPAND target draw ignores the world seed.
   - Four default-path decisions read causal provenance.

   A third affects every live world: governance stays off where the CLI turns it on.
4. **The default-off contract has drifted.**
   - Seventeen systems are on by default for new worlds, governance among them. Its own gate (M67) is still blocked [V, S-29, S-32].
   - Default wiring is maintained twice, in `main._configure_run` and `live._live_world`, and the two lists already disagree (governance) [V].
5. **The simulation is wide but its core is shallow** (measured on aggregate runs [S-28]):
   - Culture sits at its cap in 73–84% of civ-turns.
   - Military is 0 in 39–68% of civ-turns, and war is 0.6–1.5% of chosen actions.
   - About 0.5 famines start per turn, but none becomes a named event.
   - One kind of named event makes up 34–42% of all named events.
   - Money is created by fiat: tax and tithe are credited and debited from nobody, and merchant income is assigned rather than paid by a buyer [V, S-21].
   - The newest connected-world systems were measured adverse or null [S-29].

   A "grand" simulation needs a deeper, conserved core before more parallel subsystems.

**Recommended order:**
1. Owner decisions D1–D8 (section 3).
2. Wave 0 (hygiene).
3. Wave 1 (dead code).
4. Wave 2 (behaviour-neutral fixes).
5. Wave 3 (move detached harnesses out of the package).
6. Wave 4 (consolidation that unblocks expansion).
7. Depth work (section 7), each step behind a switch with a before/after run.

---

## 2. Repository map

| Area | Files | Lines | Shape |
|---|---:|---:|---|
| `src/chronicler/` | 286 | 154,261 | Turn loop: `simulation.run_turn_result` (simulation.py:1891–2772, 882 lines, 10 phases plus feature hook blocks at about 2442–2550). CLI: `main.py` (`execute_run` 1,025 lines, `_configure_run` 396; 236 long options, 68 boolean switches). 59 `*_state.py` modules (8,945 lines) hold switch state. 29 modules are unreachable from production entry points (13,880 lines). |
| `chronicler-agents/` | 97 | 75,486 | PyO3 crate with `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator`. `ffi/mod.rs` is about 5.8k lines (`tick_economy` alone is 884). The `tick.rs` monolith runs from 498 to 1523. Checkpoint layout fingerprints come from `persist::py::describe`. |
| `viewer/src/` | 479 | 64,111 | `App.tsx` → `phase75/AppShell.tsx` (1,842 lines, 32 `useState`), 71 systems panels (8.3k lines), and about 110 `lib/` readers with a WeakMap index. The decode worker handles large bundles. |
| `tests/` | 476 | 186,854 | Plus 3.3 MB of fixtures, including 54 source-inverse witnesses and a frozen source copy under `reference_baselines/26e1869…/`. 11,972 tests; 0 xfail; 272 skip sites (most are native-absent). |
| `scripts/` | 174 | 47,273 | The oracle lane (76 chunks of ≤110 s each), witnesses, manifests and screen runners. 36 scripts are archived (5.7k lines). |
| `docs/` | 1,519 | 40 MB | 460 JSON files, 69 tracked `.log` files, 39 `.jsonl` files (about 5.8 MB) and one `.cpuprofile`. `CONTINUATION.md` is 2,298 lines. |
| CI | 9 workflows | 2,495 | `tests.yml` has nine jobs, with a critical path of about 17 min. Native shard 0 takes 14.2 min and shard 1 takes 6.9 min, so the split is unbalanced by about 7 min [S-26]. Six workflows are dormant and tied to one branch. |

**Runtime modes:**
- `--agents off`: aggregate only, with no Python economy result.
- `--agents demographics-only`.
- `--agents shadow`.
- `--agents hybrid`: Rust is authoritative, and Python reconstructs the results and keeps oracle fallbacks for ecology and politics.

The Python `compute_economy` (economy.py:1742–2137) is a test oracle with no production caller [S-21].

**Switches:**
- 36 livelihood switches, reached by name through `getattr` in `livelihoods.py` (so vulture flags them falsely).
- 6 expansion switches.
- 84 entries in the served catalog (42 boolean, 42 choice).
- 17 systems on by default for new worlds: `campaigns`, `cities`, `techniques`, `epidemiology`, `contact_ledger`, `finance`, `diplomacy`, `maritime`, `gp_agendas`, `nomads`, `guilds`, `agent_movements`, `historiography`, `languages`, `fisheries`, `mutual_aid`, `governance` [V].

---

## 3. Owner decisions (needed before the waves that depend on them)

| # | Decision | Why it blocks | Recommendation |
|---|---|---|---|
| **D1** | **What to do with the source-witness pins.** They prove historical review chains by projecting current bytes back through reviewed patches (`scripts/testing/*_witness.py`, `tests/fixtures/*_source_inverse.json`). | Any edit to the 37 + 14 + 26 + 7 enforced files needs a new reviewed inverse layer. AGENTS.md forbids rewriting a pinned hash. The witness checks bytes, not behaviour. | **Option A (recommended).** Freeze the witness lane as historical evidence. Keep the fixtures but stop enforcing them on current source, by moving the 9 `test_*_witness.py` files to a historical marker or archive. Gate refactors with `scripts/turn_speed_identity.py run/compare` (9 behavioural cases), the oracle lane, the native tests and the 200-seed gate for behaviour changes. **Option B.** Keep the pins and pay one reviewed inverse layer per touched file. **Option C.** Retire pins only for files in a declared refactor scope. Under A or C, AGENTS.md and DEVELOPMENT.md must change in the same PR. |
| **D2** | **Seventeen default-on systems versus "experimental stays default-off".** Governance (M63–M66, PSI) is on by default while M67 is "not qualified" (`docs/governance/m67-readiness.md`). Fisheries is on with a `[CALIBRATE]` constant [S-12]. | Every new world runs these systems, which a new contributor would read as unqualified experiments. | Declare these 17 the "production core" in one registry, with tests and a list of what each changes. Separately decide whether governance and fisheries stay on or move behind a profile. Fix the live/CLI drift either way (bug 3). |
| **D3** | **Aggregate RNG corrections.** The EXPAND draw ignores the seed (bug 2); additive-seed collisions; the order of food debits depends on PYTHONHASHSEED (bug 4). | AGENTS.md says to preserve aggregate RNG behaviour. A fix changes outcomes on the default path. | Ship one documented "RNG hygiene correction": a new baseline, a `system_rng(namespace, world, *parts)` helper, and a PYTHONHASHSEED sweep test. Then relax `what_if.require_hash_seed`. |
| **D4** | **Provenance decision reads.** Seven are grandfathered at `tests/test_provenance_decision_guard.py:176`. Four are on the default path: `cities._lord_change`, `diplomacy._aid_convoys`, `epidemiology._reports`, `nomads._herds` [V]. | The contract says causal records describe outcomes, not decide them. Fixing these changes default-path outcomes. | Move each decision onto simulation state, one per PR, each with a baseline. |
| **D5** | **Health crowding default.** `public_health_state.py:46` defaults to `legacy_displacement`, the coupling the rework confirmed, while the corrected screens used `density_only` [V]. | Changing a persisted default changes results when the feature is enabled. Public health itself is default-off. | Keep `legacy` for saved worlds, and make new worlds that enable `--public-health` default to `density_only`. Document this as a correction. |
| **D6** | **Where detached harnesses live.** The 29 unreachable modules: experiment sessions, governance measurement and capture, expansion audits, memome, health-care observation and others. | Several have digest pins and live in the production import namespace. Their tests are 7.5% of `test_*.py`. | Move them to a sibling package (for example `src/chronicler_lab/`) or `tools/`, with an import shim for one release. Delete only on owner request. |
| **D7** | **Duplicate models.** Two war models (legacy `resolve_war` and campaigns). Two era-cost rules: legacy charges at advance, while `techniques` (default-on) charges per invention. Two movement models. A Python ecology copy and a Rust one. A Python relationship-formation fallback (`relationships.py:201–415`, `simulation.py:2576–2600`, about 250 lines) that production never reaches, because `agent_bridge.py:1290` sets `rust_owns_formation = True` unconditionally [V]. | Each pair doubles the cost of every change in that area. | Keep the legacy war model only as the `--no-campaigns` kernel for old saved worlds. Choose one cost rule for era advance (bug 5). Keep the Python ecology oracle, because it is the `--agents off` tick. Delete the formation fallback, or put it behind an explicit test flag. Generate shared constants from one source. |
| **D8** | **Evidence in git.** 69 `.log` files, about 5.8 MB of `.jsonl`, and dated progress boards. | They slow every clone and grep, and old status text contradicts itself: README names #69, AGENTS #81, RECOVERY #92 and CONTINUATION #99. | Move logs and run output to release assets or archive branches, keeping one summary per screen family. Byte-identical evidence JSON that tests read stays in place [S-30]. |

---

## 4. Bugs and contract breaches

### Lead-verified [V]

| # | Bug | Evidence | Effect | Fix | Breaks |
|---|---|---|---|---|---|
| 1 | Live int parsing crashes on `Infinity` | `live.py:1129–1136` catches `(TypeError, ValueError)` around `int(value)`; `int(float('inf'))` raises `OverflowError` | A client message with `1e999` or `Infinity` kills the live sim thread | Also catch `OverflowError`, or check `math.isfinite` first | Nothing (`live.py` is pinned, so it needs D1 or an inverse layer) |
| 2 | EXPAND target draw ignores the world seed | `action_engine.py:198`: `random.Random(world.turn * 1000 + civ_idx)` | Every seed draws the same expansion targets on the default path, which correlates seed sweeps | `stable_hash_int("expand", world.seed, world.turn, civ.name)` | Outcome change on the default path (D3) |
| 3 | Live new worlds miss the governance default | `main.py:1648–1653` sets governance only when `fresh_world`; `live._live_world` (1290–1440) sets the other 16 defaults but never governance (`grep governance live.py` is empty) | Live runs and CLI runs of the same world diverge | One default registry used by both paths | Live outcomes change, so document it as a correction |
| 4 | Food iteration order depends on PYTHONHASHSEED | `war_requisition.py:183` iterates `FOOD_GOODS`, a `frozenset` (economy.py:51); `PYTHONHASHSEED` 0–3 give four different orders, while seed 0 is stable (`salt, grain, fish, exotic, botanicals` on Python 3.13). The same set also orders float sums and a draw-down loop in the goods economy (`economy.py:167,405,465,479` and `consume_from_stockpile`) [V, spec rng-and-defaults] | Stockpile composition after army supply, and the last bits of goods-economy sums, vary between processes run under different hash seeds | A fixed tuple equal to the seed-0 order, which keeps the existing seed-0 baselines byte-identical | Changes only runs made under other hash seeds |
| 5 | Spurious `capability_scholarship` event; two era-cost rules | `tech.py:95–115` emits `capability_scholarship` before the affordability check. The legacy path charges the era cost at advance; the `techniques` path (default-on) charges `era_cost / INVENTIONS_PER_ERA` per invention instead (`techniques.py:105,544–565`), so it is not free [V] | The event is emitted on turns the civ cannot afford; the two paths price eras differently | Move the emit after the check; choose one cost rule (D7) | Event stream; outcome if the cost rule changes |
| 6 | Health crowding default keeps the confirmed coupling | `public_health_state.py:46`; `public_health.py:427` applies `1 + DISPLACEMENT_CROWDING * displaced` | Enabling public health without the flag reproduces the defect the rework found | D5 | Persisted default |
| 7 | Provenance read by decisions on the default path | `tests/test_provenance_decision_guard.py:176` `KNOWN_DECISION_READS` | Breaks the "narration and provenance only describe" contract | D4 | Default-path outcomes |
| 8 | Off-mode transient flags are never cleared | Off-mode clears at `simulation.py:2379–2387` omit `_raided_this_turn` (set by `nomads.py:1163`) and `_catastrophe_deaths_this_turn` (`utils.py:86–87` adds to it every turn); only `agent_bridge.py:570–571` clears them | Latent: the catastrophe counter grows without bound in off mode and would leak into the first native batch after a mode change | Shared `clear_region_transients(world)` called on both paths | `simulation.py` is pinned |
| 9 | Frozen tuning file cannot be loaded | `load_tuning(Path("tuning/m53a_frozen.yaml"))` raises `ValueError: non-numeric leaf at 'substrate_changes'`; `m53_baseline.yaml` loads with about 130 unknown-key warnings (Rust-side agent constants Python cannot set) | Users pointing `--tuning` at shipped files get a crash or silent no-ops | Move these files to docs evidence, or give them a `kind: record` header that the loader refuses with a clear message | `tests/test_tuning.py:218` glob test |
| 10 | Treasury money and merchant income created from nothing | `wealth_accounting.py:71–75` documents tax and tithe as "credited to the treasury, debited from nobody"; `economy.rs:2335–2337` pays priests `TITHE_RATE × tithe_base` while `factions.py:426–428` credits the treasury from the same base [S-21] | No closed money supply. Agent wealth and treasuries inflate by design | Depth item (section 7): debit payers, collect the tithe once, add a closure test | Outcome change; native rebuild |

**Downgraded:**
- **Former bug 5 (food residual) is retracted** [V]. `CAPTURED` (`grain_reserves.py:286–291`) only reassigns `granary.owner` and leaves the grain where it is, so the public residual (`food_accounting.py:58–60`) is correct without a captured term. FIX-2 becomes a regression test.
- `simulation.py`'s `except BaseException` handlers re-raise after rollback (2134–2140, 2326–2333), so they do not swallow errors.
- `timber_orders.py:266,327,391,564` hard-codes `0.99`, but `TRANSIT_DECAY["timber"]` is `0.01`, so the values agree. This is fragile, not a bug.
- A deterministic CI failure on `codex/cw-rework` (run 42417373801) was fixed in later pushes [S-26].

### Scout-reported [S] (verify before fixing)

**Saved worlds and switches**
- Saved-world prerequisite checks accept only an explicit `True`, not `_on()` (`livelihoods.py:754–792`) [S-06, S-07].
- On resume, `--workshops --workshop-mode cost_only` silently overwrites a saved `operate` mode. `_check_prerequisites` compares six keys only (`livelihoods.py:713–722`) [S-32, probed through `configure_expansion_features`].
- Mode flags given without their switch are accepted and then dropped, for example `--workshop-mode` without `--workshops` [S-32].

**War**
- Early returns in `war.declare_or_press_war` drop events.
- Non-roster army casualties ignore the actual drain.
- About 17% of soldier deaths are natural deaths booked as casualties [S-09, S-29].

**Rust politics, economy and agent core**
- Politics step 11 is computed in Rust and then discarded by Python (`politics.rs:2888–3025` against `simulation.py:1466–1492`) [S-08].
- Indexing at `politics.rs:1030` and `1053` has no guard [S-19].
- `IdSlots::new` allocates a dense table sized to the largest id ever issued. It is rebuilt at 45 call sites, so its cost grows with run length (`pool.rs:23–35`) [S-20, S-21].
- `try_spawn` duplicates its init branches [S-20].
- The turn is truncated to `u16` [S-20].
- `settle_food_purchases` panics across FFI (`wealth_transfer.rs:459,475`). With zero sale weights, buyer money is neither credited nor refunded (`:470`) [S-21].
- `partial_cmp().unwrap()` in sorts panics on NaN (`provisioning.rs:275,847`) [S-21].
- `tick_economy` discards its `season_id` argument (`ffi/mod.rs:3438`) [S-21].
- `TITHE_RATE` is a duplicated literal (`factions.py:35`, `economy.rs:113`). There is no tuning key for it, so no override can desync; the risk is the two literals drifting [V, corrected from S-21].

**Rust society**
- Culture-distribution weights saturate at `u16` (`culture_tick.rs:95–104`). A region with more than 65,535 agents loses its dominant value in drift sampling, which matters at M61b scale [S-22].
- `partial_cmp().unwrap_or(Equal)` comparators are not total under NaN (`formation.rs:789`, `movements.rs:452`, `politics.rs:1407`) [S-22].
- The hand-rolled SHA-256 in `politics.rs:745–845` is tested only on the empty input, yet it feeds seeds at `politics.rs:1147,1377,1835` [S-22].
- Rust `stable_hash_int` hand-quotes strings with `'…'`, while Python uses `repr`. A civ name containing `'` or `\` would hash differently [S-22].

**Tuning, terrain and numerics**
- Eight tuning keys are accepted but never read (`tuning.py:29,47,57–59,110,199,201`) [S-02].
- `hills` has no row in `TERRAIN_ECOLOGY_DEFAULTS` or `TERRAIN_ECOLOGY_CAPS`, but `ffi_constants.py:12–24` maps it to plains on purpose, so Python and Rust agree. The fix is an explicit row plus a parity test, not a behaviour change [V, corrected from S-02, S-12].
- `economy.py:442–450` sums floats over a set, so the last bits depend on order [S-31].
- Additive seeds collide (`agent_bridge.py:2244`, `simulation.py:1066`, `emergence.py` `seed + turn*K`) [S-31].

**LLM clients**
- No timeouts, no truncation detection, no batch deadline and no budget enforcement.
- Default models are `claude-sonnet-4-6` and `gemini-2.5-pro` [S-15].

**Live server and persistence**
- A failed start is silent, blocking work runs on the event loop, the scenario path has no guard, and reconnect state is held twice [S-18].
- Three bundle readers apply different strictness [S-18].
- `historiography.py:490–496` and the identical code in `languages.py` already write by temp file plus `replace`. They lack fsync, a unique temp name and cleanup [corrected, spec behaviour-neutral-fixes].
- Simulate-only runs write `state.json` relative to the working directory. A scout run created `./output/`, which the lead removed [S-28].

**Viewer**
- WebSocket messages are parsed into `any` with no shape check (`useLiveConnection.ts:260–263`) [S-23].
- History is validated twice per load [S-23].
- `npm run lint` works and CI runs it. Only the scout's `-f unix` invocation failed. The real gap is that `viewer/scripts/*.mjs` sit outside the eslint globs [corrected, spec viewer-streamlining].
- `playwright` is used by 10 viewer scripts and the Python QA scripts but is not declared as a dependency [S-23].

**Treasury paths**
- With agents off, in shadow mode and in demographics-only mode, `phase10_acc` is `None`, so the direct `civ.treasury` writes run in production and do not floor at zero, while the accumulator path does. AST finds 48 treasury dual-path sites [spec turn-loop-consolidation].
- `gp_agendas._projected_treasury` ignores the accumulator watermark; this is a suspected double count, filed as a correction candidate [spec turn-loop-consolidation].

**Validation**
- No multiple-comparison correction.
- The seed registry is not enforced on the gate.
- `run_needs_oracle_best_of` has selection bias.
- No connected-world extractors in analytics [S-17].

**Setup**
- `scripts/cloud_setup.sh` always exits 0, even when steps fail (`set -uo pipefail` without `-e`) [S-26].

---

## 5. Streamlining plan

The line counts are approximate. "Pinned" means an enforced pin, so the change needs D1 or a reviewed inverse layer. Run `scripts/refactor_preflight.py --git-diff origin/main` on every wave.

### Wave 0: hygiene (docs and config; no runtime)

| Item | Saves | Breaks | Risk |
|---|---|---|---|
| One current-status block, with README, AGENTS and RECOVERY linking to CONTINUATION; move CONTINUATION lines 31–2298 into `docs/superpowers/progress/continuation-history.md` | about 2,000 lines out of the entry file | Doc links only (preflight: 7 documents name CONTINUATION) | low |
| `.gitignore`: `*.log`, `*.cpuprofile`, `.coverage`, `htmlcov/`, `.mypy_cache/`, `.ruff_cache/`, `.hypothesis/`, `*.so`, `*.pyd` | prevents growth | none for untracked files | low |
| Archive the superseded 2026-03/04 audits (11 of their 12 top findings are fixed) | about 3,100 md lines | none found | low |
| Fix stale docs: `feature-options.md:40,93,106,260`; `scripts/archive/README.md`; the `analytics.py` `"version": "post-M18"` string | 0 | none | low |
| `tests.yml`: a `concurrency` group; pin `rust-toolchain` to 1.85 (it floats `@stable` in 11 uses); standardise on SHA action pins | 0 | workflow byte pins only on `native-two-shards*.yml.in` | low |
| `cloud_setup.sh`: keep going after a failed step, then exit non-zero | 0 | none | low |

### Wave 1: dead code (no behaviour change)

**Unpinned, so these can go now:**

| Candidate | Lines | Also update | Risk |
|---|---:|---|---|
| Viewer legacy components `ChroniclePanel`, `EventLog`, `FactionDashboard`, `Header`, `RegionMap`, `SetupLobby`, `StatGraphs`, `TerritoryMap`, `TimelineScrubber` [V: none has a non-test importer; `RegionMap` is imported only by `SetupLobby`] | 2,096 (+about 440 test lines; drops the `d3-force` dependency) | `components.test.tsx`, `SetupLobby.test.tsx`, `RegionMap.test.tsx`, the legacy block of `FeatureRequests.test.tsx` | low |
| `analytics.py` test-only extractors (1816–2198): delete, or wire into the analytics that DEP-7/DEP-4 need (owner call) | about 216 | their tests (historical pin only) | low-med |
| Rust `behavior.rs:1275–1398` `evaluate_region_decisions_v1` | 124 | none | low |
| `narrative.py` wrappers: `build_before_summary`, `build_after_summary`, `build_chronicle_prompt`, `thread_domains`, `render_because` | about 56 | 3 test files | low |
| `named_events.py` 4 `generate_*_name` functions | about 50 | `tests/test_culture.py:637–666` | low |
| `traditions.apply_prophet_martyrdom` | 36 | `tests/test_traditions.py` | low |
| Rust `satisfaction.rs` `resource_satisfaction` and `trade_satisfaction`; `sort.rs` `sort_by_region` (+ bench arm) | about 40 | in-file tests, `benches/cache_bench.rs` | low |
| `adjacency.is_chokepoint` | 24 | `tests/test_adjacency.py:80` | low |
| `timber_supply.pending_bills` | 14 | docs mention it | low |
| `culture.py` unused constants (`K_CULTURE_PROJECTION_THRESHOLD` stays: it is a live tuning key) | about 9 | some test imports | low |
| Viewer `factionColorDark`, `movementsOf`, `famineSpans`, `templeEventText`, the `useBundle` `parseBundle` re-export; 46 `export` keywords that nothing outside the module uses | about 30 | a few tests | low |
| `filter_targets_by_fog`, `reform_services._service`, `narration_provenance.fact_ids`, `ritual_gatherings_enabled`, `war/common.held_regions`, `ScenarioConfig.secession_pool` | about 25 | 1–2 tests | low |
| Rust `DEFAULT_AGENT_LIMIT`, `DEFAULT_CANDIDATE_LIMIT` (`PURPOSE_RESTITUTION` stays: the `PURPOSES` table is append-only) | 2 | none | low |
| Rust items only in-file tests use, moved under `#[cfg(test)]`; `marriage_scan_reference` becomes a loop over `marriage_region_reference`. `marriage_scan` and `spatial_drift_step*` stay, because the `chronicler-agents/tests/*.rs` integration crates call them [S-22, corrected] | see the dead-code spec | in-file tests | low |
| `religion.py:43–44` `PERSECUTION_REBEL_BOOST` and `PERSECUTION_MIGRATE_BOOST` (stale; the live values are in `agent.rs:221`) [V] | 2 | none | low |
| **Subtotal** | **about 2,650 source lines**: viewer about 2,130, Python about 300, Rust about 230. The 216 analytics lines are separate (owner call). The [dead-code spec](../specs/2026-11-08-dead-code-removal-design.md) is the authoritative list. | | |

**Pinned (D1 or inverse layers):**
- `main.run_chronicle` (37)
- `events.roll_for_event` and `apply_probability_cascade` (about 55; `simulation.py:54` re-exports them as historical module attributes, so the import path needs a shim or stays)
- `sidecar.SidecarReader` and its 6 readers (about 130)
- `economy.py` test-only helpers (about 48)
- `harvest_forecasts_enabled`
- `ASABIYA_COLLAPSE_VARIANCE_THRESHOLD`
- `ecology.rs` 3 constants

Together these come to about 135 lines, after the corrections in section 8. The `economy.rs` wrappers are not on this list: about 85 integration-test callers use them, so they are a test API (CON-6 makes merging them optional).

**Keep (looks dead but is not):**
- `persist.rs` `field_schema` (checkpoint fingerprint)
- the reserved `agent.rs` RNG offsets
- the snapshot `ambition` field
- `public_health` `legacy_displacement`
- the `food_allocation` `equal` regime and every `cost_only`/`record_only` control arm (they are the ablation controls)
- the `validation_oracles` shim (hash-pinned)
- the 43 livelihoods `set_*_enabled`/`*_active` functions (reached by name through `getattr`)
- pydantic validators

**Do not delete any CLI flag.** Batch manifests, the byte-identical catalog test (`tests/test_feature_matrix.py:96`) and saved bundles depend on them. Hide a flag with `argparse.SUPPRESS` instead.

### Wave 2: behaviour-neutral fixes first, then documented corrections

1. **Neutral:**
   - bug 1 (live `OverflowError`)
   - a regression test for the food residual (former bug 5, retracted)
   - bug 8 (transient clear; neutral in off mode)
   - bug 9 (tuning files)
   - atomic historiography sidecar
   - `cloud_setup.sh`
   - viewer WebSocket shape guard
   - `settle_food_purchases` returns `Err` instead of panicking
   - `total_cmp` instead of `partial_cmp().unwrap()`
   - generic orphan-mode and saved-mode checks driven by the catalog's `requires` [S-32]
2. **Corrections**, each with a baseline and a CONTINUATION entry:
   - bugs 2, 3 and 4 (as one D3 RNG and defaults correction)
   - bug 5 (scholarship event order and era-cost rule)
   - bugs 6 and 7 (D5 health crowding, D4 provenance)
   - the war event and casualty findings [S-09]
   - tithe and tax closure (bug 10)

### Wave 3: move detached harnesses out of `src/chronicler` (D6)

**Modules unreachable from `main`, `live`, `validate` and `narration_audit`** (largest first; this is a move, not a delete):

| Lines | Modules |
|---:|---|
| 1,680 | `experiment_sessions` |
| 1,653 | `governance_measurements` |
| 912 | `expansion_audit` |
| 797 | `validation_compare` |
| 701 | `health_care_observation_codec` |
| 672 | `expansion_compare` |
| 640 | `health_care_observation_mechanics` |
| 632 | `campaign_snapshot_adapter` |
| 600 | `artifact_budget` |
| 507 | `scientific_research_audit` |
| 500 | `history_forensics` |
| 465 | `evidence_admission` |
| 395 | `scientific_receipts_audit` |
| 368 | `checkpoint_replay` |
| 360 | `session_operations` |
| 352 | `memome_experiment` |
| 330 | `kin_root_exposure` |
| 312 | `health_care_capture` |
| 264 | `practice_growth` |
| 251 | `decision_delivery` |
| 239 | `experiment_receipt_inspector` |
| 180 | `governance_sequence` |
| 174 | `shadow_oracle` |
| 173 | `memome_candidate_preview` |
| 169 | `campaign_order_preview` |
| 162 | `session_comparison` |
| 160 | `community_admissibility` |
| 117 | `snapshot_campaign_sessions` |
| 115 | `governance_capture` |
| **13,880** | **29 modules in total** |

**Cost of the move:**
- 21 scripts and 50 test files (25,241 lines) import these modules [spec lab-package-relocation; the audit counted 27 files]. `validation_compare` (used by `validation-gate.yml` through `m53b_run_validation.py`) and `community_admissibility` should stay where they are. `checkpoint_replay.py:144` hashes `Path(__file__).parent`, so moving it needs a fix.
- `experiment_sessions`, `campaign_snapshot_adapter`, `evidence_admission`, `memome_experiment` and `shadow_oracle` have digest pins.
- The `reference_baselines` MANIFEST names some of their paths.
- `load_session` (experiment_sessions.py:1555) reads experiment-session directories that already exist on disk, so readers must keep working.
- Plan one `chronicler_lab` package with re-export shims, and update the oracle chunks and shard manifest in the same PR.

**Related clusters in `scripts/` and CI:**

| Cluster | Lines | Proposed action | Notes |
|---|---:|---|---|
| Archive | about 5.7k | Delete, with the manifest | It is pinned by `tests/test_script_smoke_manifest.py:53`, and four `m53_*` probes are inside the `seed_registry.json` content hash. |
| Doc-only scripts | most of 3,210 | Archive 15 of the 18 | Two are fixture generators, and one is named in hash-recorded evidence JSON. |
| `wealth_floor_*` cluster | 2,331 | Keep | `tests/test_wealth_floor_outcome_checkpoints_v2.py:122–123` hashes v1, and the oracle and shard lists reach the whole cluster. |
| Duplicate `native-two-shards*.yml` | 519 | Keep, and add an index | Both are pinned by `tests/test_native_ci_shards.py` and `tests/test_native_build_lanes.py`. |
| 4 dormant workflows | about 660 | Keep, and add an index | Scripts hash the benchmark workflows. |
| Superseded gates `run_oracle_gate.py` and `m58b_convergence_gate.py` | 367 + 540 | Owner decision | |

### Wave 4: consolidation that unblocks expansion

| Item | What it removes | Saves | Breaks or needs | Risk |
|---|---|---:|---|---|
| **One defaults and switch registry** used by `main._configure_run`, `live._live_world` (17 hand-written blocks), `feature_catalog` and the `batch_manifest` exclusion tuple | drift (bug 3) and four copies of the same list | about 170 | live parity tests; the order pinned by the fisheries/mutual-aid test | med |
| **`SwitchState` base** for the 59 `*_state.py` modules: `_bump` (39 copies), `_state(world)` (39), `__setstate__` default-fill (29), `_lane_active` (5), `_health_holders` (2) | per-switch boilerplate | about 400 | pickle and checkpoint restoration must stay exact; counter key order and types | med |
| **`system_rng(ns, world, *parts)`** in `utils.py`, replacing 10 `_rng` copies and the about 31k per-run `Random(stable_hash_int(...))` sites | stream-contract drift; a stream census becomes possible | about 50 (plus perf) | hash inputs must stay byte-identical, or this goes with D3 | med |
| **Treasury writes through the `money` seam**: about 45–55 direct `civ.treasury` writes and about 40 `if acc … else direct` sites, routed through one helper | the ledger/no-ledger split | about 100 | the accumulator `keep` category; `simulation.py` is pinned | med-high |
| **Phase registry** for `run_turn_result`'s per-feature hook blocks | an edit in the 882-line function for every new system | about 150 | exact order is part of behaviour; prove it with `turn_speed_identity` | high |
| **One source for Python↔Rust constants**: terrain tables, hunger, bonds, movement enums, `SCHISM_SECESSION_MODIFIER`, `TITHE_FOOD_GATE`, `TITHE_RATE`, the 0.1 supply floor (five places), `EconomyConfig::default` | silent drift (only a few parity tests exist) | about 60 | generated file or parity tests; native rebuild | med |
| **Screen runner (re-scoped)**: `screen_runner.py` already is the shared runner. `connected_world_screens.py` and the `cw_*_screen.py` scripts use it, and the older screen files are deliberately frozen evidence (only 18, 6 and 1 top-level names overlap) | nothing to merge | about 0 | CON-8 becomes a hash test for the frozen evidence plus docs; editing `screen_runner.py` invalidates pilots for cohorts not yet spent | low |
| **FFI generics**: 10 local `col_*` macros in `ffi/mod.rs` and 4 in `ffi/batch.rs` become one; one-shot `take_`/`cancel_`/`set_` triads become a generic slot; move `mod tests` (about 1,070 lines) to `ffi/tests.rs`; move the agent-count derivation in `tick_economy` into `economy.rs` | FFI bulk | about 200 | method names must stay; pinned files | med |
| **`tick.rs` phase structs** (the 498–1523 monolith) and `pool.rs` `try_spawn` init helper | Rust hot-path complexity | about 65 | in-file tests pin behaviour; determinism tests | high |
| **Python `compute_economy` becomes a test oracle** (economy.py:1742–2137) | about 800 lines of shadow implementation in the production module | about 800 | 21 test files, 2 scripts, about 17 inverse fixtures | med |
| **Viewer primitives**: `lib/recordGuards.ts` (`object`/`finite`/`count`/`amount`/`integer`, about 144 copies), `readLivelihoodRecord` (41 `*At` readers), `SystemPanelFrame`/`SystemSection`/`usePaged`/`formatters.ts`, `lib/download.ts` | panel and reader boilerplate | about 900–1,300 | `count` variants differ (`isInteger` against `isSafeInteger`): keep each or document the change; 12 pinned panels | med |
| `agent_bridge.build_signals` table-driven validation | 160 lines of repeated checks | about 50 | error strings pinned by tests | low |

### Wave 5: family merges (only after D1, with full identity runs)

These are merges of families of switches, recorded only as candidates (`unverified` sizes) [S-29]:
- **Upkeep:** `maintenance_obligation`, `operating_wear`, `infrastructure_condition`, `repair_projects`, `recovery_crews`, `infrastructure_crews`.
- **Care:** `health_care`, `epidemic_care`, `public_health`, `quarantine_rules`.
- **Teaching:** `learning_services` into `apprenticeship`.
- **Forest:** `timber_stock`, `timber_supply`, `timber_orders`, `harvest_cover`, `clearing_protection`, `commons_rules`.
- **Transfers:** a shared transfer-with-fee primitive over `wealth_transfer.rs`.

Each merge keeps every CLI flag and saved field as an alias, and has to reproduce the held results it replaces.

**Approximate total:**
- Waves 1, 3 and 4 remove about 4–5k lines outright.
- They move about 14k package lines and 14k test lines out of the production namespace.
- They archive about 8k lines of dead scripts. The duplicate and dormant workflows stay, because they are pinned.

The larger gain is that Wave 4 turns "add a system" from edits in about 6 files plus pinned text into one module and one registry entry.

---

## 6. Flaky and fragile

**Tests** [S-25]:
- No flake signal in the last 60 CI runs [S-26].
- Wall-clock deadlines: `tests/test_what_if_process.py:38–86` (a 4 s deadline and `< 5` s asserts), `test_python_qualification.py` (about 12 busy-waits) and the live-server polls (10 s).
- `tests/test_rivers.py` has 13 silent "No adjacencies" skips that depend on world generation.
- `tests/test_validate.py:281` seeds the global `random`.
- About 47% of `test_*.py` files are in no oracle chunk.
- The documented chunk timings are stale (18 chunks recorded, 76 now), and the per-chunk timing receipt is not committed.
- `test_audit_batch_d.py:70–104` re-implements the tithe gate without calling production code [S-21].
- Real multiprocessing under varied hash seeds is untested (batch.py:122 uses no `set_start_method`, and macOS spawns) [S-31].

**Runtime:**
- PYTHONHASHSEED dependence (bug 4, `economy.py:442`).
- Panics across FFI in the Rust money path.
- f32 agent wealth with f64→f32 casts [S-21].
- `IdSlots` cost grows with run length.
- The viewer's live mode copies history every turn and resets its index [S-23].
- The atlas has no pan or zoom and labels overlap beyond about 100 regions; faction hue is `hash % 360` [S-24].

**Process:**
- Native shard imbalance of about 7 min [S-26].
- Unpinned Rust toolchain.
- `cloud_setup.sh` hides failures.
- Undeclared `playwright` dependency.
- The viewer's `.mjs` scripts are not linted.

---

## 7. Toward a grand, broad and detailed simulation

The held results so far (connected-world adverse in 11 of 12 worlds; quarantine null; floor-means relief worse in 12 of 12; budgets cut output in 12 of 12) point to **missing core mechanisms rather than missing subsystems**. A suggested order follows; each item goes behind a switch, with a before/after run and, for promotion, the 200-seed gate.

**A. Make the core loop carry information** [S-28]
- Replace hard caps on culture, economy and asabiya with saturating curves or decay. They pin at the cap 73–84%, 24–48% and 20–31% of the time.
- Give military a stock: mustering, upkeep and attrition tied to war state (it is 0 in 39–68% of civ-turns; war is 0.6–1.5% of actions).
- Famine episodes already exist (`provenance.py` `ChronicEpisode`, `famine_ended`). Give them a peak and named events, and audit the trigger rate (`ecology.py:263`).
- Rebalance the named-event generator: `propaganda_campaign` is 34–42% of named events.
- Compute an aggregate inequality measure. `gini` is 0 in every aggregate civ-turn.

**B. Close the books** [S-04, S-21]
- One conserved money supply: debit tax and tithe payers, collect the tithe once, have buyers pay sellers for merchant margin through `settle_pairs`, and give merchants a wealth book and `credit.rs` a loan book.
- Add a treasury conservation identity, and a per-turn closure check the viewer can show.
- Extend household food budgets from the pilot regions to all regions.

**C. Measure welfare, not regional totals** [S-29]
- Add household access and welfare primaries using the `food_allocation` rations.
- Pair each subsystem's cost and benefit at equal cost before reading its results.

**D. Deepen the world**
- **Space:** per-region asabiya (M55b; the amendments rate it highest-payoff), settlement hierarchy and roads, routes beyond adjacency, a variable resource-slot count (the three fixed slots are FFI-pinned).
- **Economy:** more than 9 goods, per-good prices, a real craft chain, prime movers and fodder, domesticates and herds.
- **Society:** age structure, M64 commons, M70 revolution cascades on the existing `knowledge.rs` packets, M71 beliefs and deception, languages and culture that feed outcomes, law, bureaucracy and tax administration, real mercenaries.
- **Knowledge:** tech diffusion across controllers (today it spreads only within one controller), curation with a diversity term.
- **World generation:** more than 12 template regions, 6 civ templates and 10 traits. Procedural scenarios.

**E. Scale**
- Run the real M61b validation beyond the largest measured 53k agents.
- Make the Morton order (`spatial.rs:1363`) feed iteration, or delete it.
- Make `IdSlots` incremental.
- Widen the `u16` culture weights and cell-occupancy diagnostics.
- Make exact spatial drift population-aware: it is O(N²) per region today, while fast mode is bounded [S-22].
- Give spatial drift barriers (rivers, roads, terrain); attractors are its only pull today [S-22].

**F. Make grand runs reproducible and comparable**
- Add `--feature-profile` (`classic`, `new-world`, `agent-economy`, `connected-full`, `controls`), expanded and validated by `feature_catalog` and recorded in batch manifests [S-32].
- Enforce the seed registry on the gate, add a multiple-comparison correction, add a PYTHONHASHSEED sweep, and add a cheap nightly smoke regression. The weekly `full` gate already runs from `validation-gate.yml` [S-17, S-26, S-31, spec economy-depth-and-measurement].
- **Viewer:** a zoomable timeline and map pan and zoom, a turning-point strip across systems, a same-run turn-versus-turn diff, CSV export of the per-turn series, and memoised scrub paths [S-23, S-24].

---

## 8. Errata (2026-11-08, found while writing the specs)

These corrections were found while writing the [roadmap](../roadmaps/streamline-and-deepen.md) specs. They are applied in the sections above, and the lead re-checked the marked ones [V].

- **Food order [V].** The audit's first probes ran `python -I`, and isolated mode ignores `PYTHONHASHSEED`, so the "per-seed" orders they recorded were random. Re-measured without `-I`, the seed-0 order is stable and seeds 0–3 differ. The conclusion stands. The fix uses the seed-0 order, so the existing baselines stay byte-identical.
- **Era cost [V].** The default `techniques` path charges per invention, so era advances are not free on it.
- **`hills` and `TITHE_RATE` [V].** `hills` maps to plains intentionally. There is no tuning key for `TITHE_RATE`; it is only a duplicated literal.
- **`wealth_floor` v1 [V].** v1 is hash-pinned by the v2 test, so it is not dead.
- **`economy.rs` wrappers.** They have about 85 integration-test callers, so they are not dead.
- **Screen runner.** The screen-runner merge is already done; CON-8 is re-scoped.
- **Validation gate.** A weekly `full` validation gate already exists.
- **Workflows.** The duplicate and dormant workflows are pinned or hashed, so they stay.
- **`_rng` helpers.** They are not uniform: `gp_agendas` and `epidemiology` hash without a system prefix.
- **Live defaults.** Live applies the defaults in a different order from the CLI, as well as missing governance.
- **`gini`.** `gini` is set at `main.py:980`. A separate aggregate field avoids shifting `validation_regression`.
- **Hybrid mode.** Hybrid mode overwrites military, economy and culture from Rust aggregates.
- **Food residual [V].** Former bug 5 is retracted: `CAPTURED` changes owner only, so the residual is already correct.
- **Sidecars.** The historiography and languages sidecars are already written by temp file plus `replace`; only durability is missing.
- **Comparators.** `total_cmp` alone would reorder `-0.0` against `0.0`, so FIX-6 normalises with `+ 0.0` first.
- **Provenance reads.** The seventh grandfathered read is `scholarship._sack_cause`.
- **Dead-code list [V for the first four].** These are not dead:
  - `DEMAND_SCALE_FACTOR` and `INFRASTRUCTURE_DISCOUNT`: inert 1.0 multipliers that code still reads.
  - `sandstorm`: emitted at `climate.py:343`.
  - `events.roll_for_event`: re-exported at `simulation.py:54` as a historical attribute.
  - `K_CULTURE_PROJECTION_THRESHOLD`: a live tuning key.
  - The 8 FFI exports: the observation surface of native-only tests.
  - `PURPOSE_RESTITUTION`: part of an append-only table.
  - The `tick.rs` "duplicate" clears: a start-of-turn reset plus an end-of-tick clear.
  - `marriage_scan` and `spatial_drift_step`: called by integration tests.
- **Viewer lint.** `npm run lint` works; only the `.mjs` scripts are unlinted. The audit also missed several enforced viewer pins (`useLiveConnection.ts`, `historyComparison.ts` and seven more `lib/` files).
- **Lab modules.** 21 scripts and 50 test files import them, not 27 files. Keep `validation_compare` and `community_admissibility` in place.
- **Treasury.** There are 48 dual-path sites by AST, not about 40. The direct-write branch is live in off, shadow and demographics-only modes and has no floor at zero.

## 9. Scout index

| # | Area | # | Area |
|---|---|---|---|
| 01 | turn loop | 17 | validation and analytics |
| 02 | models and schema | 18 | persistence and live |
| 03 | agent bridge | 19 | Rust FFI |
| 04 | economy and money | 20 | Rust agent core |
| 05 | food chain | 21 | Rust economy |
| 06 | livelihoods and workshops | 22 | Rust society |
| 07 | recovery chain | 23 | viewer core |
| 08 | politics and diplomacy | 24 | viewer components |
| 09 | war and military | 25 | tests and flakiness |
| 10 | population and health | 26 | CI, scripts, dependencies |
| 11 | movement and settlement | 27 | mechanical dead code |
| 12 | ecology and geography | 28 | simulation behaviour |
| 13 | culture and characters | 29 | roadmap versus reality |
| 14 | knowledge and tech | 30 | docs hygiene |
| 15 | narration and history | 31 | determinism and RNG |
| 16 | governance experiments | 32 | feature flags |
