> Copied on 2026-11-09 from the implementer's scratch report (`scratchpad/identity/sd-COR-10/BASELINE.md`). Scratch paths below are not durable; the integrated-head check is in [the ledger](../streamline-and-deepen-ledger.md).

# COR-10 baseline: gp_agendas projected treasury respects the accumulator watermark

Date: 2026-11-08 (runs on 2026-11-09 UTC). Branch `sd/COR-10` from `sd/COR-9` (`d294ff7`).
Fix commit `165b58e`. Class: correction (owner go-ahead 2026-11-08).

## Change

`src/chronicler/gp_agendas.py::_projected_treasury` summed every `keep` treasury change
in `acc._changes`. In hybrid mode `tick_gp_agendas` runs in Phase 10 with `acc`, after
`acc.apply_keep(world)` has already written the Phases 1-9 keep changes into
`civ.treasury`, so those changes were counted twice. It now starts at
`acc._keep_applied_up_to`, as `war/common.projected_treasury` and
`diplomacy._projected_treasury` do (unfloored, same int arithmetic otherwise).
Agents-off runs pass `acc=None` to `tick_gp_agendas` (`phase10_acc` is `None` outside
hybrid), so the aggregate path cannot change. The projection gates two decisions:
founding a trading house (`>= 2 * TRADING_HOUSE_COST`) and a prophet's temple
commission (`>= cost`). No Rust, serialization, enum, accumulator category or RNG call
changed.

## Identities

| Side | Source | Native extension (sha256) |
|---|---|---|
| Before | `scratchpad/identity/sd-COR-9` (sd/COR-9 after-outputs, all 9 cases) | `natives/sd-COR-9`, `59663c67744e52891bac8e20cac1562019fbef03440fa301a3f89624a8ea0bf2` |
| After | `sd/COR-10` worktree at `165b58e` | same native (Rust unchanged). A fresh `maturin develop --release --locked` build of this branch into `venvs/w2-c1` is byte-identical (`59663c67...0bf2`), copied to `natives/sd-COR-10`. |

Runner: `~/.venvs/chronicler-native/bin/python scripts/turn_speed_identity.py`
(`PYTHONHASHSEED=0`, `RAYON_NUM_THREADS=1`).

## Sanity check before any edit

`off_s42` and `hybrid_s42` rerun from `git archive sd/COR-9 src` with the before native
(`identity/sd-COR-10-sanity`), compared with the sd-COR-9 outputs: 9 + 111 files,
**0 differences**.

## After compare (all 9 cases)

| Case | Files | Differences |
|---|---|---|
| hybrid_s1234 | 10 | 0 |
| hybrid_s42 | 111 | 0 |
| hybrid_s7 | 111 | 0 |
| off_s42 | 9 | 0 |
| off_s7 | 9 | 0 |
| proc48_hybrid_s42 | 92 | **76** |
| proc48_off_s7 | 15 | 0 |
| scaled22k_s42 | 32 | 0 |
| scaled52k_s7 | 10 | 0 |
| **Total** | **399** | **76** (one case) |

## Which decisions the correction flips

`scratchpad/cor10/shadow_runner.py` reruns a case with `_projected_treasury` wrapped to
record the new (watermark) and old (all keep changes) value and the caller's threshold;
it returns the new value, and its outputs are byte-identical to the after run
(`state.json` checked for proc48_hybrid_s42 and hybrid_s7).

| Case | Calls | new != old | new > old | new < old | Gate flips |
|---|---|---|---|---|---|
| off_s42 | 25 | 0 | 0 | 0 | 0 (acc is None) |
| hybrid_s1234 | 1 | 1 | 0 | 1 | 0 |
| hybrid_s42 | 5 | 5 | 4 | 1 | 0 |
| hybrid_s7 | 37 | 37 | 10 | 27 | 0 |
| proc48_hybrid_s42 | 79 | 74 | 40 | 34 | **9** |

The double count went both ways (already-applied income inflated the projection,
already-applied costs deflated it). Only proc48_hybrid_s42 crosses a threshold, which
is exactly the one case whose outputs differ. Its flips (turn, civ, gate, threshold,
old -> new): 33 civ 6 temple 10, 4 -> 12; 40 civ 6 temple 10, 0 -> 21; 50 civ 1 house
30, 42 -> 21 (now refused); 50 civ 2 temple 9, -16 -> 12; 50 civ 6 house 30, 19 -> 35;
51 civ 6 house 30, 1 -> 32; 55 civ 6 house 30, 18 -> 33; 145/146 civ 5 house 30, 13 -> 39
and 18 -> 36. 8 now allowed, 1 now refused. (Flips after turn 33 are on the corrected
trajectory.)

## Field-level diff of proc48_hybrid_s42 (`scratchpad/cor10/field_diff.py`)

- Differing files: `chronicle_bundle.json`, `state.json`, `state.historiography.json`,
  `state.languages.json`, `agent_events.arrow`, 10 `memories_*.json`, the 5 validation
  arrows/summary JSONs, and 53 per-turn `validation_summary/*_turn_NNN.json` files: every
  per-turn file from turn 040 on; turns 000-030 are identical.
- Events: identical through turn 32 (1,154 events before turn 33). First differing event
  is index 1192, turn 33: the after run has `shrine_commissioned` (Elder Chejadar,
  Khubukani Republic = civ 6, Merilion Weald), the temple the first flip allows (real
  treasury 12 >= cost 10; old projection 4). Everything later is the cascade of that and
  the later flips (agent tick, migration, wars).
- Totals: 8,191 -> 8,198 events (multiset: 5,326 removed, 5,333 added).
  `trading_house_founded` 5 -> 16, `agenda_fulfilled` 32 -> 46, `agenda_declared`
  76 -> 86, `agenda_failed` 38 -> 37, `build_started` 129 -> 152, `war` 78 -> 51.
  gp_agendas state counts: trading_houses 5 -> 16, shrines 14 -> 14,
  fulfilled:found_trading_house 5 -> 16.
- Bundle sections that differ: events_timeline, history_delta, world_state,
  historiography, languages, named_events, metadata (run totals). Identical:
  chronicle_entries, era_reflections, gap_summaries, pruned_civ_stats.
- `state.json`: 73,932 differing leaf paths, led by events_timeline, retired_persons,
  civilizations, named_events, agent_movements, provenance, contact_ledger; final civ
  region counts change for 5 of 10 civs. No key added or removed from the schema.

## Interpretation

All 76 differences come from one case whose first divergence is the turn-33 temple
commission that the watermark fix allows; the 8 other cases, including the three
hybrid 200-turn cases where the projection value changed 43 times without crossing a
threshold, are byte-identical. No difference is unattributed. Off-mode cases cannot
change and do not.

## Not run

- 200-seed before/after gate (milestone qualification).
- Per-switch identity matrices (`--cities --guilds`, `--finance`, ...): gp_agendas is
  default-on, so the default cases exercise the change.
- Full oracle lane (lead runs it).
