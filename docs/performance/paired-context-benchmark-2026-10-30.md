# Paired compiled context measurement — source only, 2026-10-30

This opt-in tool compares the native context batch reader before and after its
five-line early-completion change. It changes no product caller, native source,
dependency, default or checkpoint format. All checks, builds and measurements
against this new controller source are UNRUN at author freeze.

The controller is based on fa5; its own native09ec is not measured. Two sibling,
clean measured checkouts have explicit identities:

| Role | Commit | Native tree |
| --- | --- | --- |
| parent | 82902b85a94ebb008168cb06195b031c6ee1eb92 | a840fd12462deedf92b256878d474404eeac892d |
| child | ef716e7f0d5ba0fa1e4c53774389201bcc23720d | 8e3ec0e90e184bcb9f11d6bd21eb5d275e7bf9db |

Driver hashes and actual GitHub SHA/job stay separate from measured identities. No driver is copied into a measured tree. One builder and
Python/Rust toolchain build two fresh locked release wheels serially, with two
initially empty Cargo targets and isolated role venvs. Each installed extension
must match its own wheel bytes, prefix and real compiled exports. The two builds
have separate40-minute limits in a120-minute job, outside comparison limits.

The fixed matrix keeps21 conditions: slots512/8192/65536 × requests1/50 ×
prefix/spread/missing, plus8192-slot spread requests1/10/50 with eight directed
Friend bonds per queried live ID. Memories stay empty. Seed42/exact scale/eight
regions and the initialized-agent fixture remain; no World or physics tick runs.
Three trials retain20,000 requested records/helper and200 untimed warmup records.

There are126 serial source/case/trial workers and252 PLANNED helper samples,
126 per source. A worker loads its role wheel and creates one fresh pool;
both scalar and batch helpers use that pool, then the worker exits and is reaped.
Source and helper order alternate by `(case + trial) % 2`. Unlike fa5's pool
reused across three trials, this cohort creates a fresh pool per trial. No old/new data pooling
or claim that this replaces fa5's first result is supplied.

Original scalar/batch kernels, consumption, query layout, payload fingerprint
and four-endpoint wall/process-CPU clocks stay unchanged. Untimed work still
counts toward whole-worker resources. Joint scan bounds are169,205,760,000 scalar
slot visits and28,361,932,800 batch visits, excluding search/sort/conversion/setup
work; child early completion can reduce its bound.

Before/after each trial, actual scalar and batch payload digests must agree,
including f64 need bits and duplicate/missing controls. The controller also joins
parent/child observed IDs, positions, payload/control digests and checksums for
every case/trial. Reports retain every raw sample and regression; scalar drift
is shown rather than normalized away. Nonpositive clocks or checksum refusals
retain their rows and suppress affected summaries while the registered schedule
continues. Identity, setup, worker or payload failure aborts remaining work with
explicit failed/not_run states.252 actual samples are never claimed after abort.

One JOINT comparison envelope is600 wall seconds,540 CPU seconds, one allowed
CPU and2GiB application address space. Immediate KILL has no extra grace period.
Controller soft AS128MiB and worker hard AS1920MiB partition the budget; the
controller inherits a2GiB hard ceiling only to bootstrap workers. Controller and
each worker have24s CPU limits; whole waited workers share512s credit with a full
24s reservation before each launch, leaving4s supervision/accounting slack.
Only one Native pool may exist. Parent-death cleanup and reap prevent orphaned
workers. Actual waited CPU is separate from timed-helper CPU sums. These are
registered guards, not an RSS or kernel aggregate-cgroup guarantee.

Structured bodies share2MiB, including owner, partial and error fragments.
Both raw wheel files together share16MiB. Owner serialization is charged before
admission; overflow keeps bounded refusal metadata. Successful identity wheels
remain available after comparison failure through explicit always() conditions.
Artifact ZIP sizes and local wheel/ELF acquisition remain separate gates.

Publishing `lead/paired-context-benchmark-source-20261030` is inert. Only a
separately approved push to `lead/paired-context-benchmark-run-20261030` activates
the new workflow; any catalog-supported dispatch is restricted to that ref.
Paths derive from RUNNER_TEMP inside shell steps, never runner context in job env.
Main remains untouched. One new guarded fake chunk keeps the previous40 chunks,
27 legacy contracts and110-second limits.

fa5's first126 samples/approximately94× batch regression,
9705's invalid-workflow failure, b32's first care-pin failure and ef716's repair
remain separate historical evidence. ef716's first Tests41004287197/1 has nine
successful jobs per root's official metadata observation; no paired timing follows
from that result. Kernel ratios imply no World, RNG, checkpoint, whole-turn,
population-capacity or scientific qualification.
