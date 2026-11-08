# RNG Hygiene, Live Governance Default and Defaults Registry — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** `system_rng` helper (refactor), one documented RNG correction, one defaults registry used by CLI and live, governance default for live worlds, Rust repr parity.
**Architecture:** `utils.system_rng`; new `src/chronicler/switch_defaults.py`; corrections isolated in their own PRs with baselines.
**Tech stack:** Python 3.13 (`.venv/bin/python`), pytest, Rust/PyO3 (`chronicler-agents`).
**Prerequisites:** DEC-3 sign-off before PR 2 merges. PR 4 and 5 need PIN-1 (D1 option A) or a reviewed inverse layer (`scripts/testing/reviewed_main_witness.py`) for `main.py`, `live.py`, `simulation.py`, `agent_bridge.py`, `economy.py`, `scholarship.py`, `what_if.py`, `batch_manifest.py`. DEC-2 settles whether governance stays default-on before PR 5.

Baseline preparation (once, before PR 2): from fetched `main`, run
`.venv/bin/python scripts/turn_speed_identity.py run $SCRATCH/base` (9 cases, `PYTHONHASHSEED=0`). Keep the directory; every "compare" below is against it.

## File map

| File | Change | Pin |
|---|---|---|
| `src/chronicler/utils.py` | add `system_rng` | none |
| `war/common.py`, `diplomacy.py`, `maritime.py`, `guilds.py`, `cities.py`, `nomads.py`, `agent_movements.py`, `gp_agendas.py`, `epidemiology.py` | helpers become wrappers | none |
| `scholarship.py` | same wrapper | enforced (PR 4) |
| `action_engine.py` | EXPAND stream | none |
| `war_requisition.py` | fixed food order | none |
| `emergence.py`, `religion.py`, `artifacts.py` | namespaced seeds | none |
| `simulation.py`, `agent_bridge.py` | namespaced seeds | enforced (PR 4) |
| `economy.py` | `FOOD_GOODS_ORDER`, fsum | enforced (PR 4) |
| `what_if.py` | relax `require_hash_seed` | enforced (PR 4) |
| `switch_defaults.py` (new), `main.py`, `live.py`, `feature_catalog.py` | registry | `main`, `live` enforced (PR 5) |
| `chronicler-agents/src/politics.rs` | `py_repr_str` | none |
| tests | see tasks | |

## PR 1: `system_rng` refactor (COR-1 prep; behaviour-preserving)

### Task COR-1a: helper and wrappers
- [ ] Step 1: Preflight `.venv/bin/python scripts/refactor_preflight.py src/chronicler/utils.py src/chronicler/war/common.py src/chronicler/diplomacy.py src/chronicler/maritime.py src/chronicler/guilds.py src/chronicler/cities.py src/chronicler/nomads.py src/chronicler/agent_movements.py src/chronicler/gp_agendas.py src/chronicler/epidemiology.py`; expect references only, no ENFORCED line.
- [ ] Step 2: In `utils.py` after `stable_hash_int` (`:38-41`) add
  ```python
  def system_rng(namespace: str, world, *parts, system: str | None = None) -> random.Random:
      head = (system, namespace) if system else (namespace,)
      return random.Random(stable_hash_int(*head, world.seed, world.turn, *parts))
  ```
  (`import random` at module top if absent).
- [ ] Step 3: Rewrite each helper body to a single call, keeping names/signatures: `war_rng` (`war/common.py:88`) `system_rng(namespace, ctx.world, *parts, system="war")`; `diplomacy._rng` (`:248`), `maritime._rng` (`:412`), `guilds._rng` (`:171`), `cities._rng` (`:241`), `nomads._rng` (`:243`), `agent_movements._rng` (`:263`) with `system="<module>"`; `gp_agendas._rng(label, ...)` (`:241`) `system_rng(f"gp_agenda.{label}", world, *parts)`; `epidemiology._draw` (`:299`) `system_rng(namespace, world, *parts).random()`. Leave `scholarship._rng` (pinned) for PR 4.
- [ ] Step 4: Add `tests/test_system_rng.py`: for each wrapper, assert the first five `random()` values equal `random.Random(stable_hash_int(<legacy tuple>))` computed inline in the test, with a fake world (`seed`, `turn`) and parts containing a str, int and tuple; assert `system_rng("a", w) != system_rng("b", w)` streams; assert `gp_agendas` and `epidemiology` shapes separately.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_system_rng.py tests/test_diplomacy.py tests/test_maritime.py tests/test_guilds.py tests/test_cities.py tests/test_nomads.py tests/test_agent_movements.py tests/test_gp_agendas.py tests/test_epidemiology.py tests/test_war_requisition.py -q` passes; run `turn_speed_identity.py run $SCRATCH/pr1` then `compare $SCRATCH/base $SCRATCH/pr1` must report all 9 cases identical.
- [ ] Step 6: Commit `refactor: add system_rng and route unpinned _rng helpers through it` (with the attribution trailer). No ledger entry beyond a one-line refactor note.

## PR 2: RNG hygiene correction, unpinned files (COR-1; DEC-3 required)

### Task COR-1b: food debit order and sweep test
- [ ] Step 1: In `war_requisition.py` add near the top `_FOOD_DEBIT_ORDER = ("salt", "grain", "fish", "exotic", "botanicals")` (the `PYTHONHASHSEED=0` order on Python 3.13, lead-measured 2026-11-08 without `-I`; re-derive it first with `PYTHONHASHSEED=0 .venv/bin/python -c "import sys; sys.path.insert(0,'src'); from chronicler.economy import FOOD_GOODS; print(tuple(FOOD_GOODS))"` and stop if it differs). Add `tests/test_hash_seed_sweep.py::test_food_order_matches_seed0` which runs a `PYTHONHASHSEED=0` subprocess (no `-I`) and asserts `tuple(FOOD_GOODS) == _FOOD_DEBIT_ORDER` and change `:183` to `for good in _FOOD_DEBIT_ORDER:`; also use it in `:71` fsum.
- [ ] Step 2: `tests/test_war_requisition.py`: add `assert set(_FOOD_DEBIT_ORDER) == FOOD_GOODS`.
- [ ] Step 3: Write the new `tests/test_hash_seed_sweep.py`. It starts child processes, so it belongs to the native/subprocess lane: list it in the shard manifest, not in an oracle chunk, because the oracle guard blocks child processes.
  - **Child processes.** For seeds `"0","1","2","3"`, run `subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, env=child_env(seed), capture_output=True, text=True, timeout=120, check=True)`.
    - **Never pass `-I` or `-E`.** Both make the child ignore `PYTHONHASHSEED` and `PYTHONPATH`. This is the mistake recorded in the synthesis errata (section 8): `python -I` with `PYTHONHASHSEED=0` reports `sys.flags.ignore_environment == 1` and a random `hash`.
    - `child_env(seed)` keeps the platform variables the interpreter needs, as `run_python_oracle_checks.py` does (`PATH`, `SYSTEMROOT`, `WINDIR`, `TEMP`, `TMP`, `LANG`, `LC_ALL`). It adds `PYTHONHASHSEED=seed` and an absolute `PYTHONPATH=str(ROOT / "src")`, and passes nothing else.
  - **Self-checks.** SCRIPT first prints a JSON header with `sys.flags.ignore_environment`, `hash("salt")` and `chronicler.__file__`. The test asserts:
    - `ignore_environment == 0`;
    - the `hash("salt")` values of seeds 0 to 3 are pairwise distinct, so the seeds took effect;
    - `Path(chronicler.__file__).resolve().is_relative_to(ROOT / "src")`, so the child imported this checkout and not an installed editable package elsewhere.
  - **Food debit.** SCRIPT then builds the mixed food-stock region (reuse the helper in `tests/test_war_requisition.py`), runs `_withdraw`, and prints `json.dumps(stockpile, sort_keys=True)`.
    - **Independence:** the four outputs are equal.
    - **Baseline identity:** the seed-0 output equals `SEED0_BEFORE`, a literal captured from the pre-fix code under `PYTHONHASHSEED=0`. It proves the fix keeps every seed-0 baseline.
  - **Second script.** Add a second script calling `consume_from_stockpile` on a mixed stockpile, with the same self-checks. Mark it `xfail(strict=True)` until PR 4.
- [ ] Step 4: Verify both directions.
  - **Before the fix,** in a scratch worktree of `main`, the independence assertion must fail for at least one of seeds 1 to 3, while the seed-0 output equals `SEED0_BEFORE` (that is where `SEED0_BEFORE` comes from).
  - **After the fix,** all four outputs are equal and the seed-0 output still equals `SEED0_BEFORE`.
  - **Without either,** the test does not prove independence and baseline identity together.

### Task COR-1c: EXPAND and additive seeds
- [ ] Step 1: `action_engine.py:198` -> `rng = system_rng("expand", world, civ.name)`; remove the unused `civ_idx` only if no other use (`:197` is read by later code? check with `rg civ_idx action_engine.py` in that function).
- [ ] Step 2: `emergence.py:226,257,396,514,603,650` -> `system_rng("<ns>", world)` with namespaces `black_swan`, `emergence_a`... name each by the function (`rg -n "def " emergence.py` around each line); each must be unique; they take `seed`/`world`, so use `stable_hash_int("<ns>", seed, world.turn)` where only `seed` is in scope. `religion.py:138` -> `random.Random(stable_hash_int("religion_doctrine", seed, civ_idx))`. `artifacts.select_cultural_artifact_type(civ, seed)` (`:657`) keeps its signature; callers pass a hashed int (PR 4 changes the caller in `simulation.py`).
- [ ] Step 3: Add to `tests/test_system_rng.py` a namespace-uniqueness test: parse the sources with `ast`, collect first-arg literals of every `system_rng`/`stable_hash_int` call under `src/chronicler`, assert no namespace string is shared by different call sites unless listed in an allow-list.
- [ ] Step 4: Update `tests/test_action_engine.py` with `test_expand_stream_depends_on_seed`: two worlds equal except `seed`, many unclaimed regions, assert targets differ for some turn in 0..20.
- [ ] Step 5: Verify focused: `.venv/bin/python -m pytest tests/test_action_engine.py tests/test_emergence.py tests/test_religion.py tests/test_artifacts.py tests/test_hash_seed_sweep.py -q`; fix tests that pin old seeds by recomputing expected values (never edit pinned hashes).
- [ ] Step 6: Baseline: `turn_speed_identity.py run $SCRATCH/pr2` then `compare $SCRATCH/base $SCRATCH/pr2`. Expect every case to differ (record the printed changed-field lists in the ledger). Also confirm PR 2 stage "food order only" (commit COR-1b alone) compares identical to base; run compare at that commit first. Then `scripts/run_python_oracle_checks.py` (new tests into a chunk with headroom, no limit change). Run the documented 200-seed before/after gate; do not call the correction qualified until it has run.
- [ ] Step 7: Ledger: CONTINUATION entry "RNG hygiene correction (unpinned half)": what changed (EXPAND, emergence, religion streams; war food order), why (seed independence, hash-seed independence), baseline dirs and compare output, DEC-3 reference, what did not change (hash-0 food order; pinned files pending). Commit `fix: seed EXPAND and namespace additive RNG seeds; fix food debit order`. PR body lists the ten affected stream sites.

## PR 3: Rust stable_hash parity (COR-9; why: audit scout 22 finding 4, no ID existed)
- [ ] Step 1: Preflight `scripts/refactor_preflight.py chronicler-agents/src/politics.rs` (expect no enforced pin).
- [ ] Step 2: In `politics.rs` near `:727` add `fn py_repr_str(s: &str) -> String` (CPython rules: quote `'` unless text contains `'` and not `"`; escape `\\`, the quote, `\n`, `\r`, `\t`, bytes < 0x20 and 0x7f as `\xNN`; leave other chars as is). Replace `'{}'` at `:1377`, `:1835`, `:2281`, `:2409` (view each `format!` first) with `{}` fed by `py_repr_str(name)`. Do not touch the LE seed at `:1147` (matches `intelligence.py:208`).
- [ ] Step 3: Generate constants: `.venv/bin/python -c` printing `stable_hash_int('secession', 7, 3, name)` for names `["Aldor","Ka'lo","A\\B","Zoë","He said \"hi\"","tab\there"]`; paste as a table in a new Rust test and in `tests/test_politics_hash_parity.py` (which recomputes with `stable_hash_int` and compares to the same literal table, so both sides are pinned).
- [ ] Step 4: Verify: `cd chronicler-agents && cargo test stable_hash` and `cargo test politics`; `.venv/bin/python -m pytest tests/test_politics_hash_parity.py -q`. Build a fresh extension into the separate venv `scripts/cloud_setup.sh` describes and run `tests/test_politics*.py` native tests; run a native `turn_speed_identity` hybrid case, expected identical (no apostrophe names in generated worlds; verify with `rg "'" ` over `src/chronicler/world_gen.py` name tables).
- [ ] Step 5: Ledger entry (correction for names with quotes/backslashes only). Commit `fix(rust): quote politics hash inputs with Python repr rules`.

## PR 4: RNG correction, enforced files (COR-1; after PIN-1)
- [ ] Step 1: Preflight `simulation.py agent_bridge.py economy.py scholarship.py what_if.py`; confirm PIN-1 landed (no ENFORCED lines) or write the reviewed inverse layer; never rewrite a hash.
- [ ] Step 2: `simulation.py:1066-1067` -> `_art_rng = system_rng("artifact_gate", world, civ_idx)` and `select_cultural_artifact_type(civ, seed=stable_hash_int("artifact_type", world.seed, world.turn, civ_idx))`; `:2005` -> `system_rng("env_hazard", world)` (check `seed` vs `world.seed`: `rg -n "seed" simulation.py` near `:1990`). `agent_bridge.py:2244` -> `system_rng("agent_name", world, agent_id)`; `:2275` -> `system_rng("agent_mule", world, gp.agent_id)`.
- [ ] Step 3: `economy.py`: add `FOOD_GOODS_ORDER = ("salt","grain","fish","exotic","botanicals")` (same derivation and stop rule as PR 2) beside `:51`; use it at `:167,405,465,479,483`; `clamp_floor_loss` (`:442-450`) accumulate in a list and `math.fsum`. Remove the xfail from the `consume_from_stockpile` sweep test.
- [ ] Step 4: `scholarship._rng` (`:165`) -> wrapper (identical output; covered by `tests/test_scholarship.py`).
- [ ] Step 5: Set-iteration audit: write scratch `$SCRATCH/set_audit.py` (AST: `for` over a Name resolving to a module-level `set`/`frozenset`/`{..}` literal, calls to `sum/min/max/next/list/rng.choice` on such names, `next(iter(`), run over `src/chronicler`, and list each site with a verdict (order-safe: membership, per-element independent update, sorted, single element; order-sensitive: float accumulation, draw order, first-wins). Record the list in the PR body. Seed sites already checked: `war/occupation.py:45` (independent), `grain_reserves.py:568`, `grain_convoys.py:757`, `attribution_records.py:420,442` (already `sorted`), `household_retail.py:1994-2002`, `techniques.py:780`, `agent_bridge.py:2154` (scout 31).
- [ ] Step 6: Relax `what_if.require_hash_seed` (`:224-228`) only if step 5 has no open order-sensitive site and the sweep passes: drop the `PYTHONHASHSEED != "0"` clause, keep the POSIX check, and spawn arms with `env["PYTHONHASHSEED"]="0"` (find the spawn at `rg -n "Popen|subprocess" what_if.py`). Update `tests/test_what_if.py:221` accordingly. If any doubt remains, skip this step and leave a ledger note.
- [ ] Step 7: Verify: sweep test (seeds 0..3) green including `consume_from_stockpile`; `tests/test_economy_m43a.py tests/test_economy_m43b.py tests/test_scholarship.py tests/test_what_if*.py tests/test_artifacts.py -q`; `turn_speed_identity` compare against PR 2 output, expect only additive-seed fields and (if the clamp fires) `clamp_floor_loss`; native: build fresh extension, run `hybrid_*` cases, then the 200-seed gate.
- [ ] Step 8: Ledger + commit `fix: namespace remaining additive seeds; order food goods; relax hash-seed guard`.

## PR 5: Defaults registry refactor (CON-1; after PIN-1)

### Task CON-1: registry and adoption
- [ ] Step 1: Preflight `main.py live.py feature_catalog.py` (`main`/`live` enforced: PIN-1 first). Capture the live pre-image: scratch script calls `live._live_world(args, params)` for an arg matrix (no flags; each `--no-X`; `--agents hybrid`; `--finance` only; `--no-contact-ledger` with `--epidemiology`; `--fisheries`/`--no-mutual-aid`) and writes `world.model_dump_json()` per case to `$SCRATCH/live_pre/`. Likewise capture CLI worlds from `_configure_run`.
- [ ] Step 2: Create `src/chronicler/switch_defaults.py` with `SwitchDefault` dataclass and `SWITCHES` tuple in main's order (campaigns, mutual_aid, fisheries, governance(`live_exempt=True` for this PR), contact_ledger, epidemiology(requires ledger), finance, diplomacy, techniques, maritime, gp_agendas, nomads, cities, agent_movements, guilds, scholarship, grain_reserves, community_anchoring, domestic_credit(requires finance), historiography, languages). Each entry names module path and setter; `default` is read lazily from the module's `DEFAULT_ENABLED_FOR_NEW_WORLDS`. Provide `resolve`, `apply_switches(world, args, *, fresh_world, agent_mode, names=None, live=False)`, `default(name)`, `switch_state(world)` (name -> bool via `enabled`).
- [ ] Step 3: `main._configure_run`: replace the default-and-setter blocks (`:1612-1649`, `:1650-1884`) by three `apply_switches(... names=...)` slices placed where the blocks were, leaving academy services, grain storage, shipments, mobility, ablation check and explicit-on `ValueError`s untouched (`:1769-1836`, `:1789-1792`, `:1838-1841`, `:1858-1862`).
- [ ] Step 4: `live._live_world` `:1310-1438` -> `apply_switches(world, args, fresh_world=True, agent_mode=..., live=True)`; keep `capacity_aware_refugees` line and the `_apply_live_prerequisites` call. Preserve live gating (`domestic_credit and finance on`, `epidemiology and ledger on`).
- [ ] Step 5: `feature_catalog.py:332-352` -> `default(name)`. Defer the `batch_manifest` exclusion-tuple derivation (enforced; separate follow-up unless PIN-1 landed): derive from `LIVELIHOODS_ARG_KEYS`, `EXPANSION_SWITCHES` and a short explicit list, and assert in a test that the derived set equals the old tuple.
- [ ] Step 6: Replace `tests/test_fisheries_mutual_aid_promotion.py:108` source-grep with: `_live_world` yields `fishery_experiment.enabled` and `mutual_aid_enabled` True by default and False with `--no-...`.
- [ ] Step 7: Verify: scratch script re-captures live and CLI worlds; `diff -r` of dumps shows no difference (live governance exempt so still None). `tests/test_switch_defaults.py`: registry order equals main's, every `DEFAULT_ENABLED_FOR_NEW_WORLDS = True` module appears (grep-based), CLI and live `switch_state` agree except `live_exempt`. `pytest tests/test_live.py tests/test_live_integration.py tests/test_governance_runtime.py tests/test_feature_catalog.py tests/test_feature_matrix.py tests/test_fisheries_mutual_aid_promotion.py -q`; `turn_speed_identity` compare vs the PR 4 output: identical. `scripts/run_python_oracle_checks.py` passes.
- [ ] Step 8: Commit `refactor: one new-world switch defaults registry for CLI and live`.

## PR 6: Live governance default (COR-2; correction)
- [ ] Step 1: Remove `live_exempt` from the governance entry (one-line diff); delete the field if unused.
- [ ] Step 2: Tests: `test_switch_defaults.py` parity now has no exemptions; `tests/test_live.py`: `_live_world` with no flag gives `world.governance is not None`, with `--no-governance` gives None; resume path (`resume_state`) leaves a saved None unchanged.
- [ ] Step 3: Baseline: live has no `turn_speed_identity` case, so run a scripted two-session comparison: same seed, 60 turns, `--agents off` and `hybrid`, through `_live_world` + `execute_run` before (PR 5 tree) and after; keep `chronicle_bundle.json` diffs and the event-type counts (governance events appear). Plus the CLI-vs-live equality: a live world and a fresh CLI world of the same seed now have identical `switch_state`.
- [ ] Step 4: Ledger: CONTINUATION entry "Live worlds follow the CLI governance default" with baseline artefacts, DEC-2 reference, and note that resumed live sessions are unaffected. Commit `fix(live): new live worlds enable governance like the CLI`.

## Done when
- [ ] `system_rng` exists; ten helpers delegate to it; `turn_speed_identity` identical after PR 1 and PR 5.
- [ ] PR 2 and PR 4 each have a ledger entry with before/after compare output and a 200-seed gate result (or an explicit "not run").
- [ ] Sweep test (seeds 0..3) green; set-iteration audit list is in PR 4; `require_hash_seed` relaxed only if the audit is clean.
- [ ] Registry used by `main` and `live`; live and CLI new-world switch states equal; governance on for new live worlds; resumed worlds untouched.
- [ ] Rust/Python hash digests pinned both sides for quoted names.
- [ ] No pinned hash rewritten; no CLI flag removed; DEC-2 and DEC-3 recorded in the ledger.
