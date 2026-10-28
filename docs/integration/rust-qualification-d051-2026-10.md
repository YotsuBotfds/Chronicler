# Full receipt-crate Rust qualification, 2026-10-28

Frozen source `d051d7c06b1a490841d148b8906bde22f2f5d0f0` passed the complete
locked Rust test invocation: **1,088 passed, 0 failed, 2 ignored, 0 filtered**,
across 37 suite summaries. This qualifies the receipt crate's Rust tests; it
is distinct from the earlier 13 focused receipt/maritime cases and the previous
health crate's 1,081-test result.

## Source, compiler and installed release

| Identity | Value |
| --- | --- |
| Repository tree | `90d43b78ee4d49279681dbce66ea55f61da58696` |
| Native crate tree | `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` |
| Python package digest | `c14bc2f0178139b58d778926e1f803597ee0856958b02da67882b851845c8129` |
| Cargo.lock SHA-256 | `1a3fe8f890b8841f5be86059c5b6c276731c4009ef99d473ed5c7eb8858a2855` |
| Installed receipt extension SHA-256 | `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317` |
| Matching release wheel SHA-256 | `bf7dbf627e61ab5333dd20b8940770840c9742413439975b3777fa73c77b4c1f` |
| Toolchain | `stable-x86_64-unknown-linux-gnu` |
| rustc | `1.99.1 (58cf8f9c3 2026-10-13)`, LLVM `23.1.1` |
| Cargo | `1.99.1 (5f94df478 2026-08-27)` |
| Platform / embedding Python | Debian 13 x86-64 / CPython 3.13.5 |

The installed compiled submodule and all three actual native classes were
verified. Agent, ecology and politics schema fingerprints are respectively
`dcf0c34097c88451`, `4ab7f8c199b5e5f8`, `b1a710f3450f5015`, all version 1.
Their complete schema hashes match the fresh receipt release manifest. That
manifest identifies the same native crate tree; no old health wheel was used
as a substitute for the receipt release.

## Execution and preservation

The work ran against `/workspace/chronicler-next-qualified` without source
edits. The compatible warm debug cache was copied from
`/workspace/chronicler-build-health/debug` into a new target,
`/workspace/chronicler-build-receipts-full-tests-d051`. Only the copied current
crate artifacts were cleaned (824.1 MiB); dependencies were reused. The original
cache, environments and installed release stayed intact. No release build or
wheel installation was performed by this qualification.

The explicit build configuration was:

```sh
PATH=/workspace/chronicler-tooling/cargo/bin:$PATH
CARGO_HOME=/workspace/chronicler-tooling/cargo
RUSTUP_HOME=/workspace/chronicler-tooling/rustup
CARGO_TARGET_DIR=/workspace/chronicler-build-receipts-full-tests-d051
CARGO_BUILD_JOBS=1
PYO3_PYTHON=/workspace/chronicler-health-venv/bin/python
LIBRARY_PATH=/workspace/chronicler-tooling/lib
RAYON_NUM_THREADS=1
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
```

`libpython3.13.so` resolves through the preserved tooling symlink to the system
shared Python library; `LD_LIBRARY_PATH` was unset. The receipt records compiler,
linker and PyO3 override variables, including unset values. The exact test command
was:

```sh
cargo test --locked \
  --manifest-path /workspace/chronicler-next-qualified/chronicler-agents/Cargo.toml \
  --jobs 1 -- --test-threads=1
```

Cache copy took 14.18 s; cleaning the copied crate took 0.24 s; the full Cargo
invocation took 173.39 s including compilation and execution. It reported
`test` profile, unoptimized with debug information. The source revision, native
crate tree, clean tracked source and installed extension digest were checked
before and after. These elapsed times were under concurrent qualification load,
not controlled performance measurements. The occupied CPU slot was released
explicitly for the waiting full no-Rust Python lane after the process exited.

The two ignored cases are the pre-existing release-mode, Ryzen 9950X budget
checks in `tests/regression.rs`: `regression_6k_24r_under_3s` and
`regression_10k_24r_under_6s`. They were not newly excluded or relabelled. Their
performance budgets were not qualified by this debug suite. No test filter was
used. The library summary was 548 passed; integration summaries account for the
remaining 540 passed; doc-tests reported zero tests.

There were no Cargo build or test failures. An initial metadata-only invocation
of rustup/rustc omitted the supplied `RUSTUP_HOME` and reported no active
toolchain; setting the explicit tooling roots resolved it before Cargo ran. The
preflight note is retained rather than presented as a successful first command.

## Evidence

Generated evidence remains outside Git under
`/workspace/chronicler-next-qualification-evidence/rust-full-d051-20261028/`.

| Artifact | SHA-256 |
| --- | --- |
| `qualification.json` | `4ad0561d83df481e04db2b3073d6c9d7f187512d5a255866a17dc2b710af49ce` |
| `cargo-test-full.log` | `913089d0093999849319c4058018ec96bc5ec31482d192805bd4f85a2626af34` |
| `build-identity.json` | `d14e8dabdef67f97651be8bd94985ce1a8480791d6ba4820f3502d1b1c2db619` |

The driver is retained at
`/workspace/chronicler-next-qualification-evidence/run_full_rust_d051.py`, SHA-256
`1bec99c02649c0ec63a2a2831e2dd452b9985988ad9fa6eb80efaab8c2e241a9`.
The linked receipt release manifest SHA-256 is
`99d14b6d663206eae049c5af611fac3814b6381989519388ed1583a1d874e348`.
The full logs preserve every suite, ignored case, command and exit code.

This result does not replace the full Python lanes, controlled feature
interventions or the documented population/regression scientific gates. Those
retain their own source and build receipts.
