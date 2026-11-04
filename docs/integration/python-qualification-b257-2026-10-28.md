# Frozen b257 full-Python qualification — 2026-10-28

Both complete Python suites passed on the clean, unchanged source
`b25727e36eb47513a6bd7b3209f15de9c14463c3`. Their original typed receipts
accepted the executions directly, without reruns or reader adjudication.

| Lane | Passed parent tests | Skipped | Successful subtests | Pytest duration | Completed UTC |
| --- | ---: | ---: | ---: | ---: | --- |
| Native / fb20 | 7,645 | 6 | 526 | 1,051.09 s | 21:28:10.850849 |
| No-native | 7,331 | 306 | 526 | 785.41 s | 21:24:38.667457 |

Both raw pytest exit statuses were zero, with no failures or errors. Subtests
are separate from parent tests. Shared host load and recorded pre-test pauses
make these qualification durations unsuitable for speedup claims.

## Source and runtime boundary

The frozen source includes the default-off expansion systems, funded-context
publication, chronology corrections, inactive craft-work limits, bounded
receipt readers and their malformed-input fixes, health-censor reader
compatibility, CI scheduling, and the typed pre-test cancellation tool.
The unpromoted household Rust optimization and proposed recurrent science
agendas are excluded.

Both lanes used Linux/x86-64, CPython 3.13.5, explicit frozen checkout/root
import paths, `PYTHONHASHSEED=0` and recorded one-thread numerical/native
settings. Every tracked source hash, interpreter/dependency identity and
thread setting matched before/after. The no-native interpreter verified
`chronicler_agents` absent. The native lane verified the compiled simulator
classes and unchanged release extension SHA-256
`fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317`.
Its crate tree remains `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`, qualified
separately by the [full Rust checks](rust-qualification-d051-2026-10.md).

The copied supervisor used by both lanes has SHA-256
`cc8c2982b94ee1fcf0ac99aac84d8813ac5faaca3792c1ae66bbc91ee37ef961`.
Native JUnit contains 7,651 parent cases and declares 8,177 tests; no-native
contains 7,637 parent cases and declares 8,163. In each lane the excess is
exactly the terminal summary's 526 successful pytest 9 subtests. Serialized
failures/errors are zero, and serialized skip counts match the table.
The reader requires this exact reconciliation; it does not waive mismatches.

## External evidence identities

Evidence is retained beneath
`/workspace/chronicler-current-qualification-evidence/`, outside Git.
Each result links its request, copied supervisor, complete source/runtime
inventories, pytest command, pre-test pause interval, log and JUnit hashes.
Root independently rechecked the artifact hashes, raw XML counts, terminal
summaries and source/runtime equality.

| Artifact | SHA-256 |
| --- | --- |
| `native-full-b257-fb20/result.json` | `5a487b9203dba0e4e7f930ffd705b7756ae95aa671c8a86cad0d59a2c7a5ec63` |
| `native-full-b257-fb20/pytest-junit.xml` | `b5a149469342e7965742225ecbc275e3a94ff7a77b7b4fea75eaf67991319de9` |
| `native-full-b257-fb20/pytest.log` | `3cf998f3817789ad71372ebdc05f1a4f6f108c381481b13241bc3845ac49c935` |
| `no-native-full-b257/result.json` | `6932dd36b08a45a4d675c0d09b01c2c904072f4e39a13be8c74a816029372e4e` |
| `no-native-full-b257/pytest-junit.xml` | `5513782616283930fe118353a915344984ef270e4e768960bb297357b143f7bd` |
| `no-native-full-b257/pytest.log` | `f7452248a214d069464d036426d299dbbd246f72c0f73a361aa5482f68097549` |

The native pre-test pause resumed at 21:10:35.632235 UTC; no-native resumed
at 21:11:29.302445. Neither lane was paused inside pytest. The preserved older
collection failures, interruptions and reader-only adjudications keep their
original outcomes; these are new complete executions at the newer source.

## Complete offline selection at the same source

The separate offline run also passed: **28/28 chunks, 3,556 passed, 65 skipped,
zero failed**, in 237.7028 seconds. Every guard passed. The largest chunk,
`systems-2`, took 48.5574 seconds against the unchanged 110-second limit.
Full source/runtime inventories matched before/after, the extension was
absent, and independent completion verification found no live owned wrapper,
oracle or pytest processes. Completion was 21:33:26.637762 UTC.

External evidence lives in `offline-b257-20261028/` beneath the same root:

| Artifact | SHA-256 |
| --- | --- |
| `oracle/receipt.json` | `e3cd96201a46f09a767dfa65d8f9452d8438377ac96a73a35cbd116b70bd1c09` |
| `result.json` | `db84dc26d71e8a7f60a81f43ddf3edf7fc731e9153e4f93cc610a4a1a6adbdfb` |
| `verified-completion.json` | `6dbc43dbccffbd2980d7cc2d36f7b680ee27d3c3e5baab28909853cfd73154c7` |

This is the complete bounded offline selection, not native execution or the
full POSIX/subprocess suite. Subsequent lifecycle-audit definitions and their
selection update have separate focused checks; they are outside frozen b257.

## Limits

These results qualify Python mechanics at the named source on this host.
They establish no natural-world efficacy, balance, population scaling,
cross-platform execution or remote CI result. The long before/after population
gates remain separate and pending. Main remains untouched, and later
branch commits do not inherit a full-suite pass without their relevant checks.
