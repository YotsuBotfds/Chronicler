# Pin-policy transition and identity-gate coverage — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** (PIN-2) add a committed behavioural identity gate, then (PIN-1) make the 54 source-witness fixtures verify frozen copies instead of the working tree, so pinned files can be edited without inverse layers. **Architecture:** `turn_speed_identity.py` gains `digest`/`check`; frozen copies under `tests/fixtures/frozen_pin_sources/`; witness callers swap `ROOT/path` for `frozen_*`; preflight, AGENTS.md and DEVELOPMENT.md updated in the same PR as the switch. **Tech stack:** Python 3.13, pytest, GitHub Actions.
**Prerequisites:** DEC-1 signed by the owner for option A (spec section 3). Start from fetched `main`. No other PR may touch a pinned file between PR 2 and PR 3 (the freeze base must equal the goldens' source). PR order is deliberate: the gate exists before any pin is released.

## File map
| file | change |
|---|---|
| `scripts/turn_speed_identity.py` | add cases `g_*`, subcommands `digest`, `check` |
| `tests/test_turn_speed.py` | tests for `digest`/`check` (verify existing module name first) |
| `tests/fixtures/identity/{python,native}_goldens.json` | new, captured on CI |
| `tests/fixtures/identity/coverage.json` | new: path -> case names / `tests` / `none` |
| `.github/workflows/identity-gate.yml` | new workflow |
| `scripts/testing/frozen_sources.py` | new reader helper |
| `scripts/testing/freeze_pin_sources.py` | new one-off builder and `--verify` |
| `tests/fixtures/frozen_pin_sources/**` | 91 `<path>.txt` copies + `MANIFEST.json` |
| `.gitattributes` | `tests/fixtures/frozen_pin_sources/** -text` |
| 9 `tests/test_*_witness.py`; `test_grain_release_policy.py`; `test_regional_population.py`; `test_public_grain_shipments.py`; `test_health_care_policy.py`; `test_practice_observer_runner.py` | read sites only |
| `scripts/refactor_preflight.py`, `tests/test_refactor_preflight.py` | frozen-witness level, identity map |
| `AGENTS.md`, `docs/DEVELOPMENT.md`, `scripts/README.md`, `docs/CONTINUATION.md` | wording, ledger |

## PR 1: Identity gate (PIN-2)
### Task PIN-2: goldens, cases, workflow
- [ ] Step 1: Preflight `scripts/turn_speed_identity.py scripts/cities_identity.py` (expect reference-level only; both are unpinned).
- [ ] Step 2: In `scripts/turn_speed_identity.py` add to `CASES` (:42-56) the eight `g_*` rows of spec section 3 (names, args exactly as listed; keep original 9 untouched). Add `GATE_PYTHON = ("g_off_s42","g_off_proc_s7","g_batch_off")` and `GATE_NATIVE = (all other g_* plus g_off_s42 again)`. `g_batch_off` needs the batch output layout: run it once, read its directory, and if paths or timestamps appear in `batch_manifest.json`, normalise with the label approach of `tests/test_validation_parity.py` (`_Normalizer`); if not feasible drop the case and record `batch_manifest.py` as `tests` in coverage.json.
- [ ] Step 3: Add `digest`.
  - For each case directory, write `{"environment": {"compat": {python_minor, platform, rust_channel}, "provenance": {python_full, rustc, native_sha256 or null, native_source_digest or null}}, "cases": {name: {relpath: sha256(cities_identity._content(path, False))}}}`.
  - Skip `.log` and `run_manifest.json`, as `cities_identity.IGNORED_NAMES` does.
  - `native_source_digest` is a SHA-256 over `chronicler-agents/Cargo.toml`, `Cargo.lock` and `chronicler-agents/src/**` of the tree the extension was built from. The build step records it in a build receipt next to the wheel, for example `$RUNNER_TEMP/native-build.json` holding the wheel's and the installed extension's SHA-256.

  Add `check OUT GOLDEN [--lane python|native] [--build-receipt PATH]`. It checks three things in order:
  1. **Provenance.** The loaded extension's SHA-256 must equal the build receipt's, and the receipt's source digest must equal the candidate checkout's. The build must belong to the source under test; refuse otherwise.
  2. **Compatibility.** `compat` must equal the golden's. Otherwise refuse with "incompatible runtime: re-capture the goldens in a reviewed PR".
  3. **Identity.** Compare the output digests only, printing `differs:`/`only in:` lines like `compare`.

  The native SHA-256 is never an equality condition. A rebuilt extension prints `native rebuilt: <golden sha> -> <candidate sha>` for information. Exit 1 only on a failure in 1 or 2, or on an output difference. This keeps behaviour-preserving Rust refactors, whose binaries differ, mergeable without re-capturing goldens.
- [ ] Step 4: Tests, with synthetic two-directory cases:
  - `digest` is stable, and `generated_at` does not affect it;
  - a one-byte output change is detected;
  - **different native SHA-256 with identical outputs: accepted**, with the informational line printed;
  - **the same native SHA-256 with changed outputs: rejected**;
  - an incompatible `compat` (Python minor version or platform): refused;
  - a build receipt whose source digest does not match the checkout, or whose extension SHA-256 does not match the loaded file: refused. Put them in the existing turn-speed test module that already imports the script (verify with `rg -l turn_speed_identity tests`); if none imports it, extend `tests/test_permanent_faiths.py`'s neighbour only if already in an oracle chunk. Do not add a new test module (shard manifest and `tests/test_native_ci_shards.py` counts pin modules).
- [ ] Step 5: Write `.github/workflows/identity-gate.yml`: triggers `pull_request` (paths: `src/chronicler/**`, `chronicler-agents/src/**`, `scripts/turn_speed_identity.py`, `tests/fixtures/identity/**`), `workflow_dispatch` (input `capture: bool`), weekly `schedule`. Job `python-lane`: checkout, setup-python 3.13.17, `uv sync --frozen` (copy steps from `.github/workflows/tests.yml:67-120`), assert native absent, `python scripts/turn_speed_identity.py run $RUNNER_TEMP/id --case ...GATE_PYTHON`, then `check` (or `digest` + upload when `capture`). Job `native-lane`: `workflow_run` is not used inside PRs; instead copy the wheel build steps from `tests.yml:167-338` into this job (cost: a rebuild; reuse the build cache keys), install the wheel, run `GATE_NATIVE`. Do not edit `tests.yml` (job set asserted at `tests/test_native_build_lanes.py:226`). Pin actions by the same major tags as `tests.yml`.
- [ ] Step 6: Dispatch with `capture: true`; download the digests; commit `tests/fixtures/identity/{python,native}_goldens.json` unmodified. Dispatch twice more; both runs must `check` clean (determinism proof). Record the wall time per case; if a lane exceeds 25 minutes trim turns, re-capture, record the figures in the PR.
- [ ] Step 7: Build `coverage.json` from the spec table plus `rg` evidence: for each of the 91 paths, the cases that execute it (confirm with `python -X importtime`-free method: `coverage run` on one trimmed case per lane is permitted in CI only), else `tests` with the test file names (live/interactive/what_if/lab_*/pause_*/crisis scripts/viewer), else `none`. Any `none` goes in the PR description for the owner.
- [ ] Step 8: Add render smoke tests for `HouseholdMobilityEvidence`, `ForecastConstruction`, `ForecastDecisions` only after re-checking they have no direct test (`rg -l <name> viewer/src --glob '*.test.*'`); run `npm --prefix viewer run test -- <file>`, `lint`, `build`.
- [ ] Step 9: Verify: `.venv/bin/python -m pytest -q tests/test_refactor_preflight.py <turn-speed test file>`; `.venv/bin/python scripts/run_python_oracle_checks.py` (chunk limit untouched); `python scripts/turn_speed_identity.py compare` of a main-vs-main run is empty.
- [ ] Step 10: Ledger: CONTINUATION entry "identity gate added; goldens captured at <sha>; no outcome change". Commit message `Add committed identity goldens and gate workflow` plus the attribution lines.

## PR 2: Frozen snapshot data (PIN-1 part 1; additive)
### Task PIN-1a: copies and manifest
- [ ] Step 1: Confirm `main` has not moved a pinned file since PR 1 (`git diff <pr1-merge>..origin/main --name-only` against the list below).
- [ ] Step 2: Write `scripts/testing/freeze_pin_sources.py`: path set = union of `files` and `new_files` keys of every `tests/fixtures/*inverse*.json` (87 today) plus `chronicler-agents/src/health_care.rs`, `chronicler-agents/src/health_care_observation.rs`, `src/chronicler/health_care.py`, `src/chronicler/health_care_state.py` (the digests at `tests/test_health_care_policy.py:1017-1027`). Modes: `--write` copies bytes to `tests/fixtures/frozen_pin_sources/<path>.txt` and writes `MANIFEST.json` `{"freeze_commit": <HEAD>, "files": {path: sha256}}`; `--verify` (full clone only) compares each copy with `git show <freeze_commit>:<path>`.
- [ ] Step 3: Add the `.gitattributes` line; run `--write`, then `--verify` in a full clone (`git fetch --unshallow` if needed). Expected: 91 files, 0 mismatches.
- [ ] Step 4: Add `scripts/testing/frozen_sources.py`: `frozen_bytes(rel)`, `frozen_text(rel)` (`frozen_bytes(rel).decode("utf-8")`), `FROZEN_ROOT`, and `MANIFEST`. Raise `FileNotFoundError` naming the path; never fall back to the working tree.
- [ ] Step 5: Add one test to `tests/test_refactor_preflight.py` (already in an oracle chunk, `scripts/run_python_oracle_checks.py:78`): every copy's sha256 equals MANIFEST; MANIFEST paths equal the union above. Check `pyproject.toml` ruff and pytest settings do not collect `.txt` copies (unverified; if ruff globs `tests/fixtures`, add an exclude).
- [ ] Step 6: Tag the freeze commit after merge: `git tag pin-freeze-2026-11 <freeze_commit>` and push the tag (owner action if tags are protected). Verify: `.venv/bin/python -m pytest -q tests/test_refactor_preflight.py`; oracle lane. Ledger entry; commit `Freeze reviewed source snapshot for witness chains`.

## PR 3: Switch witnesses to the snapshot and release the pins (PIN-1b)
### Task PIN-1b: re-point, preflight, docs
- [ ] Step 1: Baseline before editing: `.venv/bin/python -m pytest -q tests/test_academy_candidate_witness.py tests/test_crisis_candidate_witness.py tests/test_food_accounting_witness.py tests/test_household_mobility_witness.py tests/test_information_candidate_witness.py tests/test_information_qualification_witness.py tests/test_livelihoods_sprint_witness.py tests/test_restoration_candidate_witness.py tests/test_scenarios_candidate_witness.py tests/test_grain_release_policy.py tests/test_regional_population.py tests/test_public_grain_shipments.py tests/test_health_care_policy.py tests/test_practice_observer_runner.py -q -p no:cacheprovider | tail -3`; save the pass list (`-rA | grep PASSED | sort`) to the scratchpad. Native-dependent tests may skip; record the skip count.
- [ ] Step 2: Edit read sites only (about 31): in the 9 witness tests replace `(ROOT / path).read_bytes().decode("utf-8")` and `.read_bytes()` digests with `frozen_text(path)` / `frozen_bytes(path)`; in `test_grain_release_policy.py:217-235`, `test_regional_population.py:249,261`, `test_public_grain_shipments.py:594-598`, `test_health_care_policy.py:1005-1075` (both tests, including the four direct digests) and `test_practice_observer_runner.py:444,453,518` (`Path(M.__file__).read_text()` becomes `frozen_text("src/chronicler/main.py")`). Leave `scripts/testing/*_witness.py` unchanged: they take source as an argument and read only fixtures. Leave line 246 of `test_practice_observer_runner.py` (parses the imported module for a different purpose) after reading it: if it feeds a witness comparison, switch it too.
- [ ] Step 3: `scripts/refactor_preflight.py`: add `FROZEN_MANIFEST = "tests/fixtures/frozen_pin_sources/MANIFEST.json"`. In `witness_findings` (:155-175) emit `Finding("historical", "frozen source witness", rel, "verified against the frozen copy; editing this file does not break it")` instead of `enforced` when the path is in MANIFEST. Add `enforced` findings for the copy path and MANIFEST (editing them breaks the integrity test). Add MANIFEST to the skip sets in `json_hash_records` and `literal_digest_findings` (the `witness_files` set at :323). Add the identity map: print `identity gate: <cases>` or `NO IDENTITY CASE` from `coverage.json`. Add one `NOT_COVERED` line: identity cases run only the listed switches.
- [ ] Step 4: `tests/test_refactor_preflight.py`: change the assertion at `:51-53` fixture (temporary repo with a frozen MANIFEST) and `:127-130` so a real witnessed file such as `src/chronicler/simulation.py` reports no `enforced` witness and one `historical` frozen witness, while the copy reports `enforced`. Keep the old behaviour test with a manifest-less temporary repo.
- [ ] Step 5: Docs. `AGENTS.md:45-48` becomes: "Workflow byte copies, the native shard manifest and oracle-chunk ownership pin paths and contents; run `scripts/refactor_preflight.py` before moving or deleting files. Source-witness fixtures and `tests/fixtures/frozen_pin_sources/` are frozen history: they verify the reviewed chains against the sources as of `pin-freeze-2026-11`, not the working tree. Never edit, re-hash or regenerate them. Gate refactors with `scripts/turn_speed_identity.py check` (and `compare` for two-checkout runs) plus the oracle lane." Also change the "Before refactoring" sentence in the same file's Working-safely block and drop "(see DEVELOPMENT.md)" ambiguity. `docs/DEVELOPMENT.md` "Before refactoring": rewrite the "Source witnesses" bullet (frozen reads, no inverse layers, `reviewed_main_witness.py` is now history), update the level definitions (`enforced` no longer includes witnesses), delete the 83/25 count sentence, add "Identity gate" with the case table and the correction protocol (an intended outcome change updates the goldens in its own PR with before/after and a CONTINUATION entry). `scripts/README.md:31-32`: note the freeze scripts and that `livelihoods_layer_tool.py` is retired (do not delete it).
- [ ] Step 6: Verify every chain still verifies: (a) rerun Step 1's command; the pass list must equal the saved one, with the same skips. (b) `.venv/bin/python -m pytest --collect-only -q <same files> | tail -1` equals the baseline count (15 witness tests plus the 7 embedded). (c) Release proof, in a scratch copy only: append `# edit` to `src/chronicler/main.py`, `simulation.py` and `chronicler-agents/src/tick.rs`, rerun the 14 files (all pass), run `refactor_preflight.py` on the three (no `enforced` witness line), then discard the copy. (d) Mutation sanity: flip one character in a frozen copy in the scratch copy; the matching witness test and the integrity test fail. (e) `.venv/bin/python scripts/run_python_oracle_checks.py` passes; `python scripts/refactor_preflight.py --git-diff origin/main` shows only expected findings. (f) `identity-gate` is green on the PR.
- [ ] Step 7: Ledger: CONTINUATION entry (decision date, DEC-1 option A, freeze commit and tag, goldens commit, counts verified). Commit `Verify source witnesses against a frozen snapshot; retire working-tree pins`.

## Option B/C notes (only if the owner chooses them)
- B: no code change; document in DEVELOPMENT.md the per-edit procedure of spec section 3 and require `scripts/testing/livelihoods_layer_tool.py NAME PARENT_REV PATH...` plus a `LAYERS` append per PR; serialise PRs touching the same file.
- C: ship PR 1 and PR 2 unchanged; PR 3 makes `frozen_*` consult `tests/fixtures/pin_retirement.json` (path list) and fall back to the working tree otherwise; preflight reports `enforced` only for unlisted paths; each wave adds its paths in an owner-approved PR.

## Done when
- [ ] Goldens captured on CI and three consecutive `check` runs clean.
- [ ] `coverage.json` lists all 91 paths; every `none` has an owner note.
- [ ] 91 frozen copies equal `git show pin-freeze-2026-11:<path>` (`--verify`).
- [ ] The 14 test files give the identical pass list and counts before and after PR 3.
- [ ] Editing `main.py`, `simulation.py` and `tick.rs` in a scratch copy breaks no witness test; preflight shows no `enforced` witness for them.
- [ ] No fixture file changed (`git diff --stat -- 'tests/fixtures/*inverse*.json'` empty across all PRs).
- [ ] AGENTS.md, DEVELOPMENT.md, scripts/README.md and CONTINUATION updated in PR 3.
- [ ] Workflow byte copies, shard manifest and oracle chunks unchanged.
