# Fixed historical CI duration audit — inactive draft

The reader inspects two already completed Python jobs from source
`d0281e5f57c508f27cea1676f36e0e6ed1225c9d`, Tests run `40782783254`.
It does not rerun tests, build or install an extension, import the simulator,
launch worlds, modify scientific reports, or activate sharding.

The draft branch is `lead/cloud-ci-duration-audit-draft-20261029`.
The new workflow triggers only on the distinct
`lead/cloud-ci-duration-audit-20261029` branch. The draft is inactive pending
lead review. Main and the running full-gate controls remain unchanged.

## Fixed inputs

| Lane | Artifact ID | ZIP bytes | ZIP SHA-256 |
| --- | ---: | ---: | --- |
| Native | 12858492130 | 133807 | `e045c31693155bb32d38d4952d7b53ec9c529fd89421435d242c5a6f08bc820c` |
| No Rust | 12857957732 | 135280 | `8e8d855f5b6dbd3d40cc8d194cd6bfd40b43cd80c7d71c5e0f49957f643dcb6d` |

Official artifact metadata was rechecked through the connected GitHub API.
Both are source-bound, unexpired artifacts from that run. The actual ZIP/XML
inspection remains unrun until the reviewed Action executes.

The reader additionally obtains the fixed run's metadata, complete bounded
artifact/job lists and the original two job logs. It verifies source, run,
attempt, producer job, success, artifact identity and outer ZIP digest. The
native artifact's retained identity must name the frozen source, Python 3.13,
a compiled `.so`, all three native classes and a SHA-256. This is a historical
receipt check; the extension is not loaded or newly qualified.

## Safety and output

The reader reuses the completed default-output reader's immutable ZIP path,
file-type and redirect checks. That helper's exact SHA-256 is pinned before
import and checked again at completion. Its file is unchanged. The new
transport permits only seven fixed API resource identities (three metadata
endpoints, two ZIPs and two job logs). The step-scoped bearer token is removed
from the process environment before source Git commands. It is sent only to
`api.github.com`; each approved HTTPS storage redirect receives a fresh
request without authorization. Signed URLs and network exception text are
never written to output. There are no retries or pagination.

Metadata is capped at 2 MiB per response and lists at 100 entries; incomplete
lists fail. Logs are capped at 8 MiB each. Pinned archives are under 136 kB,
contain exactly the one or two expected flat regular files, and allow at most
16 MiB per expanded member and 32 MiB total. Duplicate/case aliases, traversal,
symlinks, encryption, unsupported compression, CRC errors and extra members
fail. No archive files are extracted into the checkout.

JUnit must be UTF-8, with no NUL, DTD or entity declarations. Byte, depth,
element, attribute and testcase bounds apply. The reader requires one flat
pytest suite, finite nonnegative bounded decimal durations, successful outcomes
and independently matching header, serialized-parent, skipped and terminal
subtest counts. Pytest 9's successful subtest excess is preserved explicitly;
no duration rows are fabricated for it. Duplicate testcase identities retain
their original XML ordinal. Source modules are attributed using exact tracked
Python paths at frozen d028; unknown classnames stay explicitly unattributed.

The output directory must be fresh and outside both checkouts; each derived
report is capped at 32 MiB. Original ZIPs,
logs and API bytes are retained with hashes. `duration-report.json` includes
all testcase rows, file totals, unknown attribution, the original native
receipt and two-/three-way prospective file partitions. `duration-summary.md`
shows separate clocks and the largest files/testcases. `audit-result.json`
is positive only after both inputs and unchanged-source checks complete;
failures retain a negative receipt and any downloaded evidence. No evidence
or credentials are committed.

## Historical clocks and limits

The original native terminal reports **7,800 passed, 6 skipped and 526
successful subtests in 655.82 seconds**. The no-Rust terminal reports **7,486
passed, 306 skipped and 526 successful subtests in 374.80 seconds**. These were
read from the original completed job logs, not rerun here. XML must independently
reconcile them before the reader emits a completed audit.

Official step timestamps show native job 844 seconds, wheel-build step 159
seconds and pytest step 662 seconds; no-Rust job 391 seconds and pytest step
379 seconds. The API's timestamps have one-second resolution. The reader
recomputes these from retained metadata rather than substituting them for XML
or pytest clocks.

A testcase duration is pytest's setup/call/teardown attribution. It is not a
CPU profile or a guaranteed independently movable cost. Shared fixtures,
collection, process startup, building, installing, uploads and Actions overhead
have different accounting. XML rounding can accumulate over thousands of rows.
Native and no-Rust lanes run different tests and skips on separate VMs; their
elapsed difference is not a simulator speed comparison.

The deterministic largest-first two-/three-way partitions are proposals using
historical file totals. They exclude unknown attribution and predict only
attributed loads. Sharding would repeat native build/install and some fixtures,
change contention, and require fresh complete selection/identity/count checks
plus an aggregate success gate. There is no claimed speedup or activated shard.
Actual rankings and practical next experiments must wait for the real audit.

## Pure checks

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p test_ci_duration_audit.py -v
```

The focused stdlib suite uses synthetic ZIP/XML/API/log fixtures and mocked
transport. It covers valid pytest-9 parent/subtest accounting, duplicate identity
retention, exact module attribution, malformed XML, DTD/entity/encoding attacks,
nonfinite/negative durations, wrong counters, ZIP alias/traversal/symlink cases,
stream bounds, credential-free public hops, sanitized errors, source/artifact/job
mismatches, failed producers and retained negative receipts. It runs no native
code, network, simulator subprocesses or scientific jobs.

Local focused verification: all **18 stdlib tests passed** on Python **3.12.14**
with synthetic inputs and mocked transport. The inactive Action specifies Python
3.13 and reruns those contracts before the real artifact read. No real ZIP/XML
audit result, native execution result or test speedup is asserted by this draft.
