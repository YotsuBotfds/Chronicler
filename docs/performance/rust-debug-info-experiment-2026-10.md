# Full Rust qualification with debug information disabled

The registered `CARGO_PROFILE_DEV_DEBUG=0` experiment passed the same full
1,088 tests, with two existing ignored cases, while its fresh target occupied
1,103,060,992 uniquely allocated bytes (1.03 GiB). The prior copied-cache
qualification target reclaimed 8,905,719,808 bytes (8.29 GiB) when removed.
That is an observed 87.6% smaller final allocation in these two workflows;
different cold/warm artifact sets limit attribution solely to debug information.
No timing speedup, changed default profile, production source change or installed
wheel change is claimed.

## Registered inputs and proof

The [preregistration](rust-debug-info-preregistration.md), commit `0efff387`,
preceded every compilation. The [runner](../../scripts/experiment_rust_debug_info.py)
was implemented in `5aa86e48`, then hardened in `da5bad47` following independent
review: terminal storage samples can reject an otherwise successful process,
and execution must retain the entire prepared compiler/linker environment.
Six focused harness tests passed in 0.13 seconds. Initial preparation 001 was
superseded without executing Cargo compilation; its receipt remains unchanged.
Fresh preparation 002 and the single actual full-suite experiment completed.

| Input | Recorded identity |
| --- | --- |
| Frozen source | `d051d7c06b1a490841d148b8906bde22f2f5d0f0` |
| Native crate tree | `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` |
| Cargo lock SHA-256 | `1a3fe8f890b8841f5be86059c5b6c276731c4009ef99d473ed5c7eb8858a2855` |
| Installed release, unchanged | `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317` |
| Compiler | rustc 1.99.1 (`58cf8f9c3`), LLVM 23.1.1 |
| Cargo | 1.99.1 (`5f94df478`) |
| PyO3 interpreter | Existing health environment, CPython 3.13.5 |
| Runner SHA-256 | `0763acb58a072e1bd6721f59ed3b74000ac2ac03b4c7dc28b3fa41812e9b42b3` |

Cargo metadata confirmed the one-crate workspace and the fresh external target.
No dev/test/custom profile or Cargo configuration override existed. The saved
official Cargo reference establishes that `test` inherits `dev`; metadata alone
was not treated as effective-profile proof. All prior recorded environment
settings matched except the explicit debug-info intervention and target path.
The original one-job, one-test-thread and linker-library settings were retained.

The build-only command compiled all targets without running tests. Its JSON
compiler-artifact records then verified all **40 local crate artifacts**,
including **36 test binaries**, before test execution:

| Setting | Effective value |
| --- | --- |
| Optimization level | 0 |
| Debug information | 0 |
| Debug assertions | enabled |
| Overflow checks | enabled |
| Features | default only; no jemalloc |

Verbose rustc commands and every dependency artifact record are retained too.
The original full test command then ran once and produced all 37 suite summaries,
1,088 passes, zero failures, zero filtered/measured cases and the same individual
test names/outcomes as the preserved baseline. The ignored cases remain
`regression_10k_24r_under_6s` and `regression_6k_24r_under_3s`; their release-mode
hardware timing budgets were not qualified here. Source, Cargo inputs/configs,
toolchain/Python/linker inputs, recorded environment and installed extension were
verified unchanged around both stages. No wheel was built or installed.

## Costs and storage limits

The experiment ran 20:24:52–20:28:25 UTC under two scholarship workers and the
lead's other bounded lane. Its isolated target started empty; no dependency or
native build cache was copied. The source registry/filesystem caches could be
warm. This differs materially from the baseline's copied warm dependency target.

| Measurement | Value |
| --- | ---: |
| Build-only command wall time, including monitor overhead | 184.356 s |
| Full test command wall time after verified build | 27.235 s |
| Sum of those two command stages | 211.591 s |
| Entire execution envelope, including identity checks | 213.583 s |
| Final unique allocated target bytes | 1,103,060,992 |
| Final apparent logical bytes across file names | 1,126,895,509 |
| Sampled peak unique allocated bytes | 1,103,060,992 |
| Sampled peak apparent logical bytes | 1,137,249,573 |
| Final files | 3,498 |
| Storage samples | 198 |
| Lowest observed filesystem free bytes | 9,691,140,096 |

Do not divide the baseline's 173.389-second combined command by these times to
claim a speedup or slowdown. Dependency reuse, shared load, distinct staging,
filesystem state and this experiment's monitoring differ. The approximately
one-second storage scans report sampled peaks, not instantaneous maxima or RSS;
command timing includes polling and inventory overhead. The baseline has a
post-completion cleanup-reclaimed measurement, not a matching sampled peak.
No peak-to-peak ratio or universal percentage saving is established.

Hard-linked files count once toward allocated storage and once per name toward
apparent logical storage. The largest retained individual files were:

| File or artifact | Logical bytes |
| --- | ---: |
| Native test incremental dependency graph | 53,776,413 |
| Development `libchronicler_agents.so` in isolated target | 46,732,992 |
| Native library incremental dependency graph | 41,772,464 |
| Native test incremental query cache | 34,382,474 |
| Arrow cast dependency rlib | 33,008,864 |
| Native unit-test executable | 15,325,176 |

The existing installed release is separate from that development `.so` and
retained its original digest. Neither the 2 GiB target allocation cap nor the
3 GiB free-space floor plus 512 MiB stopping reserve was approached. The monitor
checked terminal samples even after successful child exits; no guard stop,
compile failure or test failure occurred. Other workers' continuing output was
included in the free-space observation.

## Receipts and practical scope

Evidence resides outside Git at
`/workspace/chronicler-next-qualification-evidence/rust-debug0-d051-attempt-002`.
The completed generated target is
`/workspace/chronicler-build-rust-debug0-d051-attempt-002`. It is distinct from
all source checkouts, installed extensions, wheels and shared native build
targets. Retain or remove this exact target only through the lead's coordinated
artifact policy; evidence remains regardless.

| Artifact | SHA-256 |
| --- | --- |
| `prepare.json` | `0cccd5b683cc2bf47ac266bb128afb461f92325d452f3d4ab19881805a63d43e` |
| `experiment.json` | `9e7b494812bca4742b716946043d7f53bf3dd42df44e15146d3bfcb745d01355` |
| `effective-profiles.json` | `02af38a03758754b4bfe99393a540fa82afb50d188b7a7126260abe64c99c3aa` |
| `storage-samples.jsonl` | `735b0bf1c3dfd72004cf2ebecd369e9128807d187110c7540fb5c75b2482c51e` |
| Full test log | `ad46a425cf329648bcc555ec526d87ed6e9e0d77bb1a81d884140bd4769e459b` |

The evidence also retains exact commands, Cargo metadata, the public profile
reference, complete verbose compiler log/JSON messages and largest-file samples.
The previous qualification/cleanup receipts remain intact and hash-linked.

This qualifies the explicit debug-info-only setting for the tested full Rust
workflow at this source/platform while substantially reducing its observed
artifact burden. It does not qualify a fresh release extension, different source,
scientific behavior, native wheel compatibility or a profile-default rollout.
Keep symbol-rich builds available when diagnosing Rust failures; debug-info 0
reduces debugger/source-line detail. No existing build or test default changed.
