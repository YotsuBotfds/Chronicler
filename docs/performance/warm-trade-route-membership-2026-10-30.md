# Warm trade-route membership — bounded kernel optimization

This separate branch starts from `701bd3fe960d1761e9aa3c7c5d1d7bf41d00464d`.
It changes only `intelligence.has_active_trade_route` and adds focused tests.
No native, settlement, wealth-damping or kin-reader source is composed here.

## Source evidence and contract

`resources.get_active_trade_route_pairs` deliberately returns
`set(cached_pairs)` when its turn cache is current. That protects its caller
from mutating the private cache. `has_active_trade_route` previously used this
public getter for every membership query, copying all `E` route pairs before
checking one pair. The snapshot accuracy loop in `main.execute_run` queries
every non-self civilization pair: `C * (C - 1)` such copies per snapshot, even
when Phase 2 has already built the current cache. This is source evidence of
repeated copying, not a measured whole-turn bottleneck or speedup.

The optimization normalizes the requested pair exactly as before, then checks
membership directly in the private cache only when its turn matches and its
type is exactly the built-in `set`. It returns only the resulting boolean.
Cold/stale caches and foreign types, including set subclasses, still call the
original getter. The public getter still makes its defensive copy. No cache
or collection reference escapes this call; no new state or invalidation policy
is added. Pair iteration, perception arithmetic, random draws and simulation
phases are untouched.

This contract admits ordinary `WorldState` objects with stable primitive turn
and private cache fields, plus the stable-attribute stand-ins used in focused
tests. Fallbacks probe those fields before entering the getter, which reads
them again. Arbitrary stateful descriptors or equality callbacks can observe
those extra reads; their access-order parity is not claimed. Foreign cached
iterables still retain the getter's complete conversion order and exceptions
under the admitted stable world-field contract.

## Focused verification — 64 passed

The existing `tests/test_intelligence.py` gains 12 cases covering directed and
self pairs, Unicode names, empty/current caches, cold/stale/foreign caches,
set subclasses, conversion order and exceptions, live cache edits/replacement,
normalization errors before cache access, and the public getter's independent
copy. The original two-line helper is the membership parity reference.

After a different-author source review, the first ordinary offline-guard run
passed all 62 cases in the intelligence module and the two existing resource
cache cases: **64 passed, zero failed or skipped**. The guard reported no native
import attempts, blocked I/O or bridge-factory calls. No simulation turn or
native build was selected. Pytest's reported 0.29 seconds is not an external
wall-time measurement. Full standard CI and simulation trajectory comparison
remain open.

## Fixed method002 measurement

The first, separately registered method001 producer completed successfully,
but numerical qualification refused its CPU results: two candidate CPU
samples were zero (C10 complete graph, built-in set, trials 1 and 4), despite
positive wall durations. Its original results and refusal are retained; no
clock cause is inferred and no method001 CPU medians are promoted. It was not
rerun. The distinct method002 registration increased each timed helper trial
from 10,000 to **50,000 queries**, retained four raw clock endpoints, and flushed
each partial timing row before requiring positive elapsed times.

Method002's first attempt passed its ordinary guard and numerical qualification.
All **192 positive samples, 96 trial pairs and 16 fixed conditions** reconciled
with the raw timing journal, including endpoints, deltas, true-result counts,
medians and ratios. Every graph and fallback condition is reported below.

The original helper body and candidate ran in the same process on immutable
primitive `SimpleNamespace` fixtures. The eight graphs are C = 4, 10, 30, 60
with normalized undirected ring or complete unordered non-self edges. Each
has exact built-in set and set-subclass conditions. Ordered non-self queries
cycle for 50,000 calls per timed trial; ring cases include absent routes.
Fixtures are built outside timing. Each condition has 1,000 untimed warm-up
calls per helper and six interleaved trial pairs, with helper order alternating
by trial index. Pair normalization and the original getter's defensive-copy
cost are included. Separate untimed 10,000-call loops measure traced allocation.
There is no adaptive selection, early stop or retry.

The run used CPython 3.13.5 on Linux x86_64, CPU affinity `{0}`, one CPU,
512 MiB address space, 30 CPU seconds and a 110-second attempt ceiling. Host
load averages were [0.0, 0.0171, 0.0522] before and
[0.3994, 0.1128, 0.0845] after. Summed timed process CPU was 20.498874666 seconds;
this sum and pytest's 22.60-second report are not external whole-attempt wall,
CPU or RSS measurements.

The table uses the median of the six trials for each helper. Wall times are
microseconds per query. Ratios are original/candidate, so values below 1 mean
slower candidate execution. Wall change is candidate relative to original;
positive values are regressions. Peak bytes are additional traced Python
allocation in the separate loops, original to candidate; they are not RSS.

| C | Graph | Cache | Edges | Original wall µs/query | Candidate wall µs/query | Wall ratio | CPU ratio | Wall change | Traced peak B |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 4 | ring | built-in set | 4 | 0.4799 | 0.3880 | 1.237× | 1.199× | -19.13% | 320 → 208 |
| 4 | ring | set subclass | 4 | 0.4696 | 0.5685 | 0.826× | 0.857× | +21.04% | 320 → 320 |
| 4 | complete | built-in set | 6 | 0.4951 | 0.3755 | 1.318× | 1.200× | -24.15% | 576 → 208 |
| 4 | complete | set subclass | 6 | 0.5736 | 0.6818 | 0.841× | 0.824× | +18.86% | 576 → 576 |
| 10 | ring | built-in set | 10 | 0.5074 | 0.4137 | 1.226× | 1.200× | -18.46% | 832 → 208 |
| 10 | ring | set subclass | 10 | 0.5340 | 0.6716 | 0.795× | 0.874× | +25.76% | 832 → 832 |
| 10 | complete | built-in set | 45 | 0.9118 | 0.3968 | 2.298× | 2.303× | -56.49% | 2368 → 208 |
| 10 | complete | set subclass | 45 | 0.8248 | 0.9735 | 0.847× | 0.875× | +18.03% | 2368 → 2368 |
| 30 | ring | built-in set | 30 | 0.6411 | 0.3952 | 1.622× | 1.600× | -38.35% | 1372 → 236 |
| 30 | ring | set subclass | 30 | 0.6569 | 0.7400 | 0.888× | 0.846× | +12.65% | 1372 → 1372 |
| 30 | complete | built-in set | 435 | 3.4681 | 0.4177 | 8.303× | 8.700× | -87.96% | 16732 → 236 |
| 30 | complete | set subclass | 435 | 3.4185 | 3.5550 | 0.962× | 0.955× | +3.99% | 16732 → 16732 |
| 60 | ring | built-in set | 60 | 0.8962 | 0.4704 | 1.905× | 1.833× | -47.51% | 2396 → 236 |
| 60 | ring | set subclass | 60 | 0.9292 | 1.0105 | 0.920× | 0.920× | +8.74% | 2396 → 2396 |
| 60 | complete | built-in set | 1770 | 12.5454 | 0.4325 | 29.005× | 28.508× | -96.55% | 65884 → 236 |
| 60 | complete | set subclass | 1770 | 13.0387 | 14.2586 | 0.914× | 0.913× | +9.36% | 65884 → 65884 |

For exact built-in sets, wall ratios range from 1.226× to 29.005×. The C60
complete graph uses 96.55% less kernel wall time; the C60 ring improves 1.905×.
The saving grows with copied edge count, as expected from avoiding the full
set copy. **All eight set-subclass fallbacks are slower**, by 3.99–25.76% wall
time. They still copy through the original getter and pay the added cache
checks. These regressions are part of the result and a reason to keep the
optimization limited to ordinary current-turn built-in sets.

## Evidence and limits

Root observed the first focused process and method002 process exit 0, then
independently reconciled the saved numerical evidence without replaying the
kernel. Evidence is retained outside the repository; this commit contains no
logs or machine-specific execution artifacts. The SHA-256 identities are:

- Focused 64-case root POST: `400a5fd90d74a43c8a35e860e823248e127c12fcce38c7f3eedcf21bc28dd0d2`.
- Method002 result (96,878 bytes): `db0302c3621db0f70172bc82445a9fd94805570777e98b1ed9c2aeb04d876a75`.
- Method002 raw journal (69,159 bytes): `f6592aa4add95d258e9eaa9271c59c299913034414b246839c6e53dbcc00a679`.
- Method002 qualification: `c324f2404a2e93eca956d946c7badb2e889c3329a8c55e98a7d1c2bf2c1f9bb8`.
- Method001 CPU-refusal record: `5aaba8023c7a7cf11c7c6bd748beacf74c0da815cce8fc86c2f78266f55b737f`.

This measures a warm-cache namespace kernel. It does **not** measure production
`WorldState`/Pydantic private-attribute lookup costs, whole-turn speed, total RSS,
checkpoint behavior, RNG identity, native performance or scientific outcomes.
The tests support the stated membership and error contracts; they do not prove
full simulation trajectories. Full CI, native/source compatibility and any
production performance or population gate require separate decisions. No
network, push or CI dispatch was performed during this branch's preparation.
