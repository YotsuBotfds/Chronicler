# Validate workflow semantics before running expensive lanes

Passing test jobs does not prove that every workflow can register. The retained
9705 run exposed an invalid job-level environment expression outside those
passing jobs. This lane checks every tracked `.github/workflows/*.yml` and
`*.yaml` together, including dormant workflows and the validator itself.

The lane uses upstream actionlint v1.7.12, whose tag resolved to
`914e7df21a07ef503a81201c76d2b11c789d3fca` during source preparation. The
release is marked mutable upstream, so the download checks literal SHA-256
pins for both its checksum file and Linux amd64 archive before extracting the
binary. It records the actual binary hash and version. These are upstream
release identities, not a claim of a reproducible build.

The command is `actionlint -shellcheck='' -pyflakes=''` followed by one explicit
array of all tracked workflow YAML paths. No ignore flag or new exception
configuration is added. An existing actionlint configuration remains effective
and its hash is recorded. ShellCheck and Pyflakes are deliberately disabled:
this lane validates GitHub workflow keys, expressions, contexts, dependencies
and related actionlint semantics. It does not validate shell/Python behavior,
run repository scripts, build native code, or replace the actual hosted jobs.

Publish reviewed source on `lead/workflow-semantics-source-20261030`; that push
does not activate this lane. A separately approved push of the same SHA to
`lead/workflow-semantics-20261030` starts its first hosted lint. Do not also
dispatch that first attempt manually. Future pull requests touching workflow
or actionlint configuration paths use normal checkout of their default merge
source, read-only contents permission and no secrets. Manual dispatch is guarded
to the dedicated run branch. Existing workflows and default test owners are
unchanged; main remains untouched.

The job has a five-minute ordinary hosted limit. Only the lint command has the
60-second, 20-CPU-second, one-CPU, 2-GiB address-space and joint 2-MiB diagnostic
limits; download, extraction, version observation and artifact upload are
outside that smaller command scope. A limit or nonzero lint exit fails the job.
Raw diagnostics, actual exit status, selected NUL-delimited paths, workflow
hashes and tool identity are retained, including a negative. The source-only
candidate has not run actionlint locally or on GitHub. Its first actual result
must be reviewed before claiming the current workflows pass.

When the same pinned tool is already available locally, developers can run the
same two disabled-integration flags against all tracked workflow paths before
publication. This change does not install a local tool or add literal tests.
