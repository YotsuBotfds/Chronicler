# Streamline and deepen — integration ledger

The lead session's dated record of what was integrated on `claude/exciting-mayer-nolksw`, how each piece was reviewed, and which gates ran. Nothing here is merged to `main`. Opening PRs is the owner's call. Decisions are in [streamline-and-deepen-decisions.md](streamline-and-deepen-decisions.md) and statuses in [streamline-and-deepen.json](streamline-and-deepen.json).

**Process for every task**
- An implementer works on its own branch `sd/<task>` from the roadmap plan block, in an isolated worktree.
- An independent reviewer then re-runs the checks. Corrections and the pin transition get two reviewers, one for scope and behaviour and one for repository contracts.
- Up to two fix and re-review rounds follow.
- The lead merges only approved branches, with `--no-ff`, so each reviewed head stays in history. The lead then runs the gates below on the merged head.

**Shared identity baseline.** All nine `scripts/turn_speed_identity.py` cases were run from `4e8e76b7`, with the native extension built from that tree (SHA-256 `2125dfd7b5f9e2091ac70fad5f08709c14d2e553ab65691f7638d219e9c22641`). The run used Linux and the cloud container's Python 3.13.18.

## 2026-11-09 — integration 1 (R1/R2, first batch)

Merged, each approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Class | Notes |
|---|---|---|---|
| HYG-2 | `a00ada41` | config | `.gitignore` additions; `git ls-files -ci --exclude-standard` is empty |
| DEAD-3 | `48108143` | removal | Dead Rust helpers removed; five test-only functions put under `cfg(test)`; `cargo check` gives 0 warnings |
| FIX-6, FIX-13 | `a4e37a63` | fix | `settle_food_purchases` returns `Err` before any pool write; `+0.0`-normalised `total_cmp` comparators at the six sort and argmax sites |
| DEAD-2a | `a457aab5` | removal | Dead Python leaf helpers removed from 10 modules, with their tests |
| FIX-4, FIX-5, FIX-12, FIX-2 | `e54095ca` | fix + test | M53 record YAMLs moved to `docs/validation/m53/`, with a clean-load test; historiography and languages sidecars made atomic; FIX-2's audit claim was not reproduced (`CAPTURED` moves ownership, not stock), and a test pins the residual |
| FIX-9 | `686c1224` | fix | LLM client timeout (120 s), truncation counts, token and call budgets, batch poll deadline; narration only |

Gates on the merged head `e4557096`:
- `scripts/refactor_preflight.py --git-diff 4e8e76b`: no content pin and no recorded digest touched. The only `enforced` items are native-shard and oracle-chunk ownership of eight test modules that were edited in place, which is allowed.
- `scripts/run_python_oracle_checks.py --jobs 2`: PASS in 237.4 s. 76 chunks; 8,139 passed, 69 skipped, 0 failed. The 110 s limit is unchanged.
- `cargo test --locked`: every test binary passed (library 779 passed).
- The native extension was built fresh from `e4557096`. Its SHA-256, `97049985efadbee551631cb3166267f8c8cc403eb1c418b80db8ecafd2e7c6f8`, matches the FIX-6 implementer's independent build. `check_python_env.py --expect native` passes.
- `turn_speed_identity.py`, all 9 cases against the baseline: **399 files compared, 0 differences**. This covers the cases the FIX-6 review noted as unrun (off_s7, proc48_off_s7, scaled22k_s42 and scaled52k_s7).

Not run: viewer lanes (no viewer change in this batch), the 200-seed gate (no outcome change intended), and GitHub CI (no PR).

Integration notes:
- A disk-full error during workflow A stopped worktree creation for HYG-1/HYG-3, HYG-5/HYG-6, DEAD-2b, DEP-7 and the FIX-7 review. They were relaunched, and those agents now remove their venvs when they finish.
- FIX-7 is held back for the scope ruling recorded in the decision record.

## 2026-11-09 — integration 2 (tooling chain)

Merged `sd/HYG-8`, which carries the sequential tooling chain. Each step was approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Class | Notes |
|---|---|---|---|
| CON-8 | `35307b63` | tooling/test | Pins the frozen screen scripts by SHA-256; tests the runner's state files; the single-runner docs list the unspent cohorts |
| DEP-9 | `3bec6e62` | tooling | Seed-registry gate check (a `full` run off its gate range is refused), with the 14 existing reuses on an explicit allowlist; Holm-adjusted needs p-values, reported only; `best_of` documented as never a gate; `--hash-seed`, default `0`, so the default env is unchanged; `hashseed-sweep.yml`, kept off with `if: false` until COR-1; nightly `regression-smoke.yml` with a locally generated fixture; a real two-process batch test under hash seeds 0 and 1 |
| ENV-4 | `2dcc5227` | fix | Parallel batch workers start with `spawn` and `PYTHONHASHSEED=0` |
| HYG-8 | `05bf9a31` | ci | Five later-added native modules moved from shard 0 to shard 1. The timings are real per-module JUnit times from main Tests runs 42431233265, 42428257952 and 42417310582. Projected shard times are 628.5 s and 620.6 s, a 1.2 percent gap |

Gates on the merged head `78caa287`:
- Preflight against `4e8e76b` (70 paths): no content pin or digest touched outside in-place shard and chunk ownership.
- Oracle lane `--jobs 2`: PASS in 280.2 s. 76 chunks; 8,177 passed, 69 skipped, 0 failed.
- `pytest -m real_process tests/test_batch_parallel_real.py`: 1 passed.
- Focused new and shard tests (`test_native_ci_shards`, `test_seed_registry_check`, `test_validation_multiplicity`, `test_screen_frozen_evidence`): 243 passed.
- Identity for off_s42, off_s7, hybrid_s42 and proc48_off_s7, using the integration-1 native (no Rust change since): 144 files compared, 0 differences.

Not run here:
- `actionlint` (not installed) on the new workflows.
- The first dispatch of `regression-smoke.yml`, so runner minutes are unmeasured.
- The shard balance on CI (needs a PR).
- The 200-seed gate (no outcome change).

## 2026-11-09 — integration 3 (relaunched R1/R2 tasks)

Merged, each approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Class | Notes |
|---|---|---|---|
| HYG-1, HYG-3 | `e943525e` | docs | `docs/CONTINUATION.md` opens with `## Current status` and is under 100 lines; history moved byte-for-byte to `progress/continuation-history.md`; README, AGENTS and RECOVERY drop PR chains; new `tests/test_docs_status.py`; audits index; feature-options corrected (42 switches, 861 pairs, 0 refused, dated 2026-11-08) |
| HYG-5, HYG-6 | `aa9e6a2b` | tooling | `cloud_setup.sh` prints a failure summary and exits non-zero only under `CHRONICLER_SETUP_STRICT=1`; 15 doc-only scripts moved to `scripts/archive/` with smoke-manifest entries; `docs/workflows/README.md` index |
| DEAD-2b | `8b9973a6` | removal | Test-only narrative wrappers and five analytics extractors removed |
| FIX-7 | `e01bda87` | fix (CLI acceptance) | Saved-world prerequisite refusals with "pass --no-<x> to end it". Changed-mode and orphan-mode refusals dropped under the lead scope ruling (decision record) |
| DEP-7 | `751aae7c` | measurement (partial) | `household_access` metrics module, state, analytics section (absent unless present) and viewer reader. **Switch registration deferred:** it needs `batch_manifest.py` (enforced) and waits for PIN-1, so the module is not reachable from the CLI yet |

The lead added commit `abb97f5`. It keeps the four summarised CONTINUATION entries verbatim at the end of the history file, repoints two RECOVERY.md links (minor HYG-1 review findings), and points the status block at the decision record and this ledger. Merge conflicts were only the module-count assertion in `tests/test_native_ci_shards.py` (now 468), resolved by addition.

Gates on the merged head `8ba44078`:
- Preflight against `4e8e76b` (134 paths): no content pin or digest touched.
- Oracle lane `--jobs 2`: PASS in 176.8 s. 77 chunks; 8,192 passed, 69 skipped, 0 failed.
- Focused suite: 414 passed. It covers docs status, household access, livelihoods wiring, epidemic care, recovery-skills wiring, household retail, recovery crews, narrative, batch narration, analytics, check_python_env and the screen runner.
- `cloud_setup.sh` with `PATH=/nonexistent` and a scratch native venv: exit 1 with `CHRONICLER_SETUP_STRICT=1`, exit 0 without it.
- Identity, 7 cases (all but the two scaled ones), integration-1 native: 357 files compared, 0 differences.

Open owner questions from DEP-7 (no answer needed until registration):
- the weights of a joint food-and-care welfare primary;
- whether P2's denominator is all observed person-turns (as implemented) or retail person-turns only;
- whether "child shortfall share" means the children's share of total shortfall (as implemented).

## 2026-11-09 — integration 4 (PIN-2, PIN-1; DEC-1 option A)

Merged `sd/PIN-1b`, which carries three steps. Each was approved by two independent reviewers, one for scope and one for contracts, with no blocker or major findings:

| Task | Reviewed head | Notes |
|---|---|---|
| PIN-2 | `7e3907cf` | 8 `g_*` cases, `GATE_PYTHON`/`GATE_NATIVE`, `digest`/`check`/`receipt`; `identity-gate.yml`; goldens captured **locally** at `5eedc67` (Linux, 3.13.18, rustc 1.97.0, native `2125dfd7…`), determinism shown by two re-runs per lane; `coverage.json` maps all 91 witnessed paths: 44 to gate cases, 47 to tests, none to `none` |
| PIN-1a | `72442fda` | `freeze_pin_sources.py`, `frozen_sources.py`; 91 copies plus MANIFEST under `tests/fixtures/frozen_pin_sources/`; freeze commit `c3d752fa` (main) |
| PIN-1b | `616ff9f3` | The 9 witness modules and the embedded chains read the frozen copies; preflight reports witnessed sources as historical and the copies as enforced; AGENTS.md, DEVELOPMENT.md and scripts/README.md updated |

Gates on the merged head `526f1b52`:
- Oracle lane: 77 chunks; 8,204 passed, 69 skipped, 0 failed.
- The 14 witness and embedded-chain modules plus preflight and turn-speed tests: 320 passed, 61 subtests.
- `freeze_pin_sources.py --verify`: 91 files, 0 mismatches.
- Identity: 4 cases, 0 differences.
- **Identity gate.** The Python lane gave 53 files, 0 differences. The native lane, with the integration-1 extension and a build receipt, gave 133 files, 0 differences; it printed `native rebuilt: 2125dfd7… -> 97049985…`, which independently confirms that FIX-6 is behaviour-neutral.
- Preflight now reports `simulation.py`, `main.py` and `tick.rs` with no enforced pin and with their identity-gate cases.

Not done (owner actions):
- create and push tag `pin-freeze-2026-11` at `c3d752fa`;
- dispatch `identity-gate.yml` to capture the goldens on CI and repeat the determinism runs;
- open a PR so the workflow runs.

## 2026-11-09 — integration 5 (corrections COR-9, COR-10, COR-6a/6b, COR-7)

Merged `sd/COR-7`, which carries the sequential correction chain. Each correction was approved by two independent reviewers and has its own before/after baseline, built on the previous correction's outputs. The reports are in [streamline-and-deepen-baselines/](streamline-and-deepen-baselines/).

| Task | Reviewed head | Baseline (9 cases) | Notes |
|---|---|---|---|
| COR-9 | `d294ff73` | 0 differences | Rust politics hash inputs quoted with Python `repr` rules. In a separate check with quoted names, Rust and Python agreed on 255/300 and 249/300 names before the fix and 300/300 after. Native `59663c67…` |
| COR-10 | `165b58e2` | 76 differences, all in `proc48_hybrid_s42` | The double-counted keep changes flipped 9 gate decisions: 8 temple or trading-house decisions are now allowed and 1 is refused. The first divergence is at turn 33. The other 8 cases are byte-identical. Agents-off runs cannot change (`acc` is `None`) |
| COR-6a, 6b | `677e537a` | 0 differences; 0 of 40 bundles changed in an agents-off batch over seeds 2101–2140 (development measurement, not registered) | Early war returns keep their reconciliation events; soldiers without a roster die only for people actually drained. **COR-6c** (`Army.natural_deaths`) was blocked on the then-enforced `models.py` and is now unblocked by PIN-1 |
| COR-7 | `79aae4be` | 0 differences | Rust step 11 deleted (option B); the enum variant and FFI mapping are kept. It fired 0 times in normal runs; forced runs emitted 197–319 discarded ops with identical outputs. Native `6b4909d7…` |

Gates on the merged head `ace1de11`:
- Fresh native build `d79f483d…`; `check_python_env --expect native` passes; `cargo test --locked` passes (library 782).
- Identity, all 9 cases, against the correction chain's own after-outputs: **399 files, 0 differences**. Against the pre-correction baseline: 76 differences, all in `proc48_hybrid_s42`, as COR-10's report says.
- Oracle lane: 77 chunks; 8,217 passed, 69 skipped, 0 failed.
- Native politics, gp_agendas, war and household-retail tests: 357 passed.
- Identity gate. The Python lane gave 0 differences. The native lane gave 11 differences, all in `g_learning_s42`.
  - Attribution: `g_learning_s42` was run at `sd/COR-9`, `sd/COR-10` and `sd/COR-6`, each with its own native. COR-9 changes nothing, **COR-10 makes the whole change** (3,918 → 3,811 events), COR-6 changes nothing, and the merged head equals the chain.
  - `native_goldens.json` was re-captured for that case only (the other five cases are unchanged). The spec treats re-capture as part of a correction. The provenance note records the attribution.
- Not run: the 200-seed gate, GitHub CI, and a hybrid paired batch for COR-6.

## 2026-11-09 — integration 6 (viewer chain)

Merged `sd/CON-9c`, which carries the sequential viewer chain. Each step was approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Notes |
|---|---|---|
| DEAD-1 | `55e601f2` | Nine legacy components and three test files removed, plus `d3-force` and `@types/d3-force`. The entry chunk is unchanged at 490,463 B |
| DEAD-4 | `e59a14c2` | Dead exports and the `useBundle` `parseBundle` re-export removed (unpinned slice) |
| FIX-8 | `2f733ae6` | `lib/liveMessages.ts` guard module; it is wired into `useLiveConnection.ts` in the pinned slice still to come. Also: `.mjs` lint scope, `esbuild` declared, Playwright an optional peer loaded through `scripts/lib/playwright.mjs` |
| CON-9a | `f143ea3a` | Shared `recordGuards`, `livelihoodRecord` envelope and `downloadText` |
| CON-9b | `04d4dd1d` | `components/systems/` formatters, `SystemSection`, `SystemTable` and `usePaged`. DOM unchanged |
| CON-9c | `e0f9ba87` | AppShell helpers moved to `lib/shellFeed.ts` and `lib/atlasLayout.ts`; `snapshotAtTurn`; four per-render computations memoised; a single validation pass. DOM equivalence gave 0 differences. Perf numbers were measured on a loaded host and are inconclusive, so no speedup is claimed |

Gates on the merged head `a8fc4d8f` (Node 22 in the cloud container):
- `npm ci`, `tsc --noEmit -p tsconfig.app.json`, `npm run lint` and `npm run build` all pass. The existing large-chunk warning remains.
- `npm test -- --maxWorkers=2`: **202 files; 1,919 passed, 2 skipped, 0 failed**.
- `tests/test_native_build_lanes.py` and `tests/test_docs_status.py`: 28 passed.
- Preflight against `33c6f86` (164 paths): only the frozen-snapshot entries, which are expected.
- No Python or Rust change, so identity is unaffected.

Not run:
- Browser QA scripts.
- Node 20.19.0, the floor that CI uses.
- The pinned viewer slice (plan PR 6), which is now unblocked by PIN-1.

## 2026-11-09 — integration 7 (CON-2, CON-14, LAB-1)

Merged two chains. Each task was approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Notes |
|---|---|---|
| CON-2.0, CON-2.1 | `ae761aa1` | `switch_state.py` (`bump_counter`, `lane_active`, `sub_state_getter`, `health_holders`, `SwitchStateMixin` with opt-in `_FILL_DEFAULTS`/`_FILL_PRIVATE`/`_TRANSIENT`/`_BUMP`); `scripts/switch_state_identity.py`; golden pickle corpus `tests/fixtures/state_pickles` (71 classes) dumped from `3e0ef5e9` |
| CON-2.2 | `5c18f8c5` | Shared `lane_active`/`health_holders`; `sub_state_getter` in 36 owners (4 keep their own) |
| CON-2.3 A–D | `2194653e`, `73276663`, `67f8d04b`, `1a50e661` | The unpinned `*_state` classes and their owners moved onto the mixin batch by batch, each with pickle-corpus and switched identity proofs |
| CON-14 | `3ec7b820` | Shared `_shuffle_rows`; `settlement_util.py` for cities and agent_movements; `_controller` kept as the scan form (the probe showed duplicate-name worlds differ) |
| LAB-1a–1f | `1b6edda9` … `4f98aaf7` | 27 detached modules moved to `src/chronicler_lab/` with `sys.modules` shims listed in `SHIMS`; boundary guard in `tests/test_import_compatibility.py`; wheel ships both packages. Per DEC-6, `validation_compare` and `community_admissibility` stay. PR 7 (shim removal) waits for the first tagged release |

Integration fixes by the lead:
- `77aa7696`: `adaptive_livelihoods._bump` uses `bump_counter(state.counters, …)` again. CON-2 batch C made it call `state.bump()`, which broke three `tests/test_timber_orders.py` tests that pass a `SimpleNamespace` state. The CON-14 implementer and reviewer reproduced this on `sd/CON-2.3D`; the batch C reviewer had not run those tests. The new form behaves exactly like the mixin method for this class.
- `f1002e5`: two deleted legacy viewer tests removed from `tests/fixtures/identity/coverage.json`.
- **Correction to integration 6.** The viewer merge was recorded as needing no Python gate, and the oracle lane was not run then. That merge did break `test_identity_coverage_map_names_every_witnessed_path`: PIN-2's coverage map named `SetupLobby.test.tsx` and `components.test.tsx`, which DEAD-1 had deleted. The integration-7 oracle lane found it. From now on the lead runs the oracle lane on every integration.
- Merge conflicts were resolved by addition: the module count is now 471, and DEVELOPMENT.md keeps both the identity-gate and the lab-package sections.

Gates on the merged head `f1002e5`:
- Oracle lane `--jobs 2`: PASS in 327.2 s on a loaded host. 78 chunks; 8,333 passed, 70 skipped, 0 failed.
- `switch_state_identity.py check tests/fixtures/state_pickles`: PASS, 71 classes, 0 differences.
- Import compatibility, timber orders, switch state, cities, agent movements and adaptive livelihoods: 244 passed, 8 skipped.
- Identity, all 9 cases against the post-correction baseline (integration 5): **399 files, 0 differences**.
- Identity gate: Python lane 53 files, 0 differences; native lane 133 files, 0 differences.
- Preflight: no source pin. It reports the corpus pickles' own digests and literal digests of four relocated lab modules; the tests that check those digests now read the new paths and pass.

Not run: the native Python shards, the 200-seed gate, and GitHub CI.

## 2026-11-09 — integration 8 (viewer pinned slice)

Merged `sd/VIEW-PR6` (reviewed head `4fd8de6f`). Two independent reviewers, one for scope and one for contracts, approved it with no blocker or major findings. It is viewer plan PR 6, the slice that touches formerly pinned files (FIX-8, DEAD-4 and CON-9):
- `useLiveConnection.ts` now validates running `init` and `turn` messages with `parseLiveInit` and `parseLiveTurn`. A malformed message is dropped with a warning instead of replacing the bundle or appending a turn-0 row. This is the one intended behaviour change, and the new tests fail against the old hook.
- Dead and internal-only exports removed from formerly pinned libraries.
- `exactSnapshot` now delegates to `snapshotAtTurn`.
- `downloadText` gained an optional `revokeAfterMs`; both callers pass 0, so their revoke timing is unchanged.
- Shared record guards are used where the bodies are identical.
- The entry chunk grew by about 1.5 KB, because the live hook now imports the guard module.

Gates on the merged head `065055ec`:
- `npm ci`, `tsc`, lint and build pass.
- `npm test -- --maxWorkers=2`: **202 files; 1,922 passed, 2 skipped, 0 failed**.
- `test_native_build_lanes` and `test_docs_status`: 28 passed.
- Oracle lane `--jobs 2`: PASS in 168.9 s. 78 chunks; 8,333 passed, 70 skipped, 0 failed.

Not run: browser QA and equivalence scripts, Node 20.19.0, and GitHub CI.

## 2026-11-09 — integration 9 (Rust and cross-language lane)

Merged `sd/CON-7b` as `28b1a04`. This one chain carries ten tasks, each approved by independent review with no blocker or major findings. The corrections had two reviewers each, one for scope and one for contracts; CON-6ab also had two.

| Task | Reviewed head | Notes |
|---|---|---|
| COR-8a | `584acd06` | Explicit `hills`/`river` ecology rows equal to plains, plus a Python↔Rust `TERRAIN_CAPS` parity class in `tests/test_ecology.py`. The plan's `test_ecology_parity.py` skips without native, so the test was put where the offline lane runs it |
| COR-8b | `9ef19e11` | `DEPRECATED_UNREAD_KEYS` warns once per accepted-but-unread tuning key; values still load; a reader check fails on new dead keys |
| COR-8c | `a4ae368b` | Test only: Rust `TITHE_RATE`/`TITHE_FOOD_GATE` checked against Python |
| DEAD-5b | `430deecd` | `#[cfg(test)]` on `Terrain::from_u8` and `is_adjacent_to`; the dead `old_occ` read in `tick.rs` removed |
| CON-5a | `5163b49f` | `tests/rust_source_constants.py` reader; parity rows for every constant mirror in the spec table; `test_ffi_constants.py` joins oracle chunk core |
| CON-7a | `a7a7921f` | `chronicler.economy_oracle` re-export module; 9 test modules and 3 scripts migrated |
| CON-5b | `c8abed1c` | One supply-floor and one tithe-gate literal per language; the tautological H-2 tithe tests replaced by an oracle-driven test |
| CON-6ab | `2a75dad9` | Generic Arrow column reader (`ffi/columns.rs`) replaces 14 macros; ffi tests moved to `ffi/tests.rs`. FFI column error texts are normalised (text only, no test asserts them); the PR must say so |
| CON-6cd | `cf49965b` | `derive_region_agent_counts` and `derive_civ_fiscal_inputs` move to `economy.rs`; `EconomyExtras`; the four `_with_*` wrappers removed |
| CON-7b | `1f76767c` | `compute_economy` and its oracle-only helpers live in `economy_oracle.py`; `chronicler.economy` keeps a lazy `__getattr__` shim. `compute_production` and `derive_farmer_income_modifier` stay in `economy.py` until DEAD-5a; the oracle's re-export of them must go when DEAD-5a merges |

Correction baselines are in [COR-8](streamline-and-deepen-baselines/COR-8.md): 0 differences for all three parts.

Lead fix `b07777d9`: CON-6cd had renamed `tick_economy`'s unused third parameter to `_season_id`. PyO3 exposes Rust parameter names as Python keywords, so the keyword `season_id=` would have stopped working. That is a compatibility break the plan did not intend, and the implementer had raised it as an owner question. The parameter keeps its name `season_id`, and `let _ = season_id;` marks it unused. `cargo check` reports 0 warnings.

Gates on the merged head `b07777d9`:
- `cargo test --locked`: all suites pass, including 788 in the main library suite.
- Fresh native build (`d2956542…`): `check_python_env.py --expect native` PASS; the compiled classes are AgentSimulator, EcologySimulator and PoliticsSimulator.
- Identity, all 9 cases against the post-correction baseline (integration 5): **399 files, 0 differences**. Against the pre-correction base: 76 differences, all in `proc48_hybrid_s42` (COR-10, expected).
- Oracle lane `--jobs 2`: PASS in 163.9 s. 78 chunks; 8,354 passed, 70 skipped, 0 failed.
- Native focused tests (`test_ecology_parity`, `test_economy`, `test_tuning`, `test_ffi_constants`, `test_politics_hash_parity`): 108 passed.
- Identity gate: Python lane 53 files, 0 differences. Native lane 133 files, 0 differences. The receipt check reports the rebuilt native (`d79f483d…` → `d2956542…`) with identical outputs.

New board item **FIX-14**, from the COR-8b work. Any `--tuning` file, even one that sets a key to its default, makes `off_s42` diverge from a run without `--tuning`. This predates COR-8. The first step is a diagnosis; any fix is a correction and needs a baseline report.

Not run: the native Python shards in full, the 200-seed gate, and GitHub CI.
