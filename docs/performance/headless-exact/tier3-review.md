# Tier 3 release and evidence review

Reviewed on 2026-10-05 against public baseline `edf72991cad58d6670b1f382c33d50d903a6054a` (PR #13 included). This review used source, reports, fixtures, and Tier 1/Tier 2 findings only. No timed workload, mass test, native build, external write, or private science source was executed or transferred.

## Recommendation and release gate

Approve the narrow snapshot optimization for public transfer. The final-tree exact-equivalence run and duplicate-name golden regression pass, with no identified release-blocking semantic defect. Its supported benefit is fewer repeated accuracy computations and a faster perception microbenchmark. Current evidence does **not** establish a reliable overall simulation or `execute_run` speedup, a memory improvement, or a benefit in native/hybrid/live modes.

Final evidence independently inspected: `after-final/comparison.json` passes environment and exact equivalence for all three workloads, and every `after-final/report.json` module hash matches the current source. The completed non-slow suite reports **2,813 passed, 121 skipped, 9 deselected in 70.24 s**. `final-regression-tests.log` reports **60 passed in 1.50 s**, including the newly added duplicate-name golden test. The full-suite run preceded that final added test; the focused run covers it afterward. Initial `after/report.json` predates the duplicate-name fallback and remains evidence only for its recorded source tree.

## Defensible performance claims

`paired-boundaries.json` contains three alternating baseline/candidate pairs using the standard seed-42, 60-turn, four-civilization, twelve-region workload. These are diagnostic medians, not confidence intervals.

| Measured boundary | Baseline median | Candidate median | Ratio | Defensible interpretation |
| --- | ---: | ---: | ---: | --- |
| Frozen-world perception cache/errors, repeated 80 times | 0.124178 s | 0.080717 s | 1.538x | About 35.0% lower time in this specific microbenchmark |
| World generation plus simulation turn loop | 0.147902 s | 0.138773 s | 1.066x | Control; unchanged simulation mechanism cannot justify attributing this difference to the optimization |
| Warm `execute_run`, including world generation and artifact I/O | 0.383062 s | 0.391389 s | 0.979x | No demonstrated whole-run benefit |
| Fresh interpreter CLI after equal prewarming | 0.682943 s | 0.548928 s | 1.244x | A diagnostic observation with startup/filesystem variance; insufficient for a general CLI speedup claim |

The initial `snapshot` label is narrower than full snapshot construction: its worker computes the existing pair cache and `perception_errors` on one final, frozen world. It does not construct `TurnSnapshot`, save artifacts, cover different turns, or perform the final implementation's unique-name scan. It hashes the final repeated result, proving equal results for that fixed world rather than full repeated RNG-trace equivalence. The separately measured headless runs provide the stronger actual-execution equivalence evidence.

The strengthened harness was rerun in `paired-final.json`, with source/environment/script provenance and the uniqueness check included. Its candidate source manifest matches the final headless manifest; its baseline manifest matches the verified public baseline; its environment matches both; and its script hash matches the current paired harness. Final three-pair medians are:

| Measured boundary | Baseline median | Candidate median | Ratio |
| --- | ---: | ---: | ---: |
| Frozen-world perception cache/errors, repeated 80 times | 0.095468 s | 0.074890 s | 1.275x |
| World generation plus simulation turn loop | 0.119962 s | 0.128571 s | 0.933x |
| Warm `execute_run` | 0.310155 s | 0.287682 s | 1.078x |
| Fresh-process CLI | 0.695610 s | 0.684635 s | 1.016x |

The final microbenchmark has about **21.6% lower median time**, continuing to support the narrow mechanism. The final execute median is lower, but initial paired execute was slower and the unchanged kernel control varies in the opposite direction. Three pairs across these noisy subsecond boundaries establish neither a reliable whole-run gain nor a regression. The final CLI result also illustrates why the initial 1.244x observation should not become a release claim. The updated microbenchmark performs the uniqueness scan for both baseline and candidate; this matches its own comparison task but slightly overstates original-baseline work relative to production. Retain the complete samples and scoped wording.

The earlier unpaired three-repeat headless medians were 0.028671 to 0.035091 s (single), 0.366223 to 0.439454 s (standard), and 0.303379 to 0.302320 s (wide). Preserve these observations alongside the paired data. Profiling is separate instrumentation: standard `compute_accuracy` calls fell from 3,991 to 1,036; wide calls fell from 4,889 to 1,418. These counts substantiate the mechanism. Profile totals and tiny peak-tracemalloc deltas do not substantiate whole-run or memory claims.

The final headless candidate medians are 0.022088 s (single), 0.341075 s (standard), and 0.300843 s (wide), compared with the original frozen baseline above. Final traced-peak deltas are -118, +271, and -3,422 bytes. These later, unpaired measurements strengthen final-source equivalence rather than proving a stable timing advantage.

A suitable final release statement is: “Reuse accuracy already computed for the same read-only turn snapshot, preserving exact perception arithmetic and RNG behavior. The final local three-pair diagnostic reduced the frozen-world perception calculation median by about 22%; reliable whole-run speed and memory gains were not established.” The 35% figure describes the retained initial diagnostic only. Do not call either result a whole-snapshot or simulation improvement.

## Source provenance and reproducibility

- Independently checked every module hash in `before-complete/report.json` against `git show edf7299:<path>`; all match the public baseline. The initial candidate report changes only `src/chronicler/main.py` and `src/chronicler/intelligence.py`. Both reports have the same HEAD because the implementation is an uncommitted working-tree diff; source hashes, rather than the shared revision string, identify the candidate.
- Final verified SHA-256: `main.py` = `9974aac579cc6d463e07468e835854228c8e19df75211e7ea119835e56443dce`; `intelligence.py` = `98fd8ff07f83c8fceab334d26ed96d7e895acd5a2958fb12848851c70d0546d2`. Both match `after-final/report.json` and `paired-final.json`. Current headless harness = `ed7a9739e0f89877af6735be26ae2abe9f435133fb9c7ad7a070fd1853290140`; paired harness = `90324c5d9166f8efab65b0559d63022ac19a2b8be34ce9f17a0d939b54ac7678`, matching the final paired report.
- The headless reports record identical Python 3.13.5, Linux platform, and dependency manifests; fixed seeds/workloads; repetitions; module hashes; raw wall/CPU samples; profiles; tracemalloc peaks; and equivalence hashes. Reports refuse overwrite. Native ecology/politics runtime probes enforce the pure-Python lane. Imports, profiles, tracing, hashing, and tracemalloc are outside wall-time measurements.
- The initial paired report records workload, samples, alternating-side ordering in its harness, result hashes for perception/kernel, and medians. It does **not** record roots, revisions, source hashes, harness hashes, interpreter/dependency manifests, actual generation time, or environment variables. It cannot by itself prove which source snapshot produced the result. Retain a source/environment manifest alongside it, and freeze the source trees during measurement. Avoid attaching its result to a later source revision without qualification.
- This provenance limitation applies to the retained initial `paired-boundaries.json`. The final `paired-final.json` resolves revision/module-hash/paired-script-hash/interpreter/dependency provenance, independently checked as above. Absolute source roots, imported headless harness hash, measurement timestamp, and environment-variable values remain absent. These are nonblocking reproduction details, and the final transfer manifest can preserve both scripts and fixtures.
- Headless source hashes are captured before execution and cover all current top-level package modules; there are no nested Python modules in the present package. Scripts and regression fixture hashes are not captured. A release evidence manifest should identify both harness files and the exact diff/fixture set. CPU allocation, filesystem class, concurrent workload status, and `PYTHONHASHSEED` are not captured; these are reproducibility limits, especially for subsecond comparisons.
- The fixed bundle timestamp is deliberate, affects only byte-equivalence metadata, and is applied identically. `generated_at` in the report is a description of that fixed value, not a measurement timestamp.
- Tier 1 suggested five repeats, alternate ordering, and a larger wide workload. The actual initial design uses three unpaired repeats and a bounded six-civ/twelve-region wide case. This is acceptable as disclosed diagnostic evidence, but should not be represented as the stronger originally proposed study.

Reproduce from frozen trees using one interpreter and fresh report paths:

```sh
.venv/bin/python scripts/benchmark_headless.py --source-root /workspace/Chronicler --report-dir /tmp/chronicler-before-review --repetitions 3
.venv/bin/python scripts/benchmark_headless.py --source-root /workspace/Chronicler-perf --report-dir /tmp/chronicler-after-review --reference /tmp/chronicler-before-review/report.json --repetitions 3
.venv/bin/python scripts/benchmark_perception.py --baseline-root /workspace/Chronicler --candidate-root /workspace/Chronicler-perf --output /tmp/chronicler-paired-review.json --pairs 3
```

These are reproduction instructions, not workloads executed by this reviewer. Confirm the baseline checkout is exactly the public commit and the candidate hashes match the reviewed release before using them.

## Exactness and duplicate-name fallback

The baseline public wrapper continues to recompute live accuracy. The helper extracts the original noise body without changing floating-point arithmetic, clipping, seed derivation, Gaussian draws, or bounds. The only production reuse is inside the same turn's snapshot; no cache crosses a turn, callback, or mutation phase. Tier 2 independently audited the arithmetic body and completed 4,392 exact helper comparisons and 97 focused tests.

Civilization names are used as pair-cache keys and dictionary output keys. Externally supplied duplicate names can collide even when actual objects have different accuracy inputs. The fallback detects uniqueness each turn and, when names collide, computes accuracy separately inside every selected stat read. The existing name-keyed filter, observer/target/stat order, dictionary overwrites, and cached pair-accuracy output remain intact. This reproduces the baseline's evaluation of even entries later overwritten in dictionaries, preserving primitive RNG construction/draw order. Skipping those discarded reads would be a regression despite unchanged final dictionaries. No further source fix is indicated by inspection; require a golden baseline fixture with colliding objects and unequal accuracies to certify it.

The final `duplicates_edf7299.json` and regression test cover that case: two `Twin` observers have differing faction/grudge accuracy inputs, one exact and one noisy; two production snapshots run with simulation stubbed to preserve those inputs. The frozen baseline expects six RNG instances/seeds and twelve float draws. The test matches both complete snapshot/event/narrative hashes and the ordered primitive trace. World generation occurs before this duplicate-case trace, so this fixture certifies snapshot behavior rather than simulation generation; the three standard golden traces cover generation separately. The fixture metadata identifies the public baseline, and the parent reports it was captured independently from that frozen source.

Initial headless evidence matches complete terminal state, chronicle, bundle, and all memory artifact bytes; all 120 turn snapshot/narrative/event hashes; and ordered `Random.seed`, `random`, and `getrandbits` trace contents/counts. Float primitives use exact hexadecimal representations. The changed path creates explicit `Random` instances; the trace does not independently intercept module-level bound random aliases, but no such changed-path draw is present.

`compare(...)["passed"]` means environment/output/RNG equivalence, with no speed threshold. It is not a performance acceptance predicate. The harness returns but does not serialize or directly compare `RunResult` aggregate fields, despite Tier 1's proposed coverage. Those fields are derived from unchanged exact world/memory data and remain unchanged by this diff; direct `asdict(result)` comparison excluding only `output_dir` would strengthen future evidence. This is a coverage qualification, not an identified behavioral blocker.

## Public transfer scope and separation

Transfer the reviewed `main.py`/`intelligence.py` diff, both bounded harnesses, and the frozen-public-baseline regression tests/fixtures. Publish only the measured, qualified claim above and provenance tied to the final source hashes. `output/` is ignored by the repository, so its reports are local evidence unless deliberately attached or summarized in the public review; committing implementation files does not automatically publish this review or the measurements.

The current public worktree is based on `edf7299`; the reviewed implementation diff contains only the two intended production modules. Existing public fixture metadata identifies `edf7299`. Private science revision `b665e198`, branch-only science evidence/features, Drive exports, native build artifacts, and unrelated primary-worktree edits are outside the transfer. No push, merge, upload, or paid-service action is authorized or performed by this review. Public/private separation is supported by the inspected diff and public baseline hashes; it should be rechecked against the final staged file list before release.

## Remaining items

1. Preserve final source/script/fixture provenance and this qualified evidence with the public review; local `output/` artifacts are ignored by Git.
2. Keep reliable end-to-end, memory, native, hybrid, live, resume, injection, and paid-narration benefits unclaimed because they are unestablished here.
3. Recheck the exact staged transfer file list for public-only scope before release.

Final validation and source attribution passed. No additional semantic blocker remains for the narrow public transfer.
