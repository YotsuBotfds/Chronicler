# Inactive exact-marriage enumerator experiment — 2026-10-29

Status: source draft only. No Rust compilation, test execution, native import,
World, input capture, benchmark, push or workflow activation has occurred.
Root and independent peer review must precede any remote run. Main, the
qualified runtime, pending native candidates and prior rejected optimizations
remain separate. Negative performance is a valid terminal result.

## Frozen source and scope

Base: `0900f3d203cc74102809bb871a1a057ba91a951f`, native crate tree
`803c79c8d5c024cbb8d67c58af7ffa731d79c129`. Its `formation.rs` Git blob is
`d94edb40f41fcb0cdcdd20866f1ee8d50a191b5b`, also present at qualified CBF and
the separate 535 candidate. This draft appends one `#[cfg(test)]` module;
every original byte of the file, including the default planner, Fast path,
reference helper and persistence declaration, stays unchanged. No production
call site, native API, CLI, global, RandomState, dependency or checkpoint field
is added. The appended module's hash is pinned by the dormant workflow.

The experiment compares only near-neighbor enumeration. It neither runs nor
qualifies the full marriage planner, a native simulator or a World. Existing
planner/reference tests remain untouched. A positive result permits proposing
a later isolated child with planner differential tests and ordinary exported-
output parity; it does not wire the experiment into production.

## Fixed helper and inclusion argument

The crossover is exactly 256 eligible agents. Non-finite coordinates retain
the existing reference-planner route; the screen does not invent an enumerator
result for it. Finite out-of-domain coordinates use the existing linear
enumerator, including arithmetic overflow. Dense queries whose conservative
neighborhood includes everyone use that same linear helper. If all occupied
cells have this property, no bitset index is allocated.

Other eligible lists use fixed boundaries 5/16, 10/16 and 15/16 on each axis.
Two nonadjacent cells imply an exact axis separation at least 5/16. Monotone
correctly rounded f32 subtraction, squaring and addition cannot yield a radius
at most the original 1/4. Same/adjacent cells therefore include every old
accepted pair. The original f32 expression and marriage_radius_sq filter remain
authoritative. The tight-grid counterexample `(0.25 - 2^-26, 0.5)` is retained:
its rounded delta is 0.25 despite a naive width-0.25 cell gap of two.

Fixed Vec-backed cell memberships and neighboring unions contain eligible
indices. Word/bit iteration is ascending, so near indices, distance bits and
the later planner's candidate order remain unchanged. The index is local to
one immutable Eligible copy and is discarded before the next plan. Scratch
resizes only when its length changes. No mutable cache survives movement,
death, birth or slot reuse. No physics RNG operation is introduced.

## Ordinary contracts, unrun

Six unit tests compare complete ordered near lists and every retained d2 bit,
not only checksums. Available logical counters retain Far, incest, hostility
and valid classifications with the existing precedence. The original reference
helper remains the comparison implementation.

Cases include empty/singleton lists, 255/256/257, dense and spread populations,
all cells, exact cell/radius boundaries and adjacent f32 values, the tight-grid
rounding example, both zero signs, subnormal deltas, NaN and both infinities,
finite out-of-domain extremes, identity-array irrelevance, current eligible
slots with dead holes and a reused slot. Non-finite routing also checks the
actual production planner still returns None before its reference fallback.
The original radius-threshold unit test is selected separately in the proposed
remote workflow. These tests use synthetic Rust arrays/pools, not Worlds.

## One fixed synthetic screen

Only the ignored `exact_near_broadphase_fixed_screen` can time this experiment.
It requires GitHub Actions, one actual affinity CPU, all numerical/native thread
caps one, Python hash seed zero and the fixed activation string. It has no
public CLI or input path. No admitted real eligible vectors were identified;
all inputs are prospectively fixed synthetic arrays. No new capture is allowed
by this draft.

Exactly 15 cases run, in order:

1. empty0
2. singleton1
3. small16 (spread)
4. spread255
5. spread256
6. spread257
7. spread1024
8. spread4096
9. dense1024 at (0.125, 0.125)
10. dense4096 at (0.96875, 0.96875)
11. boundaries1024 using the fixed seven-coordinate sequence
12. outside1024 with one (-1, f32::MAX) coordinate
13. nan1024
14. infinity1024
15. zeros1024 alternating signed zero and the smallest positive subnormal

For each, an untimed complete differential precedes exactly five timed old/new
pairs. Order is old/new, new/old, old/new, new/old, old/new. There are exactly
150 timed samples. No warm-up, timing retry, case omission, cutoff sweep, tuned
fixture or favorable subset is allowed. Non-finite cases time only setup and
the original reference-route decision, not reference-planner performance.

Each sample freshly constructs the same Eligible arrays. Candidate setup also
includes cell counting, membership allocation and union construction when used.
Total nanoseconds include all setup, query work and owned drops. Separate setup
and query times are retained. Query work includes word traversal, exact distance
arithmetic, gathers and actual scratch growth. black_box retains outputs without
timing a full parity-hash pass. Complete ordered parity is established separately
for the same frozen inputs. Retain distance, word and gather counts, live/peak
index capacities, scratch capacity, process CPU ticks and cumulative process
VmHWM. VmHWM does not identify an independent per-arm RSS delta. Original
marriage_pairs_evaluated counters are neither changed nor reinterpreted.

The screen has hard observed caps of 60 wall seconds, 60 process CPU seconds
and 512 MiB process peak RSS. An external 70-second TERM / five-second KILL
deadline bounds a stalled sample; exceeding any cap fails the experiment and
retains partial logs. These caps include parity, sample setup and telemetry.
They are separate from remote compilation: that step gets 35 minutes, one
affinity CPU/build job, a 12 GiB disk/2 GiB visible RAM admission, and its own
GNU-time CPU/wall/RSS record. Require 3 GiB disk/1 GiB visible RAM before the
test binary. Build output is fresh and no cache/old experiment is deleted.

## Acceptance and negative publication

All complete differential checks must pass. Using the median total sample time
of each arm, both spread1024 and spread4096 must have candidate <= 90% of old.
Every other case with n > 256 and finite coordinates must have candidate <=
105% of old. Small and non-finite route-only cases allow 105% plus a fixed
5,000-nanosecond timer/setup allowance. The allowance and all thresholds are
fixed before any data. All 15 decisions must pass; there is no pooled average
that can hide a case's regression.

After every case completes, print one final record. Performance rejection is a
nonzero ignored-test exit with its complete negative decision records preserved.
A parity/resource failure also exits nonzero and cannot produce a positive
final record. The workflow retains logs, timing, source/binary identities and
its independently parsed fixed-row summary on every outcome. It never promotes
production. No tuning, retry or larger input acquisition follows a rejection
without a new prospective source record and separate root authorization.

## Activation and measurement limits

The YAML beside this document is under docs/experiments and is inactive.
After independent peer and root review, root may copy those exact bytes to
`.github/workflows/exact-marriage-broadphase-screen.yml` on the one separate
`lead/cloud-exact-marriage-screen-20261029` branch. Its source preflight requires
the original 090 formation prefix, exact appended-module hash and a narrow file
allowlist. Python is provided only for PyO3 linkage and metadata parsing, as in
the existing Rust CI lane; no wheel or simulator pool is built/instantiated.

This is a same-binary synthetic enumerator screen. Release compilation costs,
process setup, Rust linkage and per-sample overhead remain visible. A positive
screen is not a measured World/whole-planner speedup, a default-output proof,
native execution qualification for this branch or scientific efficacy. No
claims or gate standing from CBF/535/090 are extended to this new experiment.

## Source-only admission correction after independent review

Parent `2bba50081e12464835acfe3e26140a068a4034a3` remains preserved. Its Rust
appendix, all six ordinary contracts, ignored screen, 15 cases, 150 samples,
acceptance criteria, fixed crossover and caps are byte-identical in this child.
The only implementation correction is to the dormant workflow's two RAM
admissions: each reuses the exact existing `wealth_floor_build_resources.py`
resolver (Git blob `730d2affa4845e948fc0866f65f6e54bb766a6b5`, SHA-256
`44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2`),
retained unchanged from `5a6fed7809fa314d5e5ad3878e56c4299f7f5f59`. This is
reuse of the qualified dependency, not new runtime qualification in this child.

Both call sites hash-check the resolver before loading it and retain its full
visibility-limited observation or explicit refusal in external admission JSON.
The resolver binds membership to mountinfo, refuses ambiguous/non-root mount
roots, checks visible ancestor controller/counter evidence and rereads the
membership/mapping. Namespace-invisible ancestors remain explicitly outside
the observed scope; observations reserve no RAM. No partial mapping algorithm
is left in the workflow. Build admission stays 12 GiB disk/2 GiB visible RAM;
test admission stays 3 GiB disk/1 GiB visible RAM. No execution, local compile,
project/native import, World, network, push or activation occurred for this
source correction. Independent peer and root review still precede activation.


## Source-only hosted ownership successor

The preserved `c70fe638290280861735bf13cc01dd2dc7380ef0` admission correction
remains a separate ref. This successor changes only control source, its tiny
contracts and documentation. The complete Rust crate, production prefix,
appended test module, 15 cases, five pairs, arm order, criteria, crossover and
all Rust clocks/caps remain byte-identical. No Rust test or screen has run.

The dormant workflow is now sealed to one push branch, exact workflow path,
job and attempt 1, repeated against actual GitHub context in the owner. It uses
a direct `ubuntu-24.04` hosted VM and exact D2 deployment precondition (SHA-256
`d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8`).
The original 45-minute job cap and fixed GNU timeout/taskset/time commands stay:
2100-second build, 60-second differential contracts, 15-second original-radius
contract and 70-second ignored screen. Existing build 12 GiB disk/2 GiB RAM and
test/final 3 GiB disk/1 GiB RAM floors still use exact R44. The owner has a
2,500-second wall ceiling with the original C60 25-second child cleanup reserve;
it makes no aggregate live-tree CPU budget or speed claim.

Small dedicated helpers retain only the selected ownership algorithms from
C60 controller source `3b941645a42c8c159a2f8ce9e383d484066b6355` (SHA-256
`60bb77212757f632d8d80ed226f94e6ef9864134c4453b5affeb51dc059b9dd1`)
and authenticated original27f session helper (SHA-256
`e4ca3f0c3732e4b5536a88a6284ab44b173e2165fafb59586be02fbd1d015932`,
retained exact blob `05917006880c46a8f8b7ee4345293de61abb3a17`). Selected
functions/methods remain verbatim with an explicit AST/constant dependency
closure receipt. The base supplies only init and birth/boot/session/pidfd
signalling; the C60 override supplies bounded intake, cancellation, subreaping,
owned-session cleanup and kernel-ECHILD confirmation. The adapter always fixes
`trace=False`; the omitted optional strace accumulator explicitly refuses.
There is no historical Git fetch or whole-study controller dependency.

A negative receipt exists before checkout/setup. The owner records reached
phases and actual exit/cleanup observations and always attempts terminal closure.
Positive or complete-negative status requires joined/reaped owned descendants,
final actual Git/source/production-prefix/append/template/helper/executable/
runtime/linkage identities, thread/affinity/cap observations and final R44 floors.
An early refusal retains actual available observations and explicit unavailable
fields, always incomplete. No field is synthesized from an earlier observation.
The terminal and independent always-closure are authoritative: intermediate
`screen-result.json` is provisional and cannot qualify a later closure failure.
The always step also checks the actual owner-step outcome, so a stale positive
receipt after an owner failure cannot become a positive publication.

The compiler and test streams use the qualified 8 MiB per-command intake and
256 KiB line bound; progress is capped at 8 MiB. The published light pack is
prospectively limited to 48 owner files/8 MiB plus one <=64 KiB always-closure.
It includes metadata and <=256 KiB head/tail log excerpts, explicit omission
records and full raw-log hashes. Full compiler logs and build outputs remain
outside the publication. No binary, wheel, vectors or World data is uploaded.

Exit 101 is permitted only for the ignored Rust screen. A complete 15-case,
150-sample negative result with exact arm order and recomputed fixed median
criteria becomes `complete-rejected`, `screen_accepted=false`, and an unsuccessful
owner/job. Timeout, resource, partial, source, cleanup or publication failures
are `incomplete` and can never be promoted to a complete performance rejection
or an accepted result. Consumers must require the matching terminal, bounded
always-closure, exact source and completed producer job; a success additionally
requires `complete-accepted` and successful owner/job metadata.

The tiny stdlib control contracts run with child/network/simulator/native-import
guards and synthetic protocol/fault records only. They do not execute this Rust
experiment or establish native lifecycle/performance qualification. Source peer
and root review of the new immutable successor, followed by a separate exact
one-file workflow activation, are still required. No push or activation has
occurred in this source-only correction.
