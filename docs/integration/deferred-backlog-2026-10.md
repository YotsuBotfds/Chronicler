# Deferred backlog pass, 2026-10

Branch `fix/deferred-backlog`, based on `837a44f`. Each backlog item was checked
against current code before any change, and each item has one commit. The
sources were `docs/superpowers/progress/phase-6-progress.md`,
`docs/superpowers/plans/audit-remediation-2026-04-05.md`,
`docs/superpowers/plans/2026-04-03-reaudit-remediation-plan.md`,
`masteraudit.md` and `opusaudit4-1-26.md`. Parallel work owns economy and
ecology reconciliation, governance in Phase 10, wars and occupation, and world
extinction (events.py and twilight absorption). Edits near those areas are
limited to the specific lines each fix needed.

## Item status

| # | Item | Status | Commit |
| --- | --- | --- | --- |
| 1 | M48 promotion memory and victory civ filter | Fixed | `8cc76d9` |
| 2 | M59b deferred: loyalty coupling, religious consumer, packet layout | Fixed | `b746b9d` |
| 3 | Persecution intensity unclamped (T3-4) | Fixed | `84ead3f` |
| 4 | Tech-regression flush (T1-3) | Fixed (off/shadow/demographics gap) | `d7b44e0` |
| 5 | River/hills terrain partially supported (T3-16) | Fixed | `cd6e7c5` |
| 6 | WAR 2.5x ceiling (T2-3), collapse severity (T3-13) | Decided, documented and pinned (no behavior change) | `6ec175c` |
| 7 | `K_PEAK_YIELD` unused | Removed | `7f8cf98` |
| 8 | M44/M42/M43a/M51 deferred notes | Code-actionable parts fixed or measured | `3c78762` |
| 9 | `tuning/m53_baseline.yaml` not UTF-8 | Fixed | `81a6f95` |
| 10 | Six unreferenced analytics extractors | Two wired, four deleted | `47f225d` |
| 11 | Nested test in `test_ecology.py` | Fixed | `a6b7935` |
| 12 | Rust `Exile` placeholder, bypasses 2-4 | Documented; dead Python path removed | `dfd7fe3` |
| 13 | masteraudit B-1, C-2, guard semantics, H-36..H-40 | Mostly already fixed; unknown-category rejection added | `664a74e` |

## Corrections (behavior changes)

These fixes deliberately change behavior. Each one changes only what its fix
requires.

- **Tech regression (item 4).** The audit only flagged hybrid mode, which
  already had a third `apply_keep()`. `--agents=off`, shadow and
  demographics-only modes still passed the already-flushed accumulator to
  `check_tech_regression`, which silently dropped `remove_era_bonus()`
  deltas. A civ lost the era but kept its bonus. Tech regression now follows
  the Phase 10 routing rule (`phase10_acc`). In the golden off-mode workloads
  only `wide` changes, from turn index 23 (Kethani Empire bronze -> tribal).
  The live oracle is now `tests/fixtures/performance/corrected_backlog_2026_10.json`
  (plus the `corrected_artifacts_` file). `corrected_423a67c` stays frozen. A
  test re-creates the old dropped removal and gets back the 423a67c `wide`
  turn hashes and RNG trace exactly. Another test checks that undeclared
  workloads are byte-identical.
- **Scenario terrain overrides (item 5).** `apply_scenario()` changed a
  template region's terrain string but kept the template's resource slots,
  ecology, disease baseline and turn-0 stockpile. As a result the river/hills
  resource tables never applied. For example, Dead Miles' river "Dockside"
  started as a desert with exotic goods and a cholera baseline. Regions whose
  terrain changes now get that state re-derived the same way
  `generate_world()` derives it. River and hills use plains ecology, which
  matches `TERRAIN_MAP` (both map to plains in Rust) and the plains fallbacks
  for caps, climate and terrain effects. Only scenario runs are affected.
- **Persecution clamp (item 3).** `min(1.0, ...)`. With the default multiplier
  `minority_ratio` is already in (0, 1], so nothing changes unless
  `multiplier.religion_intensity > 1`.
- **Promotion and Victory memories (item 1, agent modes).** `get_promotions()`
  queues a Promotion memory, and the next `tick()` writes it, stamped with the
  promotion turn. The write is deferred so that the same-turn Python Mule roll
  still sees only pre-promotion memories. Promotion is not in `MULE_MAPPING`,
  so writing it immediately would have suppressed Mules. Victory now requires
  that the soldier's civ is the region's post-battle `controller_civ` and that
  the region did not change hands this turn. A conquered region contains the
  realigned losing defenders, who keep Battle and Conquest memories.
- **Packet consumers (item 2, agent modes).** `AgentPool.pkt_source_civ`
  records the civ that controlled the source region when the packet was
  observed. Propagation copies it, a refresh updates it and expiry clears it.
  Provenance never affects admission. Two new consumers read packets:
  - Loyalty rally: a nonlocal threat packet whose provenance is the agent's
    own civ damps drift away by up to `LOYALTY_RALLY_DRIFT_DAMPING` (0.5) x
    strength. It never creates drift and never causes flips.
  - Religious signal: a sect-based destination preference, which is one of
    the semantics the M59b spec named. Destinations the agent has heard
    religious news about get ±`RELIGIOUS_SIGNAL_MIGRATION_WEIGHT` (0.10) x
    strength, depending on whether the agent shares the majority faith.
  New `knowledge_stats` counters: `migration_choices_changed_by_religion` and
  `loyalty_drifts_damped_by_rally`. No new RNG draws. Over an 80-turn hybrid
  probe, both consumers fired hundreds of times, which is meaningful without
  being dominant.
- **Batch token metadata (item 8, M44 NB-1).** Each run now reports the
  token delta it spent from a shared narrative client. Before, it reported
  the client's cumulative total.
- **Accumulator categories (item 13).** `StatAccumulator.add()` now rejects
  unknown categories. All 123 production call sites already use the five
  documented ones.

## Decisions

- **2.5x action-weight ceiling (T2-3).** It stays an absolute per-action
  ceiling applied as the final step, as required by AGENTS.md's capped
  modifiers and the Phase 8 roadmap. Accepted consequences:
  - A civ with military >= 70 and a hostile neighbor reaches the WAR ceiling
    from the situational boost alone.
  - Further WAR boosts have no effect once WAR is at the ceiling.
  - Suppressors such as war-weariness only show once the uncapped product
    falls below the ceiling.

  On the 837a44f subset baseline the cap fires in about 80% of civ-turns
  (analytics `precap_weights`), so moving the clamp inside the multiplier
  chain would be a global retune. That belongs in a tuning milestone.
  `tests/test_weight_cap.py::TestAbsoluteCeilingDecision` pins these
  semantics.
- **Collapse severity (T3-13).** Intentional, and applied once. The halving
  is the base loss. The M18 multiplier scales it once on both the direct
  route and the hybrid guard-shock route (shocks are normalized and never
  re-multiplied). At the 2.0 cap, collapse bottoms out at `STAT_FLOOR`.
- **`K_PEAK_YIELD` (item 7).** Removed. The ceiling it was meant to tune is
  Rust's `satisfaction.rs` `PEAK_YIELD` (1.0), and no Python-to-Rust channel
  for it ever existed. `ecology.peak_yield` now produces an unknown-key
  warning instead of being accepted silently with no effect. Eight other
  tuning keys also have no consumer (`stability.drain.twilight`, several
  `ecology.*` keys, and two `infrastructure.*` keys). They are left for their
  owners, mostly ecology.
- **Analytics (item 10).** Wired, because they work against real bundles:
  - `extract_gini_trajectory` (TurnSnapshot `civ_stats.gini`)
  - `extract_merchant_trip_stats` (`metadata.merchant_trip_stats`)

  Deleted:
  - `extract_trade_volume` and `extract_trade_flow_by_distance`, which only
    returned a "deferred" note
  - `extract_food_sufficiency`, a misnamed proxy that counted three of the
    five food goods
  - `extract_spatial_diagnostics`, which had no data path from any bundle or
    the bridge
- **Exile and bypasses 2-4 (item 12).** `find_candidates` is the only
  promotion gate. Python's "bypasses" relabel the roles of skill-gated
  candidates, using lifetime migration and switch counts that only the event
  history has, so they stay in Python. The "long displacement -> exile"
  relabel could never fire, because it read state that is only tracked for
  agents who are already named. It would also have been wrong: on a
  GreatPerson, `exile` is the deposed-leader pretender role, which drains the
  origin civ's stability and can be restored to the throne. That branch is
  removed and role-4 promotion rows are rejected. The Rust variant stays as
  reserved wire id 4.

## Already fixed before this pass

- T1-3's hybrid flush was already in place; item 4 closes the remaining
  modes.
- masteraudit B-1: stability recovery routes as guard-shock, and Rust
  consumes positive shocks. The comment that claimed shadow and
  demographics-only modes apply it is corrected: they use `apply_keep()`
  and route no shocks (the C-10 decision).
- masteraudit C-2: Phase 10 already sees same-turn events.
- The guard-category semantics were already documented and tested.
- H-36..H-40 already had dedicated tests: `test_weight_cap.py`,
  `test_phase_functions.py`, `test_culture_conversion.rs`,
  `test_demographics_integration.rs` and `test_agents_off_determinism.py`.
- B-2 (inverted persecution intensity) was fixed earlier; item 3 only adds
  the clamp.

## Measurements and follow-ups

- **M51 legitimacy activation.** The new `extract_legitimacy_activation`
  counts 0 dynasty-legitimate winners in 69 succession-crisis resolutions
  on the 837a44f subset baseline (20 hybrid seeds x 200 turns), and 0 in 63
  on this branch's subset run. Dynasty scoring is currently decorative. This is for the governance and
  succession owners; no retune was made here.
- **Victory source civ.** Victory memories still record the soldier's own
  civ as `source_civ`, so narration renders "victory over the <own civ>".
  Fixing this needs the defeated civ from war resolution, which the war
  owners control.
- **Shadow and demographics-only modes.** These modes drop all signal and
  guard-shock stat changes from their aggregate stats, including stability
  recovery and drains. This is the documented C-10 trade-off and is worth
  revisiting with the shadow-mode owners.
- **Not code-actionable here.** The M44 20-seed narration quality review
  (manual), the M42/M43a calibration and 200-seed regression (tuning), and
  the M42 price series (needs a bundle schema change). The M43a off-mode
  stockpile accumulation test is superseded, because the off-mode economy
  has been frozen since M54b.

## Verification

All results below were run on Linux, Python 3.13, with a fresh
`maturin develop --release` build of the branch's `chronicler_agents`
installed in the worktree venv.

- `python -m pytest -q -m "not slow" -n 2`: **5000 passed, 3 skipped**
  (base 4954 passed, 3 skipped; 46 new tests).
- `cargo test --manifest-path chronicler-agents/Cargo.toml`: **840 passed,
  2 ignored** (base 821 passed, 2 ignored; 19 new tests).
- Subset gate (`scripts/m53b_run_validation.py --profile subset --parallel 2`;
  20 hybrid seeds x 200 turns), compared with
  `chronicler.validation_compare` against the 837a44f baseline:
  **NO REGRESSION**, exit 0, no new required failures.
  - Oracle statuses match the baseline: arcs, cohort, community, era and
    needs PASS; artifacts PARTIAL; determinism SKIP.
  - The regression oracle still reports the pre-existing
    `terminal_population_extinction` FAIL. That is owned by the
    world-extinction work and is out of scope here.
  - The strict-floor failures drop from four to three:
    `migration_rate_per_agent_turn` now passes. Metric deltas:
    - latest satisfaction mean +0.011
    - migration rate per agent-turn +0.0024
    - satisfaction mean -0.004

  The first gate attempt was lost when the shared disk filled while the
  report was being written. It was rerun from scratch, and git objects and
  all changed files were re-verified afterwards.
- The golden off-mode oracles move only as declared, and only for item 4 (see
  above). All other items leave `--agents=off` golden outputs byte-identical.
- Not run: the 200-seed full gate, viewer checks (no viewer changes), and
  the Windows oracle lane.
