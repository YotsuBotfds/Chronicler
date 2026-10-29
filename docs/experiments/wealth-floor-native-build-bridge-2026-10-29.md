# Dormant paired native build bridge

This branch prepares an executable build controller and a disabled workflow
template. **No native build, candidate world or active GitHub workflow has been
launched by this work.** Main, the historical producers, the original C76
checkpoint path and the qualified wealth correction remain unchanged.

The purpose is to build the wealth correction against a known native baseline,
while preserving a practical fallback when a historical binary cannot be
reproduced. Merely matching compiler version strings is insufficient.

## Exact sources and the reuse decision

| Role | Producer commit | Native crate tree |
| --- | --- | --- |
| Historical D028 baseline | `d0281e5f57c508f27cea1676f36e0e6ed1225c9d` | `a4703ef4e9a21b5dbb194d318536a46e6ca8b71c` |
| Intentional wealth-floor correction | `503070175e3e78d9014add158ead8f16ce940843` | `93b32cd9b02eccf4900b33cdaeece08262be2330` |

The closed ancestry is `5030701 → 9f43bbb7 → d0281e5f`. A depth-three checkout
of exact 503 therefore supplies both commits without following a moving branch.
The controller verifies the initial candidate identity and checks out each
fixed commit into the same `candidate` path. Actual tracked bytes, executable
modes and Git identities are snapshotted before and after each build.

Historical reuse requires the rebuilt baseline's **native member** to reproduce
SHA-256 `06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6`
exactly. This is distinct from the old wheel-file or artifact-ZIP digest. The
candidate binary must be different. Both builds must have equal recorded
effective contexts, successful native API probes and complete cleanup.

If the rebuilt baseline differs, the result is `fresh_baseline_required`.
Both newly built wheels remain retained, but the old population observations
cannot be relabeled as results from the new baseline binary. Fresh baseline
worlds would then be needed. This build job itself admits no worlds.

The old 27f build recorded rustc/cargo 1.99.1, LLVM 23.1.1, maturin 1.15.0,
uv 0.13.6 and CPython 3.13.17. Its inherited effective flags, target overrides,
linker/full argv and precise Ubuntu image were not recorded. The new context
does not retroactively invent them. Exact old-native reproduction is the
decisive bridge to those retained observations.

## Corrected future job, presently disabled

The [workflow template](wealth-floor-native-build-bridge-workflow.yml) lives
under `docs/experiments`, with a false job guard. It installs no active workflow
under `.github`. Future activation is recognized only on the specifically
registered `lead/cloud-wealth-floor-native-build-bridge-2-20261029` branch and
workflow-file push path. Pure tests seal every other command, source, version,
environment setting, budget and artifact-retention rule. They recognize both
the dormant and exactly activated states, avoiding a preparation-only assertion
that would reject its own reviewed activation.
The first activation branch remains frozen at `75cb1771`; it is not the
corrected producer.

The executable entry is
`scripts/wealth_floor_native_build_controller.py build`. Its steps are:

1. Verify source/control/evidence paths, Linux/Python, the exact old supervisor
   source, actual process/memory visibility and fresh external build paths.
2. Use pinned Python/Rust/maturin/uv tools. Build D028, then 503, at the same
   producer, Cargo-target, Python-build-environment and staging-wheel paths.
3. Retain each wheel, compiler/linker records, source snapshots and probe before
   retiring only the baseline's derived Cargo target through bounded `cargo
   clean`. Source, wheels, logs and receipts are outside that target.
4. Install each retained wheel without dependency changes into a separate fresh
   locked environment. An isolated `-I -B` probe verifies the actual compiled
   module's path/hash, the three real exported classes and their registered
   checkpoint schemas. It imports no `chronicler` source and creates no simulator
   instance. These are native class/schema API calls, not physics worlds.
5. Run the candidate's four genuine Rust wealth/migration regressions, including
   the native spawning/marriage/credit/wealth-update reachability fixture.
   These tiny API fixtures do not establish natural low-balance frequency.
6. Check final source/wheel identities and child cleanup, then seal original
   evidence and bounded provenance for later independent review.

The native schema is expected to stay unchanged because the correction changes
one behavior calculation. Schema equality alone never authorizes loading old
checkpoints into the new native pool. Future candidate parents/checkpoints and
genuine repeated-seed proofs remain separate prerequisites.

## Effective context and passive traces

The build environment forwards a small explicit operating/runtime allowlist,
including inherited proxy, CA and authentication guard settings. It supplies
the registered thread/Cargo settings and records explicit present/absent build
flag states. It does not dump the environment or inspect credential files.

Cargo configuration files under the actual Cargo home and command/manifest
ancestors must be absent. Their presence refuses context completeness without
reading potentially credential-bearing contents. Source-specific identities
stay outside the common context digest; current host/platform and available
hosted-image identifiers remain recorded.

A passive `strace` execve stream records actual compiler/linker argv without
inserting a compiler/linker wrapper. The stream is bounded; only selected
successful compiler/linker records are retained. Ignored child arguments and
environment values are discarded. Potential credential-bearing arguments,
truncation, unresolved response files, missing actual linker/compiler records
or unsupported trace forms leave the context incomplete and refuse the bridge.
Tool executable paths, bytes and observed version outputs are bound to the
context. A version label cannot substitute for actual executable identity.

Limits are 64 MiB trace input/retained records, 256 KiB per trace line,
128 KiB/4,096 arguments per selected execution and 10,000 retained records.
Wheels are at most 16 MiB compressed/64 MiB expanded, with a bounded directory,
regular members and one at-most-32-MiB compiled member. No wheel is extracted by
the controller's inspector. Its hash must match the compiled module actually
loaded by the later isolated probe.

## Clocks, process ownership and resource admission

The provisional controller deadline is **30 minutes**, including cleanup and
publication checks; a separate **45-minute job timeout** covers setup and
artifact transfer. Commands stop launching 25 seconds before the controller's
deadline to reserve cleanup/finalization time. All values remain inactive
protocol design, not authorization to execute the job.

CPU values report measured controller-self and waited-child usage. They make
**no exact aggregate live-tree CPU or CPU-admission claim**. Concurrent tool
execution and job setup/publication retain their distinct clock scopes.

The controller reuses the exact 27f default-output supervisor source:
`scripts/default_output_identity_qualification.py`, SHA-256
`e4ca3f0c3732e4b5536a88a6284ab44b173e2165fafb59586be02fbd1d015932`.
The leader remains unreaped with `waitid(WNOWAIT)` while its private session is
checked and signaled. Boot/birth identity and pidfds protect cleanup. An
exclusive subreaper lease catches adopted descendants that leave that session;
unexpected or incomplete cleanup refuses completion. Cancellation is latched,
so repeated SIGTERM/SIGINT cannot interrupt TERM/KILL/reap work.

Some kernels omit `/proc/.../children`. The ownership helper uses a bounded
numeric `/proc` PPID/stat fallback there, and an empty observation requires the
kernel's WNOWAIT/ECHILD confirmation. A missing or untrustworthy interface
cannot silently certify quiescence.

Build admission needs 12 GiB free disk and 2 GiB available RAM; running/final
floors remain 3 GiB/1 GiB. The shared `wealth_floor_build_resources.py` helper
resolves actual unified membership and mount information, then takes the
minimum of host MemAvailable and every visible ancestor's remaining memory.
Missing/contradictory controller evidence, hidden bind roots, ambiguity or a
changed hierarchy refuses admission. Namespace-invisible ancestors remain
explicitly unobservable, and counter observations are not reservations.

The shared `wealth_floor_hosted_deployment.py` D2 precondition requires the
sealed direct hosted-runner flags, stable PID1 `systemd` and a valid, stable
self cgroup namespace identity. When PID1's namespace is readable, its canonical
identity must match self and remain unchanged on reread. D2 also accepts the
specifically observed case where both PID1 namespace reads fail with `EACCES`
(errno 13). That case records `pid1_cgroup_namespace: null`,
`namespace_equal: null`, `namespace_equality_verified: false` and
`namespace_equality_status: unverified_permission_denied`. Both errno observations
and all accepted identities are retained. Other errors, missing/invalid evidence,
changed observations and readable mismatches still refuse. There is no privileged
read or access workaround.

The first shared precondition (`ef872ace`, preserved in source `5a6fed78`)
refused the separate baseline-audit activation
`40815630794` before resources, source snapshots, client creation or archive
transfer. The retained record does not identify which deployment predicate
failed; the later diagnosis does not retroactively assign its cause.

The separate read-only diagnostic at source
`cc2fea8042bf8dd4a61cdbe0235aa3831cba6382`, run `40817163080`, job
`123260833950`, recorded the registered hosted flags, stable PID1 `systemd`,
a valid/stable self namespace and `EACCES13` on both PID1 namespace reads.
Namespace equality was unknown. Its independent verification receipt is
`9f853a881dd61a9a7a24f072a33a7d360129a488e27be26c809bfd7946838fc0`.
This concrete observation corrects the earlier assumption that this direct
hosted job can always read PID1's namespace without privilege.

D2 grants deployment-context eligibility only. Its evidence scope explicitly
excludes proof against namespace-invisible provider ancestors, memory admission
and world execution. The generic resource helper remains exact `44f1e1d`, with
unchanged 12 GiB/2 GiB admission and 3 GiB/1 GiB running/final floors. The D2
helper/test pair is shared byte-for-byte with the separate audit lane:

| File | SHA-256 |
| --- | --- |
| `scripts/wealth_floor_hosted_deployment.py` | `d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8` |
| `tests/test_wealth_floor_hosted_deployment.py` | `9ef3311485f045906160e855096a115986a6d9ac7ad342ed7e1ffd38ae7fa340` |

Deployment refusals now carry a fixed registered code, without arbitrary
exception text. Accepted deployment observations survive pair classification
into the final raw and light manifests. This source correction remains dormant;
it does not constitute an actual build, successful D2 runner admission or a
candidate-world grant.

## Publication and qualification boundary

Heavy raw-file hashing happens before the final publication observation. The
manifest is provisional until a matching completion seal binds its digest,
the original raw inventory and the light index. The completion records a later
clock observation, followed by a post-commit deadline/ownership check. Any late
failure removes canonical positive paths and retains superseded bytes under
`incomplete-*` names in both raw and light evidence.

The light directory plus its adjacent completion are capped at 8 MiB/32 files.
The original build evidence keeps both wheels, all bounded original tool logs,
selected compiler/linker argv, source/probe/context records and incomplete
attempts. Contracts are published separately. No native build cache is called
scientific evidence or substituted for a retained wheel.

A local `build_complete_pending_job` receipt is insufficient. A consumer also
needs the exact completed-source receipt digest, matching completion seal,
successful official producer job and published artifact identity. Baseline raw
admission, reviewed candidate binary/build pins, candidate-owned checkpoints
and determinism proofs still gate later worlds. No efficacy, population outcome,
default activation, main merge or wall-time speedup is established by this work.

## Retained first-build failure and loader correction

The first actual paired build, source
`75cb17717dedb3e59d5d55e5313d954bd98dda1f`, run `40818391220`, job
`123264802829`, failed after both release builds and isolated class/schema
probes. Its remote 163 pure cases and eight confined Linux cases passed. The
Rust regression executable compiled, then exited 127 because its dynamic loader
could not find `libpython3.13.so.1.0`. No regression assertion ran. The normalized
release-build environment had deliberately omitted inherited `LD_LIBRARY_PATH`.

The retained first attempt has these observations:

| Observation | Value |
| --- | --- |
| Rebuilt unchanged old native | Exact original `06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6` |
| Candidate native | `b56c43f16722be2c8fc6fbe5c021ec292f9a6856783d946af56d97e91575e619` |
| Equal complete release-context digest | `5aa8f0b521fe60666789ebc2ba058b9015df9104d1287a7bfa0e22caf22cc1ab` |
| Baseline/candidate release command wall intervals, including cleanup | 306.830 / 297.753 seconds |
| Regression compilation/start interval, including cleanup | 112.361 seconds |
| Raw artifact | `12873294982`, 8,104,624 bytes, SHA-256 `01157cb749641900a3805bb0609d1fa62dc50dadf57c3cb4c0b0c250bccfa3ae` |

All three original artifacts remain retained and their ZIP hashes match the
official metadata. All 64 raw members were hashed and CRC checked; both nested
wheels/native hashes were independently inspected without installation or native
imports. The independent verification receipt is
`d9fae4da38009c1022bee51336f5fd838529ac5c9adcce8db8b375004dafbefd`.
The candidate/control after-source snapshots are absent, the manifest is
incomplete and the completion is negative. These partial observations grant no
historical reuse, qualified candidate binary or worlds. Existing wheels cannot
be rebound into a completed corrected build.

The source correction queries `sysconfig.LIBDIR` and `LDLIBRARY` using only the
exact selected Python interpreter with `-I -B`. It requires canonical paths
inside that interpreter's selected installation, verifies the shared-library
file and retains its path/bytes/hash. Only the `candidate-regressions` child's
environment receives that directory as `LD_LIBRARY_PATH`; arbitrary inherited
paths are never forwarded. Both release-build environments, flags, profiles and
their common context remain unchanged. The loader facts are retained separately
in raw/light evidence and the final manifest, with their child-only scope.

Rust assertions, D2, the resource helper, process controls and all budgets remain
unchanged. The corrected activation requires a fresh both-source build and
successful regressions, after source review. No corrected activation is implied
by this prepared branch.

## Source verification

The first pure source selection passed 103 guarded cases with zero native
imports, runtime-factory calls or blocked I/O. Additional PPID fallback cases
then passed in a 112-case guarded selection. The final selection passed 136
guarded cases, including 40 resource and 18 hosted-deployment fixtures. Eight
real Linux ownership probes passed in a separate reviewed
outer-process lane; its original eight missing-PROC_CHILDREN prelaunch failures
are retained. Final deployment-precondition/workflow changes have pure fixture
coverage and leave the qualified ownership path unchanged. Exact final source
hashes, counts and receipts are recorded when that qualification closes.

The subsequent D2 source selection passed 163 guarded pure cases in 0.41 seconds:
80 bridge contracts, 40 unchanged resource fixtures and 43 deployment fixtures.
It includes raw/light publication roundtrips for both readable-matching and
repeated-EACCES observations. The offline guard recorded zero native imports,
runtime-factory calls and blocked I/O attempts. No actual host precondition,
native build or ordinary simulation world ran in that selection. The qualified
process, cleanup and publication implementation is unchanged; the two new
publication tests use bounded fixture files and stub only live-child observation.

The loader correction passed all 182 guarded pure cases in 0.60 seconds, including
19 focused query/path/environment cases. The exact prospective activation-2 copy
passed the registered workflow contract and full unfiltered actionlint 1.7.12.
Those checks used injected interpreter metadata and synthetic library files;
no actual sysconfig child query, native library import, build or world ran.
