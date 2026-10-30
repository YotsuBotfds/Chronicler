# Trusted hosted native functional smoke — source only

This small staging829 child adds an opt-in observation script and dedicated
workflow. Publish reviewed code on `lead/native-functional-smoke-source-20261030`;
a separate root-approved push of the same SHA to
`lead/native-functional-smoke-20261030` starts the first job. Do not duplicate it
with a manual dispatch. Standard workflows/default owners stay unchanged.

The job builds a fresh own-source wheel with the ordinary locked native CI path
and installs it into its fresh locked environment. It reuses
`native_ci_shards.current_identity` and `native_wheel_receipt.wheel_receipt`,
recording a distinct custom functional-build kind and the real job name. It
does not call record-build, spoof GITHUB_JOB or claim standard producer eligibility.

The functional step saves three complete class schema tuples, empty care API
results and full before/after persistent bytes, then selects exactly the two
existing no-tick configuration/schema contracts named in the script. Their
reachable helpers instantiate tiny native region fixtures directly. Neither
requests a fixture, invokes a World/tick/restore, or activates an autouse fixture.
The declared paths create three simulators total: one empty plus one per test.
Require two passes, zero skips and exact raw JUnit membership; interface
availability is not an actual decision capture or historical Kin exposure.

The functional command tree has110s/30CPU/oneCPU/2GiB per-process AS and joint
2MiB diagnostics, with GNU time recording actual command-tree scope. Build,
outer wrapper/sealing/upload overhead is separate. Max-child RSS is not
aggregate RAM. A5MiB smoke artifact contains bounded states/report/log/JUnit/
measurement/outcome; the separately verified builder artifact is<=9MiB. The
ordinary45-minute job includes fresh Rust compilation; that build is not inside
the110-second smoke bound. Before setup, require8GiB free hosted disk; use one
fresh Cargo target with no release-cache restore or duplicate target. Record
actual target/venv and free-disk data. Peak build storage remains unmeasured;
this is not a whole-job disk/owner fit result.

The current source is UNRUN. Root source/pipeline-storage review precedes any
publication/run. No local native/build/test/World operation occurred in source
preparation. The prior C fixture result retains its sampled-kernel scope, and
the old32MiB sandbox, runtime leases, whole-owner fit, installed capture,
trajectory/RNG/science and main promotion remain separately held.
