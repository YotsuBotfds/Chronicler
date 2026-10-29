# Preregistered arc optimization export parity — 2026-10-29

Status: INACTIVE DRAFT. No simulation or native build has run for this protocol.
The proposed workflow remains under `docs/experiments/`; activation requires
root lead review and successful completion of all six CI lanes at the frozen
candidate source. This is an internal development check within the user's
existing separate-branch authorization.

## Frozen question and implementation

Do the nine existing default CLI cases export the same files at these sources?

| Input | Frozen identity |
| --- | --- |
| Baseline | `d0281e5f57c508f27cea1676f36e0e6ed1225c9d` |
| Arc candidate | `249a4e1879cf5fbbb070de11f478f19825f51419` |
| Vetted helper foundation | `4ceb70ab16e1de0e0041b540842ecd6d6946402f` |
| Executed workflow-layout foundation | `db7ec48b738fa841f1b951c3ae810aa121ef1918` |
| New helper path | `scripts/arc_output_identity_qualification.py` |
| New helper SHA-256 | `0f8081e3c6bbc59902733fb798d5a1db03119d897363605490286c553e4cfaff` |

The new helper is the vetted helper with exactly three lines changed: its
description and the two source constants. Its supervisor, resource guards,
matrix, contracts and receipt logic are unchanged. The two early wheel/native
hash receipts introduced at `4ceb70ab` remain available on failed attempts.
The proposed YAML uses the corrected executed layout: external environment
paths are set by the first `GITHUB_ENV` step, not a job-level `runner.temp`.

Baseline, candidate and qualification controls use three separate clean
checkouts. Actual tracked bytes/modes and Git identities are recorded before
and after work. The source crate trees, `uv.lock`, `pyproject.toml`, and existing
identity/comparison scripts must agree. No frozen source is rewritten.

A fresh external Python 3.13 environment uses the candidate lockfile, with
explicit per-arm `PYTHONPATH`. One candidate release wheel is built from an
empty external Cargo target with `maturin build --release --locked`; build
artifacts and old outputs are not reused. Actual interpreter/tool/package,
wheel, compiled native module and checkpoint-schema identities are retained.
The imported `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator` must
be the real compiled module's classes before and after each case.

## Fixed exposure

| Case | Seed | Turns | Agent mode | Regions / starting civs | Scaling input |
| --- | ---: | ---: | --- | --- | ---: |
| off_s42 | 42 | 300 | off | default 8 / 4 | 0 |
| off_s7 | 7 | 300 | off | default 8 / 4 | 0 |
| hybrid_s42 | 42 | 200 | hybrid + validation sidecars | default 8 / 4 | 0 |
| hybrid_s7 | 7 | 200 | hybrid + validation sidecars | default 8 / 4 | 0 |
| hybrid_s1234 | 1234 | 200 | hybrid | default 8 / 4 | 0 |
| proc48_hybrid_s42 | 42 | 150 | hybrid + validation sidecars | 48 / 10 | 0 |
| proc48_off_s7 | 7 | 200 | off | 48 / 10 | 0 |
| scaled22k_s42 | 42 | 30 | hybrid + validation sidecars | 12 / 4 | 18,800 |
| scaled52k_s7 | 7 | 20 | hybrid | 12 / 4 | 43,700 |

All baseline cases run in table order, followed by all candidate cases:
**18 worlds and 3,200 requested turns**. The scaling values are the existing
driver's population inputs, not independently verified initial pool sizes.
The 48-region fixtures retain the driver's automatic world selection; no
worldgen flag is added. Off mode can still use native ecology/politics.

One driver invocation runs one case. Failure stops further cases. There are
no retries, substitutions, shorter horizons, added feature flags, faith-ID
projection or retuning. Old checkpoint IDs are never attached to new pools.

## Unchanged admission and execution controls

The helper and children share one actual allowed CPU. Python hash seed,
OMP/OpenBLAS/MKL/BLIS/VECLIB/NUMEXPR/GOTO/Rayon caps, Python CPU count and Cargo
build jobs retain their registered one-thread settings. Unexpected simulation
environment switches refuse execution.

The job limit is 90 minutes. One aggregate 80-minute helper deadline covers
build, installation, probes, cases, audits, comparison and final inventories.
It is never reset between cases. Private-session ownership, birth and pidfd
checks retain the bounded 10-second TERM / 5-second KILL cleanup. Uncertain
cleanup withholds final payload hashing and cannot qualify a run.

Disk floors remain 12 GiB before build, 6 GiB after build and 3 GiB during
execution. Available RAM floors remain 2 GiB at build admission and 1 GiB
during execution. Observed host `MemAvailable` is constrained by readable
cgroup-v2 max/current pairs; charged cache gets no speculative credit. A
declared nonroot cgroup must exist and expose its pair. The actual hierarchy
root may omit control interfaces, but an observed nonroot pair remains
required. Visibility observations and every refusal are retained.

## Acceptance and retained evidence

Both arms must contain exactly the nine registered case directories and
completed seed/mode/shape/horizon/history contracts. Required chronicle,
state, bundle, historiography/language state, memory streams, hybrid agent
events and selected validation sidecars must be present and nonempty.
Independent native/source probes and the untouched driver provenance files
must agree with the fresh wheel and source packages before and after cases.

The frozen candidate `turn_speed_identity.py compare` runs with no extra
switch. Its existing rule compares the case file sets and shared files,
excluding `.log` and `run_manifest.json`. Bundle comparison may normalize
only `metadata.generated_at`; every raw bundle must contain exactly that
single timestamp key and exactly one existing-regex match. No additional
normalization is introduced. Comparison exit zero alone is insufficient.

All raw exports, logs, audits, probes, wheel, native copy, source records and
resource journal are retained. Each completed audit pins its full raw case
file map, which is rehashed after comparison. Final installed-native and
wheel hashes and source snapshots must remain unchanged. `inventory.json`
pins every payload file except itself and final `result.json`; the result
stays negative until inventory completion. Failures retain partial outputs
and unattempted cases. Neither original completed proof branches nor their
artifacts are changed.

The final stdout summary and full artifact record actual source/native/wheel/
inventory hashes, case statuses and elapsed resource accounting. The actual
compared-file count is observed rather than assumed from earlier runs.

## Verification and limits

The inherited 20 pure helper contracts are retained, with two new checks for
the exact source/helper pins and rejection of another source before any
world/build. Pure checks and YAML validation must pass before activation.
Their execution results are recorded separately below when available.

This qualifies exported-file behavior only for these sources, fixed cases
and the fresh environment. It is not a speed experiment, exact-resume/native
pool-state or RNG qualification, full population gate, or feature-efficacy
study. The newer finite-research integration at `22a48ffa` / recovered
`49b2a35b` and held native household/forkserver prototypes are outside scope.
No local native build is admitted while workspace storage is below the
unchanged 12 GiB floor.

## Local control checks before activation

On Python 3.13.5, all **22 pure contracts passed**: unittest reported 0.026
seconds; its external wrapper recorded 0.1516 seconds. No worlds or native
builds ran. `actionlint` 1.7.12 also passed the proposed YAML. Git independently
reported the same Rust crate tree for both frozen sources:
`a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`.

The external pure-check receipt SHA-256 is
`32150b7b339c0707143f42c343d372e3e23d32708df1e9647b1a776f7adeca85`;
its retained unittest log SHA-256 is
`fc1106da62038ee0b08addbad9f84549e8b2357b94f93826ed48c6cd21983811`.
These checks qualify the control contracts only. The 18-world exported-output
comparison remains unrun and inactive.
