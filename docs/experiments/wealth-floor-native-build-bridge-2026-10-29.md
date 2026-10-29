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

## One future job, presently disabled

The [workflow template](wealth-floor-native-build-bridge-workflow.yml) lives
under `docs/experiments`, with a false job guard. It installs no active workflow
under `.github`. Future activation is recognized only on the specifically
registered `lead/cloud-wealth-floor-native-build-bridge-20261029` branch and
workflow-file push path. Pure tests seal every other command, source, version,
environment setting, budget and artifact-retention rule. They recognize both
the dormant and exactly activated states, avoiding a preparation-only assertion
that would reject its own reviewed activation.

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

The shared `wealth_floor_hosted_deployment.py` precondition additionally requires
the sealed direct hosted-runner context, PID1 `systemd` and matching self/PID1
cgroup namespace identities. It refuses unsupported topology before any build
or large archive transfer. This is recorded VM-context evidence, not proof
against namespace-invisible provider ancestors. The generic memory helper stays
unchanged and reusable by the separate baseline-audit controller.

The shared precondition refused the separate baseline-audit activation
`40815630794` before resources, source snapshots, client creation or archive
transfer. The retained record does not identify which deployment predicate
failed. Actual runner compatibility therefore remains unqualified; this build
lane stays inactive pending that diagnosis. No predicate is weakened here.

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
