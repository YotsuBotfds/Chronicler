# Inactive second baseline-audit source: explicit denied-namespace scope

This separate source prepares a second byte-audit attempt. It is inactive and
requires root review before any new activation. The original prepared source
`0cd03109`, failed activation `9aae9ab1` and diagnostic `cc2fea80` remain frozen.
The old failure's particular predicate remains unknown.

The [first failure](https://github.com/YotsuBotfds/Chronicler/blob/a4341f9f36db4a5af0e7a908665f67b4b6cc9183/docs/experiments/wealth-floor-baseline-audit-result-2026-10-29.md)
occurred before archive/resource work. A separately verified
[diagnostic](https://github.com/YotsuBotfds/Chronicler/blob/69d0f178e2318868cc0f370f6bf8fac5dc997e5d/docs/experiments/wealth-floor-deployment-diagnostic-result-2026-10-29.md)
observed stable registered runner flags, PID1 systemd and own cgroup namespace,
with PID1 namespace readlink denied by `EACCES13` twice in that fresh context.
Those observations do not retroactively determine the older job's cause.

Root authorized the small shared D2 deployment policy. Its exact helper is
SHA-256 `d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8`;
the matching pure fixture file is
`9ef3311485f045906160e855096a115986a6d9ac7ad342ed7e1ffd38ae7fa340`.
Both are copied byte-for-byte from the builder's frozen pair. D2 admits only
initial and repeated PID1-namespace `EACCES13` under stable hosted flags,
PID1 systemd and valid stable own namespace. Readable namespaces must match.
Other errors, missing errno, malformed values, mismatch or changed observations
still refuse. No privileged access is attempted.

The accepted denied observation records `pid1_cgroup_namespace=null`,
`namespace_equal=null`, `namespace_equality_verified=false`, status
`unverified_permission_denied` and both errno values `[13,13]`. This is an
explicit direct-hosted-VM context assumption with visible-scope limitations;
it proves neither unavailable PID1 equality nor hidden provider limits. The
controller preserves these facts and its metadata no longer requires or
asserts verified equality on this narrow denied path. Readable matching
observations retain verified equality. Registered D2 refusal codes are
preserved in bounded negative receipts without arbitrary exception text.

The new producer/template branch is exactly
`lead/wealth-floor-baseline-audit-activation-2-20261029`. The workflow path
filter stays exactly `.github/workflows/wealth-floor-baseline-audit.yml`.
The dormant body remains outside active workflows until a separately reviewed
byte-identical activation copy. The old activation branch is not moved.

All five historical artifact IDs, ZIP digests, original expiry, comparison
seal, historical candidate roles, file inventories, methods and scientific
policy are unchanged. Generic resource helper `44f1e1d` remains byte-identical.
Disk/RAM admission stays 12/2 GiB and running floors 3/1 GiB. Transport remains
1,200 wall/300 process-CPU seconds, audit 1,800/900 on its one continuous
budget, controller 3,300 wall seconds and job 60 minutes. All four source
snapshots, final checks, finite 29-file/192-MiB publication bounds and completed
producer/publication requirements remain. Candidate-world proof pins stay
null; there is no build or world launcher.

The complete guarded selection passed **234 cases in 1.01 seconds**: 80 job,
40 unchanged resource, 71 admission and 43 D2 fixtures. This covers the original
207 selection plus D2/refusal/metadata cases. The existing early-refusal fixture
now constructs the registered `namespace_mismatch` code required by D2's
closed exception API; its refusal assertion is unchanged. A real D2 policy
call over injected observations proves the controller retains unverified
equality. No real local probe, historical plan, download, audit, native build
or world was run. Original failures and all earlier evidence remain intact.

Unfiltered and template actionlint, diff checks and the inert direct CLI pass.
Independent read-only source refresh found no concrete blocker in D2 scope,
unverified-equality propagation, safe refusal codes or activation-2 binding.
These checks qualify source only; root must review the frozen corrected commit
before a separate actual workflow copy, final-copy checks and one activation.
