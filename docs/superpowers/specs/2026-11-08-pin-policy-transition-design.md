# Pin-policy transition and identity-gate coverage — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** DEC-1 (decision record), PIN-1, PIN-2
> **Depends on:** DEC-1 signed by the owner (PIN-1, PIN-2 are written for option A)
> **Feeds:** every task the audit marks "pinned" (DEAD-5, CON-1..CON-4, CON-6, CON-10, FIX-1..FIX-3, FIX-7, COR-*), Wave 4/5 refactors
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (D1) + scouts 25 (e), 27 (finding 9)

## 1. Goal and scope
Stop the byte-level source pins from taxing every edit, without losing the history they prove and without losing behavioural protection. Changes: the witness tests read **frozen copies** of the pinned sources instead of the working tree (PIN-1); a committed behavioural gate replaces the protection the pins gave (PIN-2). Not changed: workflow byte copies, native shard manifest, oracle-chunk ownership, `reference_baselines/`, any fixture's bytes, any simulation outcome.

## 2. Current behaviour (verified)
- 54 fixtures `tests/fixtures/*inverse*.json` name **87 paths** (my count): 38 `src/chronicler` (incl. `transport_contract.json`), 14 Rust, 26 viewer, 7 scripts, and 2 test files (`tests/test_batch_manifest.py`, `tests/test_crisis_forecast_misleading_example.py`). 13 witness scripts in `scripts/testing/`.
- Mechanism: a test reads `ROOT/path` bytes, projects them back through patches (`scripts/testing/academy_candidate_witness.py:15-35`; `livelihoods_sprint_witness.py:36-57`, 41 layers, `LAYERS` at :24) and compares to the base hash. The newest layer's `current_sha256` therefore equals the working file, so any edit fails.
- Readers of working-tree source: 9 `tests/test_*_witness.py` (15 tests) plus 5 mixed behavioural files: `test_grain_release_policy.py:217`, `test_regional_population.py:243`, `test_public_grain_shipments.py:584`, `test_health_care_policy.py:1005,1057` (also direct digests of `health_care.py`, `health_care_state.py`, `health_care.rs`, `health_care_observation.rs` at :1017-1027), `test_practice_observer_runner.py:444,453,518` (`Path(M.__file__)`). About 31 `ROOT/path` read sites.
- **Audit correction:** scout 25 says `refactor_preflight.py main.py` reports no witness. False: it reports 9 enforced witnesses (run at c84d11e); `livelihoods_r3` matches the current file.
- Recorded `base`/`head`/`parent` commits are **not** a verification input: no test calls git. 27 of 64 recorded ids are absent from this clone (878 commits, shallow). They are unreliable anchors (candidate heads, possibly squashed).
- CI: all 7 `actions/checkout@v4` in `.github/workflows/tests.yml` (e.g. :21) use the default depth 1. The oracle guard blocks `subprocess.Popen` (`scripts/testing/python_oracle_guard.py:51`), so `git show` is impossible in the main offline lane.
- `scripts/turn_speed_identity.py:41-56`: 9 cases (seeds 42/7/1234, 20-300 turns, off/hybrid, scaled 18.8k/43.7k agents). It is a **base-vs-new** comparison of two checkouts (`compare`, :314); no committed golden, no CI use. Cases only use default switches.
- Existing goldens: `tests/test_performance_equivalence.py:227` (3 workloads, 20-60 turns, `agents="off"`, **all 17 default-on systems forced off**, `scripts/benchmark_headless.py:94-115`); `validation_parity/goldens.json`; `test_checkpoint_replay.py` (agents off). Nothing pins default-switch or hybrid output.
- Default-off, so absent from all 9 cases: grain reserves/storage/forecasts/shipments, transaction receipts, scholarship, academy services, household mobility, community anchoring, domestic credit (`DEFAULT_ENABLED_FOR_NEW_WORLDS` greps).

## 3. Design
### DEC-1 — owner decision record
| | A freeze (recommended) | B status quo | C scoped retirement |
|---|---|---|---|
| Mechanism | witness tests verify `tests/fixtures/frozen_pin_sources/<path>.txt` | add inverse layer per edit | A's mechanism, manifest-limited to declared files |
| Per-edit cost | 0 | see below | 0 for listed files; one owner PR per scope |
| History kept | full chain, all mutation tests | full | full for all |
| Working tree guarded by | identity gate (PIN-2) | byte pin | byte pin outside scope |
| Repo cost | +2.75 MB (0.5 MB packed) | +20-60 KB/layer | same as A for scope |

Option B procedure per touched pinned file: edit; `python scripts/testing/livelihoods_layer_tool.py NAME PARENT_REV PATH...` (needs git history); read every hunk; append NAME to `LAYERS` (`livelihoods_sprint_witness.py:24`); for `main.py`, check `reviewed_main_witness.py` chains; run the witness tests. Cost grows with edit size (hunks carry 3+ context lines, each `new` unique), doubles review volume, and serialises PRs: two PRs on one file both append a newest `current_sha256` and conflict. Option C shares A's code (`frozen_source()` consults a manifest) but leaves two policies; each wave needs an owner-approved scope edit and unlisted files stay pinned forever.
**Recommendation: A.** The owner signs: (1) option A; (2) byte-level review provenance for ~91 files is no longer machine-enforced, replaced by the PIN-2 gate as required check; (3) +2.75 MB of frozen copies, never edited; (4) the freeze base is the last `main` commit before PIN-1 merges; (5) AGENTS.md/DEVELOPMENT.md wording (plan PR 3); (6) the rule "never rewrite a pinned hash" now applies to fixtures and frozen copies.

### PIN-1 — how to keep witnesses verifiable
Evaluation (question 1):
- **Re-point to `git show <commit>`**: strongest in theory, but depth-1 CI, shallow cloud sessions and the subprocess guard break it; recorded commits are partly absent; the fallback is skip, i.e. no guarantee. Rejected as the verifier.
- **`historical` marker**: tests still read the working tree, so they fail on first edit, or are never run. Guarantee: none. Rejected.
- **Archive (delete tests, keep fixtures)**: zero cost, zero guarantee; same as `scripts/archive`. Fallback only if the owner refuses 2.75 MB.
- **Frozen terminal snapshot (chosen)**: commit the exact bytes the newest layers terminate at. The unchanged chain code then verifies every layer and every mutation-refusal assertion offline, in any clone depth, inside the oracle guard. Lost: only "working tree equals the terminal bytes", the pin being released.
Shape: `scripts/testing/frozen_sources.py` (`frozen_text(rel)`, `frozen_bytes(rel)`, manifest) and `tests/fixtures/frozen_pin_sources/MANIFEST.json` `{freeze_commit, files:{path: sha256}}`; copies stored as `<path>.txt`; `.gitattributes` gains `tests/fixtures/frozen_pin_sources/** -text` (precedent: `reference_baselines/** -text`). The 87 paths plus the 4 digest-pinned `health_care*` files (91). Witness modules gain no logic; only their callers swap `ROOT/path` for `frozen_*`. Provenance of the copies is checked once by `scripts/testing/freeze_pin_sources.py --verify` (needs full clone; compares `git show freeze_commit:path` to the copy and to the newest layer digests) and the commit is tagged `pin-freeze-2026-11` so it stays reachable. Integrity in the normal lane: a test in `tests/test_refactor_preflight.py` (already in an oracle chunk, so no new module or shard entry) asserts each copy's sha256 equals MANIFEST.

What each enforced pin protects today (question 2): (a) review provenance (every change ships a human-read literal diff); (b) change detection (any drift forces re-qualification); (c) a few embedded invariants: `test_practice_observer_runner` proves default `main` AST equals the qualified parent plus reviewed optional routing; `test_grain_release_policy` proves the opt-in policy is the only change. (a) is replaced by ordinary PR review plus the ledger; (b) and (c) need behaviour checks (PIN-2): default-path output identity.

### PIN-2 — identity gate
Extend `scripts/turn_speed_identity.py` (not a new tool):
- `digest OUT_DIR GOLDEN.json`: per case, sha256 of every file's canonical content (reuse `cities_identity._content`, `scripts/cities_identity.py:48`: bundle decoded, `generated_at` dropped); `check OUT_DIR GOLDEN.json` prints differing files. `compare` stays for two-checkout runs.
- Goldens `tests/fixtures/identity/{python,native}_goldens.json`, each recording interpreter, platform, native wheel identity; captured by a workflow run on the CI runner, never a laptop (the performance fixtures record `python 3.13.17 Linux`).
- **The native hash is provenance, not an equality condition** (review 2026-11-08). Each run records its extension's SHA-256 and the source digest it was built from. The gate checks that the loaded extension matches its own build receipt and source. It then judges identity by output digests only, within a compatibility class (Python minor version, OS and architecture, Rust channel). A candidate whose binary differs from the golden's passes when every output digest matches. Requiring binary equality would replace the source-byte pin with a binary-byte pin and block the native refactors this transition is meant to permit.
- Separate workflow `.github/workflows/identity-gate.yml` (PR on pinned-path filters, `workflow_dispatch`, weekly). Not `tests.yml`: its job set is asserted (`tests/test_native_build_lanes.py:226`).
- Coverage map `tests/fixtures/identity/coverage.json` (path -> case names or `"tests"`/`"none"`); `refactor_preflight.py` prints it per path.

New cases (all `--simulate-only`, `PYTHONHASHSEED=0`, `RAYON_NUM_THREADS=1`; turn counts to be trimmed after timing, unverified):
| case | args | covers |
|---|---|---|
| `g_off_s42` | `--seed 42 --turns 120 --agents off` | simulation, models, economy, ecology.py, finance, tuning, turn_artifacts, main (default-on systems) |
| `g_off_proc_s7` | `--seed 7 --turns 100 --regions 48 --civs 10 --agents off` | same on a wide map |
| `g_hybrid_s42` | existing `hybrid_s42` trimmed to 100 turns, `--validation-sidecar` | agent_bridge, sidecar, tick/pool/region/household/merchant/economy/ffi/schema/lib/batch.rs |
| `g_grain_s7` | `--seed 7 --turns 120 --agents hybrid --grain-reserves --grain-storage --grain-storage-policy maintain --grain-storage-work-budget 1 --public-grain-shipments --harvest-forecasts --transaction-receipts` | grain_reserves(+state), grain_storage(+state), harvest_forecasts(+state), public_grain_shipments(+state), public_purchase_receipts, transaction_receipts(+state, .rs), food_accounting |
| `g_learning_s42` | `--seed 42 --turns 120 --regions 24 --civs 6 --agents hybrid --scholarship --academy-services` | scholarship(+state), learning_services(+state), teaching_work.rs |
| `g_mobility_s1234` | `--seed 1234 --turns 100 --agents hybrid --household-mobility-liquid-requirement 25 --community-anchoring --capacity-aware-refugees` | household_mobility_state, regional_population, household.rs |
| `g_scaled_s42` | existing `scaled22k_s42` | batch.rs/large pools |
| `g_batch_off` | `--batch 3 --seed 100 --turns 40 --agents off` | batch_manifest.py (paths normalised as `tests/test_validation_parity.py` does; unverified) |
Off cases run in the python lane (native absent) and again with native for `ecology.rs`/`ffi/ecology_sim.rs` (off mode uses `EcologySimulator`, `main.py:341-354`). Resume/`run_checkpoint.py`: `scripts/checkpoint_identity.py` cases (`hybrid_s42_long`, `proc48_hybrid_s42_scholarship`, `off_s42_long`) run in the weekly job. Remaining modules stay on their tests: `live.py` (`tests/test_live*`, `checkpoint_identity.py live_*`), `interactive.py`, `what_if.py` (`test_what_if*.py`), `lab_*/pause_*` (reached from live/interactive/what_if), 7 crisis scripts (`tests/test_crisis_*_example.py`), 26 viewer files (vitest 194 test files, `lint`, `build`; `HouseholdMobilityEvidence`, `ForecastConstruction`, `ForecastDecisions` show no direct test hit: add render smoke tests). Rust `economy.rs`, `tick.rs` etc. also keep `cargo test`.

## 4. Compatibility
No saved format, flag or import path changes. Fixtures untouched. Only test read paths and docs change.

## 5. Pins and preflight
`refactor_preflight.py`: a path in a frozen fixture is `historical` ("frozen witness; working tree not read"); the frozen copy and MANIFEST are `enforced`; fixture hash-literal findings for files read only via frozen copies drop to `historical`. `NOT_COVERED` gains the identity map. `tests/test_refactor_preflight.py:127` and `:51` change accordingly. Workflow copies, shard and oracle ownership remain `enforced`. The new tests go into existing modules, so no shard-manifest edit (`tests/test_native_ci_shards.py` module counts stay).

## 6. Classification
PIN-1 and PIN-2 are behaviour-preserving (no outcome change). Proof: every witness test passes unchanged against frozen copies before any source edit; the 9-case `compare` base-vs-new is empty.

## 7. Tests
Changed: the 9 witness tests, 5 mixed files (read sites only), `tests/test_refactor_preflight.py`. New: manifest-integrity test; a negative test that editing the working `main.py` leaves all witnesses green and `refactor_preflight` reports no `enforced` witness.

## 8. Risks
Goldens are environment-bound (wheel/Python bump forces a reviewed regeneration, which is itself a correction-style PR); gate runtime unmeasured; frozen copies may be mistaken for live code (the `.txt` suffix and README guard that); a witness that fails when frozen copy is wrong is detected by the one-off `--verify`. Rollback: revert PR 2; fixtures never changed.

## 9. Size
3 PRs, in this order: PR 1 identity gate (about +450 lines plus goldens); PR 2 frozen copies (+2.75 MB data, about +150 lines); PR 3 re-point 31 read sites, preflight, docs (about +120 lines, 60 doc lines). The gate lands before any pin is released.
