# Behaviour Corrections (COR-3 to COR-8) — Implementation Plan
> **For agentic workers:** execute task by task; steps use checkbox (`- [ ]`) syntax. Run the
> preflight before touching any file; never rewrite a pinned hash; one PR per numbered PR block.

**Goal:** land six verified behaviour corrections, each with a baseline, a ledger entry and owner sign-off where a DEC applies.
**Architecture:** small edits in existing modules; new optional serialized fields are omitted when empty; shadow-compare before switching any decision read.
**Tech stack:** Python 3 (`.venv/bin/python`), pytest, Rust/PyO3 for COR-7 only (build into the separate venv from `scripts/cloud_setup.sh`).
**Prerequisites:** DEC-4, DEC-5, DEC-7 answered in writing; PIN-1 for enforced files (`tuning.py`, `ecology.py`, `scholarship.py`); work from fetched `main`.

Common baseline recipe (referred to as BASE below):
1. Before editing, on clean `main`: `.venv/bin/python scripts/turn_speed_identity.py run <scratch>/base --case off_s42` and again for `hybrid_s42` and `proc48_hybrid_s42` (native cases need the built extension).
2. After editing: same into `<scratch>/new`, then `.venv/bin/python scripts/turn_speed_identity.py compare <scratch>/base <scratch>/new`. "Identical" = no differences reported.
3. Default-path outcome changes also need a paired seed batch (same seeds, before and after, report the changed metrics and event counts) using the batch runner (`src/chronicler/batch.py`, seeds from `scripts/seed_registry.json`), and the documented 200-seed gate before any default calibration claim. State in the ledger which gates were not run.
4. Always finish with `.venv/bin/python scripts/run_python_oracle_checks.py` (bounded lane; does not qualify native runs).

## File map
| File | Change |
|---|---|
| `src/chronicler/tech.py` | COR-3 emit order, shared multiplier |
| `src/chronicler/techniques.py` | COR-3 import multiplier |
| `src/chronicler/public_health.py`, `livelihoods.py` | COR-4 new-enable default, help text |
| `src/chronicler/models.py`, `war/occupation.py`, `action_engine.py` | COR-5 `Region.last_takeover` |
| `src/chronicler/cities.py`, `diplomacy.py`, `epidemiology.py`, `nomads.py`, `scholarship.py` | COR-5 reads |
| `tests/test_provenance_decision_guard.py` | COR-5 guard entries removed |
| `src/chronicler/war/runtime.py`, `war/armies.py`, `models.py`, `attribution_records.py` | COR-6 |
| `chronicler-agents/src/politics.rs` (+ tests), `src/chronicler/politics.py` comments | COR-7 |
| `src/chronicler/ecology.py`, `chronicler-agents/src/ecology.rs` (tests only), `tuning.py`, `tests/` | COR-8 |
| `docs/CONTINUATION.md`, `docs/integration/*.md` | ledger and docs per PR |

## PR 1: Scholarship emit order (COR-3)
### Task COR-3: move the event after the gate, share the multiplier
- [ ] Step 1: Preflight `.venv/bin/python scripts/refactor_preflight.py src/chronicler/tech.py src/chronicler/techniques.py`. `tech.py` shows DIGEST rows (`tests/fixtures/performance/corrected_*.json`, `reference_baselines/.../MANIFEST.json`). Find the test that reads them (`rg -l corrected_423a67c tests`) and confirm it does not compare the current tree; if it does, stop and ask for PIN-1.
- [ ] Step 2: Record BASE. Also record the current count of `capability_scholarship` events from a `--no-techniques` run with a scholarship civ (a small script in the scratchpad using `tests/test_tech.py` fixtures).
- [ ] Step 3: In `tech.py` add `SCHOLARSHIP_COST_MULTIPLIER = 0.8` near `TECH_REQUIREMENTS` (`:31`). In `check_tech_advancement` (`:92-115`) compute `scholarship = civ.active_focus == "scholarship"`, set `effective_cost` from the constant, run the gate, and only after the gate passes (before or after the charge) append the `capability_scholarship` event when `scholarship`.
- [ ] Step 4: In `techniques.py:106` replace the literal with `from chronicler.tech import SCHOLARSHIP_COST_MULTIPLIER as SCHOLARSHIP_COST` at call sites or module level if no import cycle (`tech.py` must not import `techniques` at module level).
- [ ] Step 5: Tests in `tests/test_tech.py`: (a) scholarship civ with treasury below cost emits no event and returns None; (b) with enough treasury, exactly one event and `treasury == before - int(cost*0.8/rate)`; (c) `tech.SCHOLARSHIP_COST_MULTIPLIER is techniques.SCHOLARSHIP_COST` equal. Keep `tests/test_techniques.py:398` passing.
- [ ] Step 6: Verify: `.venv/bin/python -m pytest tests/test_tech.py tests/test_techniques.py tests/test_acc_hardening.py -q` pass; BASE compare identical on the default (techniques-on) cases; the legacy count from step 2 drops to the number of successful advances.
- [ ] Step 7: Owner gate. Ask for the DEC-7 era cost rule. If A (recommended): add a short "cost rule" paragraph to `docs/integration/techniques.md`. If C: stop; open a separate calibration PR with the 200-seed gate.
- [ ] Step 8: Ledger: CONTINUATION entry "scholarship event only when the advance is paid; one multiplier constant; cost rule = <A/C>"; stream-only on legacy path; commit message `fix: emit capability_scholarship only for paid era advances (COR-3)`.

## PR 2: Health crowding default for new enables (COR-4)
### Task COR-4
- [ ] Step 1: Preflight `src/chronicler/public_health.py src/chronicler/public_health_state.py src/chronicler/livelihoods.py` (expect references only).
- [ ] Step 2: Edit `public_health.py:38-39`: `state = PublicHealthState(crowding="density_only")`. Leave `public_health_state.py:46` and `__setstate__` unchanged. Confirm by reading how `set_<name>_enabled` is reached (`rg "set_public_health_enabled|_enabled" src/chronicler/livelihoods.py src/chronicler/main.py src/chronicler/live.py`) that restore never builds a fresh state for a world that had one.
- [ ] Step 3: Update `livelihoods.py:244` text: new enables default to `density_only`; saved worlds keep their recorded mode; `legacy_displacement` stays selectable.
- [ ] Step 4: Tests in `tests/test_residence_exposure.py:445-466`: change the first assertion to `density_only`; keep the old-JSON/old-pickle assertions (legacy); add: explicit `legacy_displacement` stays legacy through pickle and resume; a world with a state that was disabled and re-enabled keeps its mode; new enable with `args=None` gives `density_only`. Run `rg -n "public_health" tests/*.py -l` and fix any test that enabled without the flag and asserted displacement results.
- [ ] Step 5: Verify: `.venv/bin/python -m pytest tests/test_residence_exposure.py tests/test_public_health.py tests/test_public_health_integration.py tests/test_cw_rework_screen.py tests/test_batch_manifest.py -q`; native file `tests/test_residence_exposure_native.py` needs the build (state in the ledger if not run). BASE compare: identical (feature default-off). Paired run: the same hybrid world with `--public-health` (plus its required flags) before and after, 8 seeds, report epidemic deaths and displaced counts via `scripts/cw_rework_screen.py` (confirm its flags from its argparse before use).
- [ ] Step 6: Ledger: "persisted default unchanged; new enables without `--public-health-crowding` now use density_only; saved worlds untouched"; cite `docs/superpowers/progress/connected-world-rework-report.md`; commit `fix: new public-health enables default to density_only crowding (COR-4)`. Owner sign-off required (DEC-5).

## PR 3: Takeover field and cities read (COR-5 #1)
### Task COR-5.1
- [ ] Step 1: Preflight `models.py cities.py war/occupation.py action_engine.py`. Add `last_takeover: tuple[int, str] | None = Field(default=None, exclude_if=_is_none)` to `Region` (`models.py` near `:504`). Write it at `war/occupation.py` (occupation start, `:105`; annexation, `:164`) and `action_engine.py:659`.
- [ ] Step 2: Shadow test: temporary assertion in `cities._lord_change` that `bool(old read) == (region.last_takeover is not None and world.turn - region.last_takeover[0] <= 1)`; run `tests/test_cities.py tests/test_war_occupation.py tests/test_war_integration.py` and a 20-seed batch with the assertion logging mismatches to the scratchpad. Mismatch count must be reported.
- [ ] Step 3: Replace the read at `cities.py:570-572`; remove `('cities', '_lord_change', 'recall')` from `KNOWN_DECISION_READS` (`tests/test_provenance_decision_guard.py:178`). The provenance `cite` of the cause stays (describing, not deciding).
- [ ] Step 4: Verify: guard test, `tests/test_cities.py`, BASE compare (expected identical if mismatches = 0; otherwise it is a correction: run the seed batch and describe the difference).
- [ ] Step 5: Ledger, commit `fix: cities decide sacks from region takeover state, not provenance (COR-5)`. Owner sign-off (DEC-4).

## PR 4: Diplomacy aid reads famine state (COR-5 #2)
- [ ] Step 1: Preflight `diplomacy.py`. Decide the state with the owner: onset/repeat of a food crisis is "a crisis report whose region was not already in `famine_cooldown`" (`models.py:441`). Write the predicate as a small function in `ecology.py` or `diplomacy.py` reading only region fields.
- [ ] Step 2: Shadow-compare against `ev.episode == "tick"` across 20 seeds; log mismatches.
- [ ] Step 3: Replace `diplomacy.py:1759`; drop the guard entry (`:180`). Test in `tests/test_diplomacy.py`: an ally in a continuing famine does not get a second convoy inside the cooldown, one in a new crisis does.
- [ ] Step 4: BASE and a 40-seed paired batch comparing `aid_convoy` counts and treasury totals. Ledger + sign-off; commit `fix: aid convoys read region famine state (COR-5)`.

## PR 5: Epidemiology onset flag (COR-5 #3)
- [ ] Step 1: Preflight `epidemiology.py`. Add a persisted bool `episode_open` on the epidemiology row (default False, omitted when False): set True when the report is emitted, cleared when the outbreak subsides after the same gap used by `provenance.CHRONIC` for epidemics (read `provenance.py` `CHRONIC`/`EPISODE_FAMILY` to copy the gap).
- [ ] Step 2: Shadow-compare `onset` at `epidemiology.py:905`; log mismatches over 20 seeds.
- [ ] Step 3: Switch; drop the guard entry (`:182`). Tests in `tests/test_epidemiology.py` for onset, repeat within the gap, return after the gap.
- [ ] Step 4: BASE + 40-seed paired batch (arrival events, epidemic counts). Ledger, sign-off, commit `fix: epidemic onset from row state (COR-5)`.

## PR 6: Nomad drought gate (COR-5 #4)
- [ ] Step 1: Preflight `nomads.py`. Replace the recall at `nomads.py:825` with a drought-condition check for the civ (see `events.py:498` `has_condition`), keeping `phase == ClimatePhase.DROUGHT` as it is. To keep the 10-turn tail, store `state.drought_until` per civ when a drought condition is seen (persisted, default empty).
- [ ] Step 2: Shadow-compare, switch, drop guard entry (`:184`). Keep the cause recall at `:820` and `:828` (it only cites).
- [ ] Step 3: Tests in `tests/test_nomads.py`; BASE; 40-seed batch counting `pasture_drought`. Ledger, sign-off, commit.

## PR 7: Scholarship reads (COR-5 #5-#7, one PR, opt-in)
- [ ] Step 1: Needs PIN-1 (`scholarship.py` enforced). Replace `_in_famine` (`:750`) with the PR 4 predicate, `_newly_occupied` (`:391`) with `Occupation.since_turn == turn`, `_sack_cause` (`:406`) with `last_takeover`. Remove the three guard entries (`:184-190`); the guard set must now be empty, so delete the `KNOWN_DECISION_READS` constant and make the test fail on any decision read.
- [ ] Step 2: Verify `tests/test_scholarship.py tests/test_provenance_decision_guard.py`; BASE (identical: opt-in); one `--scholarship` scenario before/after. Ledger, sign-off.

## PR 8: Early returns in `declare_or_press_war` (COR-6a)
- [ ] Step 1: Preflight `war/runtime.py` (references only). Before the two `return Event(...)` at `:107-115`, add `world.events_timeline.extend(ctx.events); flush_military_losses(ctx)` (factor the pair into a local helper used by the final path at `:139-140`).
- [ ] Step 2: Test in `tests/test_war_integration.py`: arrange `world.active_wars` stale entry so `reconcile_wars` closes a war, then call with a truce; assert `war_ended` is in `events_timeline` once.
- [ ] Step 3: BASE, 40-seed batch (event counts by type, military stat totals), ledger, commit `fix: war early returns keep reconciliation events (COR-6)`.

## PR 9: Non-roster casualties follow the drain (COR-6b)
- [ ] Step 1: `war/armies.py:340-343`: `count = drain_population(...)`. Edit docstring. Owner to confirm "soldiers die only for people actually drained".
- [ ] Step 2: Test in `tests/test_war_armies.py`: an army with no roster whose civ regions have zero population loses 0 soldiers; with population it loses `count`.
- [ ] Step 3: BASE (campaign cases), 40-seed batch (casualties, army counts), ledger, commit.

## PR 10: Natural deaths out of casualties (COR-6c)
- [ ] Step 1: Add `Army.natural_deaths: int = 0` (`models.py:865`, omit when 0). In `reconcile_rosters` (`war/armies.py:447`) increment `natural_deaths` instead of `casualties`. In `attribution_records.py:619-621` use `casualties + natural_deaths` for the closure change; update the docstring at `:23`.
- [ ] Step 2: Tests: `tests/test_war_armies.py` (counter split), the attribution-records tests (`rg -l reconcile_rosters tests`), and `war/runtime.py:208` verdict with a natural-only army.
- [ ] Step 3: BASE, 40-seed batch (destroyed vs demobilized counts, `army_destroyed` events). Ledger quoting the 17% figure as prior, new measured figure from the batch. Sign-off.

## PR 11: Delete Rust politics step 11 (COR-7)
- [ ] Step 1: Preflight `chronicler-agents/src/politics.rs` (references only). Confirm `ffi/batch.rs:125` keeps `StripToFirstRegion` mapped.
- [ ] Step 2: Remove `step_forced_collapse` (`:2888-3025`) and its call (`:3189-3196`); update the header comment (`:1-5`, "11-step" to "10-step"). Keep the `CivOpType` variant.
- [ ] Step 3: Tests: delete the step-11 block in `chronicler-agents/tests/test_politics.rs:1147-1220` and the step-11 assertions at `:1610`; rewrite `tests/test_politics_parity.py:700-715` and `tests/test_politics_bridge.py:1603-1606` to assert no op has step 11 when asabiya is below 0.1; change range checks (`1 <= step <= 11`) to 10; remove the `op[0] != 11` filters in `tests/test_politics_bridge.py:2243,2363` only if still harmless (leave them).
- [ ] Step 4: Verify: build into the separate venv (`scripts/cloud_setup.sh` describes it), then `cargo test politics` in `chronicler-agents`, `.venv/bin/python -m pytest tests/test_politics.py tests/test_politics_bridge.py tests/test_politics_parity.py -q`, and BASE native cases `hybrid_s42` and `hybrid_s7`: must be identical. The Python oracle path is untouched.
- [ ] Step 5: Ledger: "Rust step 11 removed; Python collapse (post-aggregation, severity-scaled) remains authoritative"; retain build and source identities; commit `refactor: drop discarded Rust forced-collapse step (COR-7)`. Option A (Rust authoritative) is a later correction, not part of this PR.

## PR 12: `hills`/`river` rows and parity test (COR-8a)
- [ ] Step 1: Preflight `ecology.py` (enforced: needs PIN-1). If PIN-1 is not done, ship only the test.
- [ ] Step 2: Add `"hills"` and `"river"` rows equal to `"plains"` in both tables (`ecology.py:50-72`) with the comment "legacy labels map to plains in Rust, `ffi_constants.TERRAIN_MAP`".
- [ ] Step 3: Test in `tests/test_ecology_parity.py`: for each key in `TERRAIN_MAP`, Python caps (table lookup) equal the Rust cap row for `TERRAIN_MAP[key]` (read via the exposed ecology test hook if one exists; otherwise parse `ecology.rs:85-95` with a regex).
- [ ] Step 4: Verify tests; BASE identical. Ledger: behaviour-preserving.

## PR 13: Deprecate unread tuning keys (COR-8b)
- [ ] Step 1: Needs PIN-1 (`tuning.py`). Add `DEPRECATED_UNREAD_KEYS` listing the eight dotted names; in `load_tuning` (`tuning.py:425-440`) warn `"tuning key X is accepted but has no effect"` for each present. Keep the constants and `KNOWN_OVERRIDES` entries.
- [ ] Step 2: Tests in `tests/test_tuning.py`: a YAML naming a deprecated key warns once and loads; a test that fails if any non-deprecated `K_*` constant has no reader (`rg`-style scan of `src/chronicler`), so new dead keys cannot appear.
- [ ] Step 3: Verify, BASE identical, ledger.

## PR 14: `TITHE_RATE` parity test (COR-8c)
- [ ] Step 1: Add a test in `tests/test_economy_bridge.py` (or the nearest economy parity file) that reads `economy.rs` for `const TITHE_RATE` and `TITHE_FOOD_GATE` and compares to `factions.TITHE_RATE` and `economy.py:2124`. No source edits, so no pin touched.
- [ ] Step 2: Ledger note that no tuning key exists; any future key goes through CON-5.

## Done when
- [ ] Each PR merged on its own with BASE compare result, focused test list and oracle lane result in the ledger.
- [ ] DEC-4, DEC-5, DEC-7 answers recorded in the ledger entries that rely on them.
- [ ] `KNOWN_DECISION_READS` is empty or deleted.
- [ ] No pinned hash rewritten; every enforced-file edit cites PIN-1.
- [ ] Gates not run (200-seed, native) are named as not run.
