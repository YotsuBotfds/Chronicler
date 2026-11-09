> Copied on 2026-11-09 from the implementer's scratch report (`scratchpad/identity/sd-COR-9/BASELINE.md`). Scratch paths below are not durable; the integrated-head check is in [the ledger](../streamline-and-deepen-ledger.md).

# COR-9 baseline: Rust `stable_hash_int` repr parity

Date: 2026-11-08 (UTC run ended after midnight). Branch `sd/COR-9` from `5eedc67`. Class: correction.

## Identities

| Side | Source | Native extension (sha256) |
|---|---|---|
| Before | `4e8e76b` (source-identical to `5eedc67` under `src/` and `chronicler-agents/`) | `scratchpad/base-native/chronicler_agents`, `2125dfd7b5f9e2091ac70fad5f08709c14d2e553ab65691f7638d219e9c22641` |
| After | `sd/COR-9` worktree at `d294ff7` | `scratchpad/natives/sd-COR-9/chronicler_agents`, `59663c67744e52891bac8e20cac1562019fbef03440fa301a3f89624a8ea0bf2` (release, `maturin develop --release --locked`) |

Runner: `~/.venvs/chronicler-native/bin/python scripts/turn_speed_identity.py`.

## Sanity check before any edit

`off_s42` and `hybrid_s42` rerun from `5eedc67` with the before native, compared with
the base outputs: 111 + 9 files, **0 differences**. The base outputs reproduce.

## After compare (all 9 cases)

| Case | Files | Differences |
|---|---|---|
| hybrid_s1234 | 10 | 0 |
| hybrid_s42 | 111 | 0 |
| hybrid_s7 | 111 | 0 |
| off_s42 | 9 | 0 |
| off_s7 | 9 | 0 |
| proc48_hybrid_s42 | 92 | 0 |
| proc48_off_s7 | 15 | 0 |
| scaled22k_s42 | 32 | 0 |
| scaled52k_s7 | 10 | 0 |
| **Total** | **399** | **0** |

## Field-level check

`scratchpad/cor9/field_diff.py` decodes every JSON output without normalisation.
The only field that differs is `chronicle_bundle.json` `$.metadata.generated_at`
(one per case, 9 in all), a wall-clock timestamp that `turn_speed_identity compare`
normalises. No event, verdict, stat or state field differs: events added 0, removed 0,
verdicts changed 0.

The same script collected every civilization name in the outputs: **37 distinct names,
0 whose Python `repr` differs from the old Rust `'name'` quoting**. Scenario YAMLs
(`scenarios/*.yaml`) contain no civ name with `'` or `\`. So the fixed seeds are
byte-identical for every civ in these runs, which is why the outcome is unchanged.

## Where the correction does change outcomes

Scratch end-to-end check (`scratchpad/cor9/secession_e2e.py`): one civ at stability 0
with 5 regions, turn 100, seeds 0..299, Python `check_secession` vs Rust
`PoliticsSimulator` breakaway op.

| Name | Python fires | Rust before (agree) | Rust after (agree) |
|---|---|---|---|
| `Aldor` | 39 | 39 (300/300) | 39 (300/300) |
| `Ka'lo` | 17 | 32 (255/300) | 17 (300/300) |
| `A\B` | 23 | 30 (249/300) | 23 (300/300) |
| `He said "hi"` | 32 | 32 (300/300) | 32 (300/300) |

Before the fix Rust and Python disagreed on 45 and 51 of 300 seeds for names that need
escaping; after it they agree on all 300 for every name. Names that need no escaping
(including ones with `"` only) are unchanged.

## Interpretation

The correction changes Rust politics RNG only for civ names containing `'`, `\` or
control characters (secession, vassal rebellion, proxy detection, restoration). No such
name occurs in generated worlds or bundled scenarios, so all 9 identity cases are
byte-identical. Out of scope: non-ASCII characters CPython treats as non-printable other
than C1 controls (for example U+00A0, U+200B) still hash differently.

Not run: 200-seed before/after gate; full offline oracle lane (lead runs it).
