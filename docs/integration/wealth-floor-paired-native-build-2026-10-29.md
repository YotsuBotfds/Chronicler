# Wealth-floor paired native build — 2026-10-29

The corrected paired build **passes the build prerequisite**. It reproduces the
original old native exactly and produces a distinct candidate in the same
recorded effective context. **Final baseline reuse and world execution remain
unqualified.** Candidate checkpoint/determinism proofs and outcome gates remain
separate; no simulation efficacy or speedup is established.

This [JSON readout](wealth-floor-paired-native-build-2026-10-29.json) is curated.
The full verification receipts are identified below; their complete member
inventories, private logs and binary payloads are not embedded here.

## Frozen producer and identities

[Run 40820753788](https://github.com/YotsuBotfds/Chronicler/actions/runs/40820753788), attempt 1, job
`123272420780` (`paired-native-build`), completed SUCCESS. Control source is
`3bf976cde1f0b4809945162395714e5aacccebdd` on
`lead/cloud-wealth-floor-native-build-bridge-2-20261029`. The activation ref stays
frozen; this readout lives on a separate docs branch.

| Identity | Baseline | Candidate |
| --- | --- | --- |
| Exact source | `d0281e5f57c508f27cea1676f36e0e6ed1225c9d` | `503070175e3e78d9014add158ead8f16ce940843` |
| Native crate tree | `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` | `93b32cd9b02eccf4900b33cdaeece08262be2330` |
| Native SHA-256 | `06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6` | `b56c43f16722be2c8fc6fbe5c021ec292f9a6856783d946af56d97e91575e619` |
| Wheel SHA-256 | `2e491456d01c2dd7bb2f7688e6acbc06b614610bbbe5be5ea6f0832ae220759a` | `4ebf720dfb1f39d4e19069cbadb44cfd60d1476874c41ec97dd19c69ae354d9a` |

The equal complete context SHA-256 is
`5aa8f0b521fe60666789ebc2ba058b9015df9104d1287a7bfa0e22caf22cc1ab`. Current unknowns are empty. Tool versions are
rustc/cargo 1.99.1, LLVM 23.1.1, maturin 1.15.0, uv 0.13.6 and CPython 3.13.17.
The original inherited flags, target overrides, linker/full argv and Ubuntu image
remain historically unknown; version matches alone do not establish reuse.

Manifest SHA-256: `dffb6aa2f07d89a23aad89a9988dd37f39f876cbff29c573838010cdbbb09169`. Positive completion
SHA-256: `442f58798e655f241290baa0020456e26107193f7d2ec5696549f6599460ce59`. The completion binds that manifest,
raw inventory `f9cdd8fddc3dcd8ae87815ff54d721e5dc7fa04fc3b7e15cba7b4e09842faf61` and light index
`221b28e582a3ad366f36c3f9b430a8eb52ea2c46f9503f3f0346d1793c1e4e81`. All source/control before-and-after snapshots
match. The JSON records exact archive paths and expiries.

| Artifact | ID | ZIP bytes | ZIP SHA-256 |
| --- | --- | ---: | --- |
| contracts | 12874783356 | 4,043 | `1182088bffbf25cfa2f9ab825fb97a3f92cfde9be97d89deed728c6a9906bb45` |
| light | 12874574280 | 702,101 | `a623ed545c8aabc1f19325a0884210c357d8d30ed903d703d79f21d30a29b759` |
| raw | 12874494535 | 9,041,361 | `fe23a7da31d04d7dd751937ba5050e953fa6a6597b865148bc11b559270b2ff9` |

All **85 raw + 17 light + 3 contract members** were checked. Lead review independently
streamed all 105 original members (15,764,010 bytes) and both inner native
payloads. The raw archive has an empty prefix; light copies use `light/` and the
completion is adjacent at `completion.json`.

## Executed checks and loader correction

Remote checks passed **182 guarded cases** (0.92 s) and **8 confined Linux
lifecycle cases** (2.52 s). Both isolated wheels exposed all three real compiled
classes and the registered schemas. The four genuine Rust regressions ran and
passed: preventing poor-balance utility amplification, preserving raw utility without additional wealth,
ordinary/threshold bit preservation, and credit-debit entry into the low-balance
case. Exact names remain in the curated JSON and original log.

First activation `75cb1771` / run `40818391220` / job `123264802829` is retained as
FAILURE. Both release builds/probes completed, then the compiled Rust test
executable exited 127 while loading `libpython3.13.so.1.0`; no assertion ran.
Candidate/control after-snapshots and positive completion were absent. Its wheels
were never rebound into the corrected producer.

The fix reads the exact selected interpreter's `sysconfig.LIBDIR` and
`LDLIBRARY`, validates canonical installation paths, and sets
`/opt/hostedtoolcache/Python/3.13.17/x64/lib` **only for the regression child**.
The observed library is 30,692,912 bytes, SHA-256
`5d82130178b6867f33842ba6c493f229d1d9ad3c8f302558298833c48b45c229`. Arbitrary inherited loader paths
are excluded; both release contexts retain `LD_LIBRARY_PATH: null`.

D2 records namespace equality as null/unverified after both PID1 namespace reads
return EACCES13. Its evidence scope does not attest namespace-invisible provider
ancestors. The resource helper and 12/2 GiB admission, 3/1 GiB running/final floors
remain unchanged.

## Named clocks and prospective options

| Recorded scope | Seconds |
| --- | ---: |
| Baseline release command, including cleanup | 301.390 |
| Candidate release command, including cleanup | 281.555 |
| Regression config query, including cleanup | 0.158 |
| Regression compile/run command, including cleanup | 107.993 |
| Controller wall after inventory and light hashing | 700.367 |
| Measured controller self CPU | 7.589 |
| Measured waited-child CPU | 692.683 |

The completion observation precedes its commit; a post-commit deadline/ownership
check and successful producer exit follow. These clocks have different scopes;
there is no exact aggregate live-tree CPU admission claim. Limits remain
30 minutes for the controller and 45 minutes for the job.

Two unimplemented options merit a separate measured study:

- Move the read-only selected-Python loader preflight before both release
  compilations, preserving the regression-only environment change.
- Retain verified unchanged Cargo dependencies while forcing a fresh candidate
  crate/link. Require native-byte equality with this cold reference and all
  provenance checks before accepting a speed claim.

Neither option has a measured benefit here; the qualifying cold-build protocol
is unchanged.

Full lane verification: `2eb25378086c3708dfbc8bf8754db4f3544f340831e347bda8d343589adab8c3`. Lead-qualified consumer
pins: `66fe4093ff1db5f5c63368a52655c2ea002644876a05f6bdf9ed75cd97bbf99d`. Independent metadata/seal peer:
`095cf3abd380889978995d1bba41b3a6c04b9a2de93f168e39dfd3fcb8637620`. The builder's
`historical_reuse_eligible` classification qualifies the binary bridge; root's
`baseline_reuse_qualified` and `world_execution_authorized` remain false.
