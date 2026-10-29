# Dormant deployment-only diagnostic registration

The first byte-audit run, `40815630794` at `9aae9ab1`, refused deployment
admission before any resource or archive operation. Its broad receipt leaves
the failed environment/PID1/namespace predicate unknown. This separate source
prepares a small observation-only diagnostic; it is not activated.

`scripts/wealth_floor_deployment_diagnostic.py` defaults to inert output.
Explicit observation categorizes only `GITHUB_ACTIONS` and
`RUNNER_ENVIRONMENT`, reads PID1 comm with a 129-byte sentinel, classifies it
as systemd/init/tini/bash/python/other, and records cgroup namespace format,
equality, stable rereads and fixed error categories/numeric errno. It never
prints arbitrary comm, environment, namespace or error text. The recorded
predicate follows unchanged `ef872ace`'s order over the current diagnostic's
observations; it does not rewrite the earlier failed run's unknown predicate.

The unchanged `44f1e1d` resource helper can observe host/visible cgroup
headroom through an injected bounded reader. All underlying file reads are
at most 129 bytes, namespace values admit at most 128 bytes and aggregate
observed metadata is capped at 64 KiB. If memory metadata exceeds that budget
or the hierarchy is unsupported, the receipt reports an unavailable
observation. It retains numeric availability/limits and visible-ancestor count
without path dumps. No result grants admission or proves invisible provider
limits.

Execution uses one process pinned to one available CPU, thread caps one,
a hard 30-second wall timer and a five-minute job timeout. Output is capped
at 64 KiB and written to a fresh exclusive regular file. Fatal failures retain
only a fixed stage/reason and numeric errno. There is no token, HTTP, archive,
build, native import, world, sudo or privilege path.

The dormant workflow stays outside `.github/workflows`. A future exact copy
would use only branch
`lead/wealth-floor-deployment-diagnostic-activation-20261029` and path
`.github/workflows/wealth-floor-deployment-diagnostic.yml`. Tests admit both
prepared and byte-identical known-active body forms, avoiding an obsolete
preparation-only absence assertion. Root must review the concrete source and
fixtures before any single remote diagnostic activation. Both shared helpers,
the failed audit activation and main remain unchanged. No real local probe is
authorized or claimed by these pure injected fixtures.

Qualification: 88 guarded cases passed in 0.21 seconds (30 diagnostic,
40 unchanged resource and 18 unchanged deployment fixtures). The guard recorded
no native imports, blocked IO or runtime-factory calls. Unfiltered and template
actionlint, diff checks and the inert direct CLI passed. Independent read-only
source review found no concrete blocker in bounds, predicate ordering,
sanitization or dormant activation scope. Both shared helper hashes remain
unchanged. This prepares source only; no real local probe, remote diagnostic,
archive transfer, build or world was run.
