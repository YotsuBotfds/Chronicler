> Copied on 2026-11-09 from the implementer's scratch report (`scratchpad/identity/sd-COR-6/BASELINE.md`). Scratch paths below are not durable; the integrated-head check is in [the ledger](../streamline-and-deepen-ledger.md).

# COR-6 baseline: war event and casualty accounting

Date: 2026-11-08 (runs on 2026-11-09 UTC). Branch `sd/COR-6` from `sd/COR-10` (`165b58e`).
Class: correction (owner go-ahead 2026-11-08 for a, b and c; decision record
`docs/superpowers/progress/streamline-and-deepen-decisions.md`).

| Part | Commit | Status |
|---|---|---|
| COR-6a: flush events and military losses on the two early returns of `declare_or_press_war` | `cad9adb` | landed |
| COR-6b: non-roster casualties are the people actually drained | `677e537` | landed |
| COR-6c: `Army.natural_deaths` | none | **blocked**: `src/chronicler/models.py` (where `Army` is defined) is ENFORCED by five source-witness fixtures (`tests/fixtures/{food_accounting,household_candidate,livelihoods_cwr1,livelihoods_l0,regional_population}_source_inverse.json`); PIN-1 has not landed. Not started. |

## Changes

- **6a** `src/chronicler/war/runtime.py`: `declare_or_press_war` runs `reconcile_wars`, which can
  emit `war_ended` (`war/peace.py` `close_external`) or `war_declared` (`open_war`) into
  `ctx.events` (provenance has already observed them). The truce return and the
  "could not muster" return skipped `world.events_timeline.extend(ctx.events)` and
  `flush_military_losses(ctx)`. All three returns now call one helper `_publish(ctx)`
  (same two statements, same order as the old final path).
- **6b** `src/chronicler/war/armies.py` `apply_casualties`: the non-roster branch now uses
  `count = drain_population(...)`, so soldiers, casualties, attrition, the attribution note
  and the returned kill count follow the people actually drained (owner decision: soldiers
  die only if people were drained). `drain_population` drains `min(amount, population)`,
  so this differs only when the army's civ holds fewer people than the requested deaths.
- No Rust, serialization, enum, accumulator category or RNG call changed.

## Identities

| Side | Source | Native extension (sha256) |
|---|---|---|
| Before | `scratchpad/identity/sd-COR-10` (sd/COR-10 after-outputs, all 9 cases present) | `natives/sd-COR-10`, `59663c67744e52891bac8e20cac1562019fbef03440fa301a3f89624a8ea0bf2` |
| After 6a | `scratchpad/identity/sd-COR-6a`, worktree at `cad9adb` | same native (Rust unchanged) |
| After 6b (= branch head) | `scratchpad/identity/sd-COR-6`, worktree at `677e537` | `natives/sd-COR-6`: fresh `maturin develop --release --locked` build of this branch into `venvs/w2-c1`, byte-identical `59663c67...0bf2`; `check_python_env.py --expect native` PASS |

Runner: `~/.venvs/chronicler-native/bin/python scripts/turn_speed_identity.py run/compare`.
Field diff: `scratchpad/cor6/diffcases.py` (per-file sha256 with `generated_at` blanked,
events_timeline multiset diff by (turn, type, actors, description), war_state counters,
end civ stats).

## Sanity check before any edit

`off_s42` and `hybrid_s42` run from the start commit `165b58e` with the before native
(`identity/sd-COR-6-sanity`), compared with sd-COR-10: 9 + 111 files, **0 differences**.

## Compares (all 9 cases)

| Case | Files | 6a vs before | 6b (head) vs before |
|---|---|---|---|
| hybrid_s1234 | 10 | 0 | 0 |
| hybrid_s42 | 111 | 0 | 0 |
| hybrid_s7 | 111 | 0 | 0 |
| off_s42 | 9 | 0 | 0 |
| off_s7 | 9 | 0 | 0 |
| proc48_hybrid_s42 | 92 | 0 | 0 |
| proc48_off_s7 | 15 | 0 | 0 |
| scaled22k_s42 | 32 | 0 | 0 |
| scaled52k_s7 | 10 | 0 | 0 |
| **total** | **399** | **0** | **0** |

`diffcases.py` agrees: the only raw byte difference is `metadata.generated_at` in each
`chronicle_bundle.json`, which `turn_speed_identity` also ignores.

## Paired 40-seed batch (plan step 3 for PR 8 and PR 9)

Seeds 2101-2140 (template 8x4, 200 turns, `--agents off --simulate-only`, `PYTHONHASHSEED=0`).
Not in `scripts/seed_registry.json` and outside its restricted ranges; not registered
(development measurement, not a screen). Three source exports: `sd/COR-10`, `cad9adb`, `677e537`
(`scratchpad/cor6/batch-{base,a,b}`, summary in `batch-b/summary.json`).

| Metric (40 worlds) | before | after 6a | after 6b |
|---|---|---|---|
| bundles changed vs before | - | 0 / 40 | 0 / 40 |
| war_declared / war (action) events | 366 / 1543 | same | same |
| army_raised / army_destroyed / army_disbanded | 1033 / 645 / 364 | same | same |
| war_ended / peace_treaty | 50 / 266 | same | same |
| siege_begun / occupation / annexation / liberation | 433 / 207 / 138 / 64 | same | same |
| battles recorded / armies alive at end | 1180 / 23 | same | same |
| final civ military total | 833 | same | same |

No hybrid batch (6b's branch is reached only by armies without a roster, i.e. aggregate mode;
6a would apply in hybrid too but the 5 hybrid identity cases show 0 differences).

## Why there are no differences (path probe)

`scratchpad/cor6/probe.py` wraps `runtime._publish` and `armies.drain_population` (observe
only) on the after-source for the same 40 seeds:

- `declare_or_press_war` returns: truce 20, could-not-muster 26, final 304. **Pending
  reconciliation events at an early return: 0 of 46.** (Final path: 266 of 304 carried events,
  published as before.)
- `apply_casualties` non-roster drains: 1367 calls, **0 short** (requested deaths were always
  available in the civ's regions).
- off_s42 (300 turns) alone: 1 truce return (no events), 49 drains (0 short).

Four probe processes (seeds 2104, 2126, 2128, 2132) raised at the very end because the
parallel probes shared one working directory for the relative `output/` sidecar; the counters
are written in `finally` after the simulation finished, so their counts are complete. The batch
runs used one directory per seed and all exited 0.

## Interpretation

Both corrections are latent on these worlds: the conditions they fix (a war reconciled away
in the same call as a truce/no-muster return; a non-roster army whose civ has fewer people
than the deaths requested) did not occur in 9 identity cases or 40 paired worlds. The unit
tests construct both conditions and fail on the old code
(`tests/test_war_integration.py::test_truce_early_return_keeps_reconciliation_events`,
`::test_cannot_muster_early_return_keeps_reconciliation_events`,
`tests/test_war_armies.py::test_aggregate_casualties_follow_the_population_drain`).
No difference is unattributed. The destroyed-vs-demobilized verdict change belongs to 6c,
which is blocked, so it is not measured here (the 17% prior from
`docs/superpowers/roadmaps/connected-world-program.md:420` is still unmeasured).

Tests run: `.venv` (no native) `tests/test_war_{armies,battles,consequences,integration,logistics,occupation,peace,requisition}.py tests/test_attribution_records.py`: 168 passed, 4 skipped;
native venv `w2-c1` `tests/test_war_integration.py tests/test_war_armies.py`: 30 passed;
`tests/test_native_ci_shards.py`: 210 passed.

Not run: 200-seed gate, full oracle lane (lead), hybrid/native seed batch, Rust tests (no Rust change).
