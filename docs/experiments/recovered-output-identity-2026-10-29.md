# Preregistered recovered-producer default output identity — 2026-10-29

Status: **INACTIVE DRAFT**. This protocol has created no world or native build.
The proposed workflow is under `docs/experiments/`; no active workflow or
completed proof branch is modified. Local contract tests and YAML validation passed after the separate timing
study released its execution lease; the 18-world comparison remains unrun.

## Question and fixed source pair

Does the complete recovered producer preserve the existing default exports
against the original public lead integration for the same fixed nine cases?

| Input | Frozen identity |
| --- | --- |
| Baseline | `2f9d618b70f3304c02dcaeef12996b4a99e074c0` |
| Complete recovered producer | `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1` |
| Executed shared-helper foundation | `4ceb70ab16e1de0e0041b540842ecd6d6946402f` |
| Arc control foundation | `4fe8b5231a561c9f74e1a461e9b551a614b98c4d` |
| Shared helper | `scripts/arc_output_identity_qualification.py` |
| Shared helper SHA-256 | `0d3a2c5db023a47a82307d3a9b789eebd979915e52be66e7208f0c93a94540f5` |
| Required run selection | `--source-pair recovered` |

The existing arc helper and its existing contract suite are reused. A closed
two-pair registry adds this exact recovered pair; the original `arc` pair and
default still bind `d0281e5f` to `249a4e18`. Unsupported pair names and arbitrary
SHAs are not accepted. Selection changes only expected source identities and
records the selected name in `freeze.json`, `result.json` and stdout. It does not
change scenario, physics, matrix, budget, normalization or supervision behavior.
No third helper or duplicate contract suite is introduced. The inherited arc
protocol remains a historical record of its own source/helper, not qualification
of this new pair.

Three separate clean checkouts hold baseline, candidate and controls. Before
and after execution the shared helper verifies actual HEADs, all tracked source
bytes and executable modes. Both source crate trees must match, as must
`uv.lock`, `pyproject.toml`, `turn_speed_identity.py` and `cities_identity.py`.
Read-only source inspection found these shared inputs equal for this pair and
the Rust crate tree `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c`; runtime checks
remain mandatory. Frozen producer trees are never edited.

The separate arc proof (run `40793636869`) compares `d0281e5f` with `249a4e18`.
The recovered producer's full CI (run `40793639813`) and its 62-tick controlled
native composition proof have their own scopes. None supplies this default
output comparison. Finite research and the other experimental systems retain
their ordinary defaults; no feature flag or controlled-World substitution is
added to this matrix.

## Unchanged fixed matrix

| Case | Seed | Turns | Agent mode | Regions / initial civs | Scale input |
| --- | ---: | ---: | --- | --- | ---: |
| off_s42 | 42 | 300 | off | 8 / 4 | 0 |
| off_s7 | 7 | 300 | off | 8 / 4 | 0 |
| hybrid_s42 | 42 | 200 | hybrid, sidecars | 8 / 4 | 0 |
| hybrid_s7 | 7 | 200 | hybrid, sidecars | 8 / 4 | 0 |
| hybrid_s1234 | 1234 | 200 | hybrid | 8 / 4 | 0 |
| proc48_hybrid_s42 | 42 | 150 | hybrid, sidecars | 48 / 10 | 0 |
| proc48_off_s7 | 7 | 200 | off | 48 / 10 | 0 |
| scaled22k_s42 | 42 | 30 | hybrid, sidecars | 12 / 4 | 18,800 |
| scaled52k_s7 | 7 | 20 | hybrid | 12 / 4 | 43,700 |

All baseline cases run in table order, then all candidate cases: **18 worlds
and 3,200 requested physics ticks**, with complete horizons required. Scaling
inputs are the existing driver's inputs, not verified initial native pool counts.
The 48-region cases retain the driver's automatic world selection. Off mode can
use native ecology and politics. No extra worldgen/scenario/physics switch is
available through the new source-pair selection.

One invocation runs one case. A failure stops further cases and preserves
unattempted rows. There are no retries, substitute seeds, shorter horizons,
new scenarios, retuning or favorable-sample extensions.

## Preserved execution and evidence rules

A fresh external Python 3.13 environment uses the candidate's frozen lockfile.
A fresh external Cargo target builds exactly one locked release wheel, shared
by both arms; no saved binary is silently attached to new state. Before and
after every case, actual source/native probes verify the imported source path,
Git SHA/package digest, compiled module, all three class exports and checkpoint
schemas, interpreter and environment. Available classes are not a count of
active simulator pools; this study qualifies exported files, not captured pool
state or checkpoint/RNG restoration.

The job allows 90 minutes; the helper's single 80-minute deadline includes
build, install, probes, worlds, audits, comparison, cleanup and final inventory.
The helper and children share one actual CPU, hash seed zero, and one
numerical/native/build thread. Private-session ownership, process-birth and
pidfd checks retain bounded 10-second TERM / 5-second KILL cleanup. Uncertain
cleanup withholds final inventories and cannot qualify a run.

Disk floors remain 12 GiB before build, 6 GiB after build and 3 GiB during
execution. RAM floors remain 2 GiB at build admission and 1 GiB during execution.
Host available memory is constrained by actual cgroup-v2 max/current pairs;
missing declared nonroot interfaces fail closed. The kernel hierarchy root may
omit interfaces only when an actual nonroot pair was observed. No cache-credit
or resource-floor waiver is introduced. These floors preclude a local build
on the currently smaller free workspace; the inactive proposal targets GitHub
Actions rather than reducing admission requirements.

Each arm must have exactly the nine registered case directories and every
completed seed/mode/shape/horizon/history contract. Required chronicles, states,
bundles, language/historiography state, memories, hybrid agent events and selected
sidecars must be present and nonempty. The untouched driver diagnostics and
actual probes must agree with the fresh wheel and package identities.

The unchanged frozen candidate comparator compares all case file sets and
shared files with its existing `.log` and `run_manifest.json` exclusions. Only
`metadata.generated_at` may be normalized: every raw bundle must contain that
single timestamp path and exactly one existing-regex match. No metadata, faith,
research or historical-prefix projection is added. Comparison exit zero alone
does not establish completion or qualification.

All raw outputs, logs, wheel/native copy, source records, audits, probes and
resource observations are retained. Per-case audits pin their entire raw file
maps and are rehashed after comparison. Installed binary, wheel, sources and
audits must remain unchanged. `inventory.json` hashes all payloads except itself
and the final `result.json`; the result stays negative until inventory completion.
Failures remain visible. Actual file counts are observed, not inherited from
older 399-file results.

## Review and activation boundary

The inherited 22 pure contracts remain, with three additional contracts for
closed registry pins, rejection before any evidence/child creation, and the
recovered proposal's explicit source selection without physics overrides.
All 25 contracts and YAML validation passed; the proposal remains inactive. Independent
source review cleared the closed registry, selected-pair binding and inactive
workflow. The checks qualify control behavior only; no world or native build
has run under this recovered-pair protocol.

Acceptance applies only to this exact source pair, fixed matrix and observed
environment. It does not establish a speed gain, feature efficacy, natural
research exposure, arbitrary platform identity, exact checkpoints/native/RNG
state equality or full population-gate qualification. Main, archived proof
branches and their prior results remain unchanged.


## Executed local control checks

At clean control `45f767c0291712b5a6f99f82f192d38e00ed88a9`, Python 3.13.5
reported **25 unittest contracts passed in 0.028 seconds**. Existing `actionlint`
1.7.12 passed the proposed YAML with exit zero and no diagnostic output. These
checks ran only after root released the separate timing study's execution lease.
No native module/pool, world or build was created by these control checks.

The external receipt is
`/workspace/chronicler-evidence/recovered-output-controls-20261029/receipt.json`,
SHA-256 `13737f1abb7935a05d1e83c7ca51c02b2552c3f38aa38245f293385ba91ddabb`.
The retained unittest log SHA-256 is
`df77f7a4ece015716387fa34dd4377d617cb6848938511a91f9ec7ac94547f61`.
Helper, contract-suite and YAML byte hashes are pinned in that receipt. Subsequent
result documentation does not change those tested source files. No active
workflow or raw output comparison is claimed by this local check.


## Activation standing

Root and independent source review cleared `8bf8cbee` after all 25 pure
contracts and actionlint passed. The shared helper's closed registry preserves
the old arc source pair and selects the recovered pair explicitly; matrix,
resource, cleanup, native and source checks and the sole generated_at rule are
unchanged. No third copied qualification implementation was introduced.

The active copy of this registered workflow runs only on
`lead/cloud-recovered-identity-20261029`, with baseline `2f9d618b` and candidate
`c76efe85`. Candidate prerequisites are complete: all six CI lanes in
run 40793639813 and the separately qualified 62-tick native composition proof.
Neither substitutes for this default-off exported-output study. The Action
repeats pure contracts, builds one fresh shared native wheel and runs exactly
the fixed eighteen worlds /3,200 physics ticks. Its actual control identity and
result are retained by the run. Main, archived studies and held Rust corrections
are unchanged. No natural efficacy, checkpoint-byte parity or speedup follows
from a matching export result.
