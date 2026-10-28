# Preregistered fixed default export parity — 2026-10-28

Status: DRAFT, not executed. The draft branch does not contain an active workflow.
Activation requires review of these exact controls; activation is an internal lead
review within the user's existing separate-branch development authorization.

## Frozen question and sources

Do the existing nine default CLI identity cases produce the same exported files
at baseline 2f9d618b70f3304c02dcaeef12996b4a99e074c0 and candidate
d0281e5f57c508f27cea1676f36e0e6ed1225c9d on one fresh Linux environment?

Both sources get separate clean checkouts. The qualification controls get a third
checkout at the actual workflow SHA. Nothing rewrites either source, their tests,
or their default simulation settings. This does not include the inaccessible newer
local research integration recorded at 22a48ffa.

The exact existing CASES map and both identity/comparison scripts must agree.
One candidate release wheel is built only after actual tracked bytes/modes, clean
standing, crate-tree equality, and uv.lock/pyproject equality are checked.
The build uses an empty external Cargo target and external wheel directory:
maturin build --release --locked. Build artifacts are never restored from cache.
UV uses the frozen candidate lock into a fresh external environment without
installing the project. Explicit per-arm PYTHONPATH selects its checkout.
Python is 3.13; actual patch version, package versions, compiler/tool versions,
source paths, compiled native SHA and retained wheel SHA are recorded.

## Fixed cases and exposure

| Case | Seed | Turns | Mode | Regions / starting civs | Scaling input |
| --- | ---: | ---: | --- | --- | ---: |
| off_s42 | 42 | 300 | off | defaults 8 / 4 | 0 |
| off_s7 | 7 | 300 | off | defaults 8 / 4 | 0 |
| hybrid_s42 | 42 | 200 | hybrid, validation sidecars | defaults 8 / 4 | 0 |
| hybrid_s7 | 7 | 200 | hybrid, validation sidecars | defaults 8 / 4 | 0 |
| hybrid_s1234 | 1234 | 200 | hybrid | defaults 8 / 4 | 0 |
| proc48_hybrid_s42 | 42 | 150 | hybrid, validation sidecars | 48 / 10 | 0 |
| proc48_off_s7 | 7 | 200 | off | 48 / 10 | 0 |
| scaled22k_s42 | 42 | 30 | hybrid, validation sidecars | 12 / 4 | 18,800 |
| scaled52k_s7 | 7 | 20 | hybrid | 12 / 4 | 43,700 |

Scaling inputs are the existing driver's population multipliers, not independently
verified initial pool sizes. The 48-region cases use the existing automatic world
selection, with no added worldgen flag. Off mode may use native ecology/politics;
it does not mean native absence.

Order is all nine baseline cases in the table order, then all nine candidate
cases: exactly 18 requested worlds and 3,200 requested turns. One driver invocation
runs one case, so failure stops all remaining cases. No feature flags, faith
projection, retries, sample substitutions, shortened horizons, or retuning.

## Admission, execution and retention

The helper and every child inherit one actual allowed CPU via affinity.
OMP/OpenBLAS/MKL/BLIS/VECLIB/NUMEXPR/GOTO/Rayon thread caps, Python CPU count
and Cargo build jobs are one; PYTHONHASHSEED is zero. Existing driver's quiet
output setting is retained. Unexpected CHRONICLER simulation environment
switches refuse admission.

The job limit is 90 minutes. One aggregate helper deadline of 80 minutes covers
build, installation, probes, all worlds, audits and comparison; it is not reset
between cases. Child termination has a bounded 10-second TERM and 5-second KILL
cleanup margin. Private-session leaders remain unreaped through ownership and
live-writer checks. Unexpected process groups or uncertain cleanup fail
qualification; no global host-process or arbitrary escaped-session cleanup claim
is made. Outer job cancellation may prevent later upload; absent evidence is not
a pass.

Disk admission is 12 GiB before build and 6 GiB after build. Available RAM must
be at least 2 GiB at those admission points. Runtime monitoring requires 3 GiB
free disk and 1 GiB available RAM. Host MemAvailable is constrained by observed
cgroup-v2 limit minus current usage; charged cache receives no speculative
reclaim credit. Missing visibility or any floor refusal stops work. A real host
may refuse this protocol. Thresholds do not change after observation.

Fresh independent subprocess probes before and after every case verify the
actual source checkout/path, environment prefix, compiled module origin, and
that all three exported native classes are the actual compiled module's classes.
Their checkpoint schema identities and the actual loaded .so hash must match the
one compiled member of the fresh wheel. Each untouched driver which.txt is copied
to a unique provenance file and must itself match those observed paths/hashes.

All cases require nonempty chronicle/state/bundle, default historiography and
language state sidecars, and memory stream exports. The six hybrid fixtures
require agent_events.arrow; a null fixture without it refuses this registration
rather than establishing a general native-runtime defect. Four validation-sidecar
fixtures require all five core validation outputs. Conditional extra exports are
retained and compared. Actual seed/mode/region shape, final world/bundle turn,
and every completed history turn must match the fixed case.

## Acceptance and limits

Each arm must contain exactly the nine registered case directories. The existing
turn_speed_identity.py compare runs without --faith-ids. It compares file sets and
all shared non-log files, excluding run_manifest.json and .log files as its existing
contract states. Its decoded bundle comparison and additional raw-bundle comparison
may normalize only metadata.generated_at: each raw bundle must have exactly that
single generated_at key and exactly one existing-regex match. A second timestamp
field, even if named the same, refuses admission. No other normalization is added.

Every raw output and log, excluded manifest, independent probe, audit, wheel,
compiled binary copy, resource journal and before/after source record is retained.
inventory.json gives size and SHA-256 for every payload file except its own
self-reference, including result.json. Neither logs nor manifests are deleted.
Final tracked-source bytes/modes/clean standing, installed native hash and wheel
hash must remain unchanged. Failure retains partial outputs and unattempted cases.

Acceptance requires complete execution, all admission/provenance/audit checks,
unchanged identities, complete inventory, and existing comparison exit zero.
A zero comparison exit by itself is insufficient.

This establishes exported-file parity only for these sources, cases, build and
environment. It does not capture native checkpoint blobs, full Python/native RNG
state, or internal per-turn objects. It is not exact-resume qualification, a
performance benchmark, a world-benefit experiment, or permission to promote any
held native optimization. Elapsed time is resource accounting, not a speed claim.
