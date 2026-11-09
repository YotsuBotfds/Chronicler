# COR-8 baseline report (COR-8a, COR-8b, COR-8c)

Correction class. Owner go-ahead: the decisions of 2026-11-08 (DEC record; corrections started on
the lead's recommendation). Integrated in integration 9 of the
[ledger](../streamline-and-deepen-ledger.md).

Provenance of this report: the implementers' scratch `BASELINE.md` files were removed in a
disk cleanup after the merge. This report is assembled from their recorded results in the workflow
journal and from the lead's own integration-9 run, which repeats the before/after comparison on
the merged head.

| Part | Reviewed head | Change | Before → after | Result |
|---|---|---|---|---|
| COR-8a | `584acd06` | `src/chronicler/ecology.py` gets explicit `hills` and `river` rows in `TERRAIN_ECOLOGY_DEFAULTS` and `TERRAIN_ECOLOGY_CAPS`, equal to `plains` (Rust maps both labels to plains through `ffi_constants.TERRAIN_MAP`). Python lookups already fell back to plains. | base2 (integration 5, native `d79f483d…`) → `sd/COR-8a` | 9 cases, 399 files, **0 differences**. `proc48_hybrid_s42` has 6 hills regions and `proc48_off_s7` has 4, so the rows ran on both ecology paths. No generator emits `river`; it is covered by unit tests only. |
| COR-8b | `9ef19e11` | `src/chronicler/tuning.py` gains `DEPRECATED_UNREAD_KEYS` (the eight spec keys plus `culture.culture_projection_threshold`, unread since DEAD-2a). `load_tuning` warns once per deprecated key present and still loads it. `K_*` constants and `KNOWN_OVERRIDES` stay. | `sd/COR-8a` → `sd/COR-8b` | 9 cases, 399 files, **0 differences**. A targeted `off_s42` run that sets all nine keys to extreme values changes no simulation field against a neutral tuning file; only the stored `tuning_overrides` and `generated_at` differ. |
| COR-8c | `a4ae368b` | Test only: `tests/test_economy_bridge.py::test_tithe_constants_match_rust_economy` checks Rust `TITHE_RATE`/`TITHE_FOOD_GATE` against `factions.TITHE_RATE` and the single `economy.py` gate literal. | `sd/COR-8b` → `sd/COR-8c` | No source change; 9 cases, 399 files, **0 differences**. |

Identity gate on each part: Python lane 3 cases, 53 files, 0 differences; native lane 6 cases,
133 files, 0 differences. No goldens were re-captured.

Finding recorded for later, not changed by COR-8b: any `--tuning` file, even one that sets a key
to its default (`multiplier.aggression_bias: 1.0`), makes `off_s42` diverge from a run without
`--tuning`, from the action history onward. This predates COR-8. It is board item FIX-14
(investigation; a fix would be a correction).

Not run: the 200-seed gate; a `river` world (no generator produces one); a mutated Rust tithe
constant against the COR-8c test.
