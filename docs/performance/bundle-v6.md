# The history as changes between snapshots (bundle version 6)

Branch `perf/bundle-headroom`, from `main` `ea08126` (PR #34). This changes
the viewer bundle file only. The simulation, its RNG draws, `state.json`, the
sidecars, `chronicle.md`, the memories, `agent_events.arrow` and the
snapshots handed to `on_turn` callbacks are unchanged. No Rust code changed.
Decoded, a version-6 bundle is the version-5 bundle: the same values, number
types and key order.

## Problem

`tests/test_bundle.py::TestBundleSize` (seed 1, 500 turns, 10 regions, 5
civs, agents off, the defaults) guarded the bundle at 24 MB. After PR #34
the world wrote 21.55 MiB on the native runtimes and 22.67 MiB on the
Python (no-Rust) path. Every new system adds a per-turn field, and more
civilizations alive at once make the per-civ rows and pair tables longer, so
the next system would have broken the guard.

## Where the bytes were

Version-5 size-guard bundle, by top-level field:

| Field | No-Rust MiB (share) | Native MiB (share) |
| --- | --- | --- |
| `history` | 15.87 (70.0%) | 15.63 (72.5%) |
| `world_state` | 3.21 (14.2%) | 2.81 (13.1%) |
| of which `events_timeline` and `named_events` | 2.72 | 2.37 |
| `events_timeline` | 2.43 (10.7%) | 2.11 (9.8%) |
| `historiography` | 0.61 (2.7%) | 0.49 (2.3%) |
| `named_events` | 0.29 (1.3%) | 0.26 (1.2%) |
| `languages` | 0.18 (0.8%) | 0.17 (0.8%) |
| `chronicle_entries` | 0.07 (0.3%) | 0.07 (0.3%) |
| Total | 22.67 | 21.55 |

`world_state.events_timeline` and `world_state.named_events` were the same
lists as the top-level fields, written twice.

History fields summed over the 500 snapshots. "Unchanged" is the share of the
field's bytes in snapshots where the whole field equals the previous one;
"v6" is what the field's patches take in the new file:

| Field | No-Rust MiB (share) | unchanged | v6 | Native MiB (share) | unchanged | v6 |
| --- | --- | --- | --- | --- | --- | --- |
| `civ_stats` | 5.60 (24.7%) | 0% | 1.35 | 5.43 (25.2%) | 0% | 1.27 |
| `diplomacy` | 1.90 (8.4%) | 0% | 0.77 | 1.95 (9.1%) | 0% | 0.72 |
| `techniques` | 1.20 (5.3%) | 0% | 0.43 | 1.22 (5.7%) | 0% | 0.41 |
| `proxy_wars` | 1.03 (4.5%) | 0% | 0.20 | 0.90 (4.2%) | 0% | 0.17 |
| `finance` | 0.91 (4.0%) | 0% | 0.36 | 0.91 (4.2%) | 0% | 0.37 |
| `perception_errors` | 0.85 (3.8%) | 0% | 0.64 | 0.81 (3.7%) | 0% | 0.57 |
| `relationships` | 0.66 (2.9%) | 50% | 0.05 | 0.63 (2.9%) | 37% | 0.06 |
| `per_pair_accuracy` | 0.42 (1.9%) | 48% | 0.05 | 0.39 (1.8%) | 57% | 0.04 |
| `movements_summary` | 0.39 (1.7%) | 80% | 0.01 | 0.39 (1.8%) | 83% | 0.01 |
| `maritime` | 0.35 (1.6%) | 10% | 0.04 | 0.38 (1.8%) | 0% | 0.04 |
| `contact` | 0.35 (1.5%) | 0% | 0.22 | 0.37 (1.7%) | 0% | 0.22 |
| `ecology` | 0.31 (1.3%) | 0% | 0.13 | 0.41 (1.9%) | 0% | 0.19 |
| `campaign` | 0.30 (1.3%) | 8% | 0.11 | 0.25 (1.2%) | 9% | 0.09 |
| `nomads` | 0.29 (1.3%) | 89% | 0.00 | 0.28 (1.3%) | 89% | 0.00 |
| `region_cultural_identity` | 0.19 (0.9%) | 97% | 0.00 | 0.19 (0.9%) | 99% | 0.00 |
| `region_control` | 0.19 (0.8%) | 97% | 0.00 | 0.19 (0.9%) | 97% | 0.00 |
| Other fields | 0.89 | | 0.17 | 0.90 | | 0.17 |

What grows with civilizations alive times turns: `civ_stats` (5.56 rows per
snapshot no-Rust, 5.46 native, about 2 KiB a row; `governance` alone is 2.46
and 2.43 MiB), the pair tables (`relationships`, `per_pair_accuracy`,
`perception_errors`, `diplomacy.pairs`, about civs squared a turn) and the
per-civ system rows (`finance.civs`). What repeats: whole fields such as
`region_control`, `capitals`, `federations`, `cities` and `nomads` most turns,
and inside the rows that change, most of the row. In `civ_stats`, `traditions`,
`folk_heroes`, `regions`, `capital_region`, `federation_name`, `tech_era` and
the boolean flags are unchanged from the previous snapshot in 95-99% of rows;
`governance`, `action_counts`, `war_weariness` and `treasury` change in most.

## The format

Version 6 (`src/chronicler/bundle_codec.py`) keeps `chronicle_bundle.json`
plain JSON:

- `history_delta` replaces `history`. Item 0 is the first snapshot; each later
  item is a patch against the snapshot before it.
- `world_state.events_timeline` and `world_state.named_events` are `null`
  when they equal the top-level `events_timeline` and `named_events`.

A patch of a value `a` (the previous snapshot's) into `b`:

| Patch | Meaning |
| --- | --- |
| an object, against an object | only the changed and new keys, each a patch of the old value (a new key holds its value); `"~d"`: removed keys; kept keys keep their order and new ones follow, `"~o"` gives the full order when it differs |
| `{"~l": [[i, patch], ...]}`, against a list | the changed items; `"~t"`: appended items, `"~n"`: the new, shorter length. A list cheaper to write whole is written whole |
| `{"~r": value}` | `value` itself, where a literal object would read as a patch (a list replaced by an object) |
| anything else | the new value |

An unchanged snapshot is `{}`. The encoder compares strictly (1, 1.0 and
`true` differ, as do key orders and `-0.0` and `0.0`), so decoding restores
the version-5 text byte for byte. Decoded snapshots are separate JSON trees
in Python; the viewer shares unchanged values between consecutive snapshots
and does not mutate them. A history with a reserved key (`~d`, `~o`, `~r`,
`~l`, `~t`, `~n`) anywhere is written whole as `history`; no current field
has one.

`assemble_bundle` still returns the decoded layout, with `bundle_version` 6;
`write_bundle` encodes it. Pruning (version 5) still applies before encoding.
Live-mode turn messages are unchanged.

Not done:

- Rounding floats to the viewer's precision. The validation oracles and
  narration read these values, and the bundle would stop decoding to the
  version-5 one; the lossless changes already restore the headroom.
- The event timeline. It is now the second field (28% of the size-guard
  file, 39% of the procedural one below): 17,565 events there, whose repeated
  keys and default values (`"shock_region":null`, `"consequences":[]`,
  `"source":"aggregate"`) take about as much as their descriptions. A
  columnar layout would be the next saving; every event reader in the viewer
  would have to change.
- Interning strings, and compression (gzip at level 6 would give 1.10 MiB
  native, against 2.47 MiB for version 5; nothing reads gzip).

## Savings

Each change alone, on the version-5 bundles:

| World | Version 5 | `world_state` copies dropped | History deltas | Version 6 |
| --- | --- | --- | --- | --- |
| Size guard, no-Rust | 23,769,889 (22.67 MiB) | -2.72 MiB (12.0%) | -11.33 MiB (50.0%) | 9,029,934 (8.61 MiB), -62.0% |
| Size guard, native | 22,594,862 (21.55 MiB) | -2.37 MiB (11.0%) | -11.28 MiB (52.4%) | 8,276,564 (7.89 MiB), -63.4% |
| Hybrid, seed 42, 8 regions x 4 civs, 300 turns, every switch on | 7,878,401 (7.51 MiB) | -0.90 MiB (11.9%) | -3.56 MiB (47.4%) | 3,203,064 (3.05 MiB), -59.3% |
| Procedural 48 x 10 hybrid, seed 42, 300 turns, every switch on | 34,839,386 (33.23 MiB) | -5.84 MiB (17.6%) | -12.67 MiB (38.1%) | 15,430,726 (14.72 MiB), -55.7% |

"Every switch on" is `--mutual-aid --fisheries --campaigns --governance
--contact-ledger --epidemiology --finance --diplomacy --techniques --maritime
--gp-agendas --nomads --cities --agent-movements --historiography
--languages`.

In version 6 the size-guard file is `history_delta` 4.53 MiB (52.7%),
`events_timeline` 2.43 (28.3%), `historiography` 0.61, `world_state` 0.49,
`named_events` 0.29 and `languages` 0.18 (no-Rust). The largest patches
are `perception_errors` (0.62 MiB: every pair's errors change every turn),
`civ_stats.governance` (0.43), `techniques.regions` (0.41), `diplomacy.pairs`
(0.39), `finance.civs` (0.34) and `diplomacy.top_grievances` (0.30).

Encoding the size-guard history takes about 0.8 s and decoding about 0.6 s
(Python); the viewer decodes on load.

The size guard is tightened from 24 to 10.5 MB, about 20% above the no-Rust
size.

## Readers

| Reader | Change |
| --- | --- |
| `bundle_codec.load_bundle`, `decode_bundle` | new: read any version, decoded |
| `snapshot_pruning.restore_bundle` | decodes first, so validation (`validation_io._load_bundle`), batch analytics (`analytics.load_bundle_records`), narration (`main._run_narrate`), `run_oracle_gate.py`, `epidemiology_stats.py` and `m_af1_compare.py` read version 6 unchanged |
| live mode (`_validate_legacy_live_bundle`) | decodes before validating; the viewer receives the decoded bundle |
| `scripts/third_wave_controls.legacy_artifact_bytes` | a version-6 file decodes and projects as version 5, so the live artifact oracle (`corrected_artifacts_farmland_2026_10.json`) is unchanged |
| scripts reading `history` (`agent_movements_identity`, `cities_identity`, `viewer_systems_identity`, `provenance_identity`, `diplomacy_report`, `techniques_report`, `finance_census`, `nomads_report`, `m53_baseline`, `build_viewer_systems_fixture`, `prune_dead_civ_snapshots check`) | `load_bundle` |
| `scripts/generate_viewer_fixture.py` | writes the fixture decoded, as the viewer's tests import it |
| byte-identity scripts (`diplomacy_identity` and the like) | unchanged: they compare canonical JSON, which works between two version-6 runs; across the format change the bundle differs and `scripts/bundle_v6.py compare` checks it |
| viewer (`viewer/src/lib/bundleCodec.ts`) | `classifyParsedBundlePayload` decodes before its key check, for files and live `bundle_loaded` messages |

`scripts/bundle_v6.py` converts bundles in place (`convert`, version 4 is
pruned first), writes the decoded layout for other tools (`decode`), compares
two bundles or run directories once decoded (`compare`, ignoring
`generated_at` and `bundle_version`) and prints the breakdown above
(`breakdown`).

Older bundles load unchanged in Python and in the viewer. A version-5 or
older viewer rejects a version-6 file with "Missing required keys: history"
rather than misreading it.

## Evidence

Linux, Python 3.13.17. Native lane: the extension built from this tree with
`maturin develop --release` (`AgentSimulator`, `EcologySimulator` and
`PoliticsSimulator` real classes; extension SHA-256 `21344bb6...02ef`, the one the
ledger records for `84bfb44`). No-Rust lane: a separate environment
without `chronicler_agents`. Base runs used an exported copy of `ea08126`'s
tree; all runs set `PYTHONHASHSEED=0`. Without it the size-guard world writes
the same sizes on both lanes (equal once decoded; `generated_at` differs).

**Identity.** For the size-guard world on both lanes, the small hybrid world
and the procedural world, `scripts/diplomacy_identity.py compare BASE NEW`
finds every file byte-identical except `chronicle_bundle.json` (`state.json`,
the historiography and languages sidecars, `chronicle.md`, the memories and
`agent_events.arrow`), and `scripts/bundle_v6.py compare BASE NEW` finds the
bundles equal once decoded. Decoding each version-6 bundle gives the base
bundle text byte for byte, apart from `generated_at` and `bundle_version`.
On the golden workloads, the artifact oracle's version-5 and pre-pruning
projections of the new bundles match the frozen hashes
(`tests/test_governance_dormancy.py`, `tests/test_historiography.py`).

**Fixtures.** `viewer/src/__fixtures__/cities_bundle_v6.json` is what
`write_bundle` writes for the cities fixture at version 6 (240,058 -> 66,352
bytes); a Python test checks it byte for byte and a viewer test decodes it
to the cities fixture. `systems_bundle.json` moves to version 6 (only
`bundle_version` changes; its layout is the decoded one).

**Tests.**

| Lane | Base (ledger, `84bfb44`; `ea08126` adds docs and a test comment) | Branch |
| --- | --- | --- |
| `pytest -m "not slow" -n 2` (native build) | 6,141 passed, 3 skipped | 6,163 passed, 3 skipped |
| `pytest -m slow -n 2` | 11 passed, 3 skipped | 11 passed, 3 skipped (the size guard at < 10.5 MB included) |
| No-Rust environment, `pytest -n 2`, no marker filter | 5,918 passed, 226 skipped | 5,940 passed, 226 skipped |
| `scripts/run_python_oracle_checks.py` | 2,102 passed, 28 skipped | 2,124 passed, 28 skipped; PASS in 76.6 s, largest chunk 29.5 s of 110 s; no native module loaded |
| Viewer `npm test -- --maxWorkers=2` | | 280 tests, 37 files (4 new in `bundleCodec.test.ts`) |
| Viewer `npm run lint`, `npm run build` | pass | pass (existing large-chunk warning) |

The 22 new Python cases are `tests/test_bundle_codec.py`, added to the oracle
lane's `systems-2` chunk. Base counts are the ledger's; they were not rerun.
No Rust code changed, so `cargo test` was not run.

**Browser.** Headless Chromium (Playwright) on the production build
(`vite preview`) opened the version-6 and version-5 size-guard bundles
(no-Rust) and the procedural hybrid pair. On the Overview, Character, Trade
and Campaign surfaces (full page) and the Diplomacy, Finance, Techniques and
Governance panels (plus Food, Cities, Wars and Maritime for the procedural
pair), at the first, middle and last turn, the two versions render the same
DOM once Recharts' generated clip-path ids are normalized. Screenshots are
identical except a few chart panels whose pixels vary from run to run with
identical DOM. No console errors or warnings.
