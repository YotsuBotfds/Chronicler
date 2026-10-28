# Household decision journal: not accepted for promotion

The exact journal prototype passes its focused correctness checks and reduces
the isolated phase substantially in concentrated 100k-agent migration fixtures.
It **does not meet the registered whole-workload acceptance rules**. Keep the
prototype separate from production. The observed variability also prevents a
confident claim that the prototype itself causes the estimated normal-run
regression. No fallback, threshold, workload or seed was tuned after this result.

The [prospective contract](household-decision-journal-2026-10.md) was committed
as `92e30ee1` before implementation. Production code is `38ced96d`; the additional
adversarial test is `c6b7b33f`. The full-boundary fixture was frozen in `7d8d3b38`
before exposure runs. `2883d930` transparently clarified the previously unranked
full-workload boundaries after the exposure pilot and before qualification:
both complete-process and `execute_run` CPU must meet the criteria. A favorable
warmed window cannot qualify a failed full-workload comparison.

## Exactness and build

The retained test reference is the old `2dd47347` consolidation function,
byte-identical after only function-name/visibility normalization. Its SHA-256
is `257a916b779f60686efa3c16661cec2e755df1af1b3ac665773d6f29e505518b`.
The new sparse first/last-entry journal preserves mutable first-match queries,
remove/reinsert behavior, final last-entry deduplication and output order.
Suppressed primary actions remain immediately visible to later household checks.

Five optimized Rust tests pass; the opt-in benchmark is ignored by default.
They include 768 seeded inputs, fresh and stale ID lookups, two successive
phases, duplicates/conflicts, shared dependents, asymmetric overlapping pairs,
dead/recycled/travelling slots and married minors. Complete pending vectors
(including untouched floating-point bits) and persisted household counters
match the reference. The review-requested dependent-rebellion case covers
later approval and later catastrophe cancellation while retaining earlier
follower records. The coordinator also retains the full Rust qualification;
this report's directly executed focused receipt is separate from that run.

The release wheel uses Rust tree `f083f3da388312c66dc2820ddfe4e2369719d5ce`
from `c6b7b33f`, unchanged compiler/profile/dependencies and one compiler job:

| Item | SHA-256 |
| --- | --- |
| Baseline extension | `fb20dbc81828420fedc9a0b25fb8791a694a158d2c502ec915b8132a52875317` |
| Candidate extension | `9f494a2c6622f8ee80528abad378f3ec5c4e3663587a0400c73e6100208f86e3` |
| Candidate wheel | `192c5bab315153db85744d31987391a3dd957f3350d37412d299e74f5beacefa` |

Real Agent/Ecology/Politics classes and a fresh constructor were verified.
All three complete native checkpoint schema tuples match the baseline exactly;
extension identity itself changes. There are no new persistent fields, RNG
streams, enums or native APIs. No full native Python suite or new nine-case
matrix is claimed for this unpromoted prototype.

## Isolated phase screen

These are same-binary old-reference/new-kernel **wall** medians, five
interleaved pairs, at `c6b7b33f`; they are not process CPU or whole-turn gains.
The test asserts complete decision/counter byte equality before timing.
FNV output fields are fast checksums, not cryptographic identity evidence.
The first screen from `38ced96d` is retained separately.

| Fixture | Baseline ms | Journal ms | Ratio of phase medians |
| --- | ---: | ---: | ---: |
| 20k, shock, spread | 3.791 | 1.840 | 2.06 |
| 20k, shock, concentrated | 4.287 | 2.227 | 1.92 |
| Near 100k, shock, spread | 17.485 | 11.953 | 1.46 |
| Near 100k, shock, concentrated | 50.774 | 11.064 | 4.59 |
| Near 100k, concentrated, one dependent | 64.319 | 15.316 | 4.20 |
| Near 100k, cancellation-heavy | 18.897 | 8.994 | 2.10 |

Normal cases were explicitly repeated rather than hidden behind the shock
result. Pooling 25 paired phase samples, 20k spread is 1.1385 to 1.2007 ms
(62 microseconds worse); 20k concentrated 1.2071 to 1.2145 ms; 100k spread
7.4622 to 7.5510 ms; 100k concentrated 7.5287 to 7.1956 ms. At 1k, spread
is 48.44 to 45.35 microseconds and concentrated 47.31 to 46.64 microseconds.
No small-bucket fallback was introduced. Separate 100k concentrated-shock
fixture processes peak at 40.59/41.06 MiB RSS; that is whole-process RSS,
not an isolated scratch-allocation measurement.

## Full workloads and preserved negative result

Both interpreter executable bytes, Python build/sysconfig/optimization flags,
all installed distribution versions, complete non-bytecode runtime package
trees and actual loaded-library hashes match. Only the intended native
extension differs. This includes NumPy, SciPy, Arrow, Pydantic/core, arro3 and
the other required packages. All runs use one Rayon/OpenBLAS/OMP/MKL thread
and `PYTHONHASHSEED=0` on the same Xeon Platinum 8573C host (five visible CPUs,
four-CPU cgroup quota). Quiet windows pause the two gates, observer and queued
Python qualification worker, with coordinator pause/resume acknowledgements.

The unwrapped default workload and the fixed family-cohort food shock each
use seed42, 20k target, 12 template regions/four civilizations, 20 warm-up and
eight measured turns. Each has five complete base/head pairs, with alternating
arm order. Total active quiet windows are 62.763 and 50.779 seconds. Every arm,
process receipt and actual run file is retained.

The shock pairs insert the same 6,480 sorted adult marriages. The registered
origin is region9/Sapphire Coast, adjacent to regions2,5,7. Measured turns
contain 1,628–3,904 actual migrations and 808–2,041 household followers per turn;
rebellion/catastrophe cancellations are zero and retained as zero. Complete
exposure/population records match across every arm and pair. This confirms
exposure, not a balanced physical food intervention.

The table reports the **median of the five paired baseline/candidate ratios**
and their full range. Values above1 favor the candidate. They are not ratios
of marginal medians. Wall results are retained independently of CPU results.

| Workload and boundary | Median paired ratio | Paired range |
| --- | ---: | ---: |
| Default, complete process CPU | 0.9474 | 0.8248–1.1638 |
| Default, complete `execute_run` CPU | 0.9570 | 0.8082–1.1777 |
| Default, complete process wall | 0.9472 | 0.8222–1.1479 |
| Default, complete `execute_run` wall | 0.9572 | 0.8061–1.1597 |
| Default, warmed window CPU | 1.0286 | 0.7996–1.1955 |
| Default, warmed window wall | 1.0233 | 0.7990–1.1931 |
| Shock, complete process CPU | 0.9642 | 0.8827–1.3026 |
| Shock, complete `execute_run` CPU | 1.0108 | 0.9158–1.3296 |
| Shock, complete process wall | 0.9694 | 0.8818–1.3015 |
| Shock, complete `execute_run` wall | 1.0156 | 0.9134–1.3311 |
| Shock, warmed window CPU | 1.0206 | 0.9353–1.2610 |
| Shock, warmed window wall | 1.0185 | 0.9354–1.2642 |

The shock fails the required 5% gain on both full CPU boundaries. The normal
point estimates exceed the 3% regression limit, while the wide paired ranges
make a confident causal regression claim inappropriate. Neither warmed-window
results nor the isolated phase result supplies a pass or wall-speed claim.

The initial exposure pilot remains exploratory: 10 actual run artifacts match
with only the established bundle timestamp normalization, including decoded
and raw bundle checks. Its warmed CPU is 2.485 to 2.144 seconds, complete-run
CPU 6.970 to 7.385 seconds and complete-process CPU 8.151 to 9.536 seconds.
The prematurely started shared-load qualification attempt is preserved with
`ABORTED.json` and excluded. No favorable arm or negative result was discarded.

External receipts are under `/workspace/chronicler-native-scaling-evidence`:
native/environment identities, reference hash, both optimized focused logs,
all phase screens, the pilot, aborted attempt, quiet-window acknowledgements,
frozen harness/runner hashes and every individual paired timing. The candidate
wheel/environment/cache remain intact. Further candidates or larger whole-run
experiments require a separate prospective amendment and CPU allocation.
