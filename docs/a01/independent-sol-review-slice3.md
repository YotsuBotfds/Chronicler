# Independent A01 slice-3 review — completed

**Verdict:** No remaining blocker or actionable defect found in the owned slice-3 source and final Python-off evidence. The implementation is suitable for the contract's staged integration order; this verdict does not approve production deployment or full A01/native acceptance.

Reviewed implementation commit: `81a4a355c0755b168d66e839e009a8f6504d71b6`, isolated branch `/workspace/Chronicler-slice3`. Exact baseline: `2ab3b4814abb665c7b3d5c255152cf5767bbf25a`, tree `46f0e042302f33865b76bd71d5b1b2c3dcda1b4f`. The final captures used a clean worktree at this implementation commit, and the reviewed implementation/runtime/test/harness bytes match its Git objects. Evidence-only summary/report files were subsequently added to the worktree for a successor commit; this review remains tied to the implementation bytes above.

Read the complete `A01-turn-artifacts-contract.md`, `IMPLEMENTATION-SLICES.md`, and `sol-independent-review.md` supplied under `/workspace/chronicler-slice3-input/contract`. Rechecked the final ten-file commit, `docs/a01/SLICE3.md`, final reports and raw captures. No repository file was edited by this reviewer. Review deliverables were written only outside the repository.

## Findings and resolved concerns

No remaining P0/P1/P2/P3 finding.

Two initial P2 evidence concerns were raised and resolved during review:

1. **Baseline provenance.** The initial comparator admitted HEAD alone. Final `scripts/a01_acceptance.py:79-84` requires the exact clean baseline and equality between current source/native bytes and independently hashed Git object bytes. This prevents modified bytes hidden by working-tree status flags from passing as the baseline. Lines 89-92 also enforce native-source equality across arms. Adversarial coverage is at `tests/test_turn_artifact_runner.py:246`.
2. **Coverage naming.** The initial `integrated_acceptance` could become true for a no-doubles Python-off capture despite having no demanded native Phase-10 rows. Final `scripts/a01_acceptance.py:120-124` distinguishes the narrower Python-off result, always leaves full integrated acceptance false, and marks native acceptance blocked. All final candidate captures explicitly use doubles, so both integrated acceptance fields are false. Coverage limitations are also stated in `docs/a01/SLICE3.md`.

The final comparator additionally revalidates artifact manifests against actual files, including extra files (`scripts/a01_acceptance.py:93-99`), compares exact trace bytes, and retains signed-zero/encoding diagnostics (`scripts/a01_acceptance.py:56-71`; test at `tests/test_turn_artifact_runner.py:296`).

## Runtime and API preservation

- `src/chronicler/main.py:340-356` captures source N before the result call and checks explicit source/completed N+1 against `world.turn`. Existing selector/narrator signatures, call arguments, seed schedule, last-turn settlement detection, and pending-injection forwarding remain unchanged.
- `src/chronicler/main.py:494-525` reads the supplied Phase-10 view at the former urban extraction point. Missing `settlement_id` remains a gate; missing `region` retains the None fallback; missing required columns/null settlement IDs still fail at the original urban access. Controller assignment reads current end-turn regions and falls back to historical affinity, retaining iteration, coercion, arithmetic, and filters.
- `src/chronicler/main.py:525,542` releases decoded column references and the view/result before `on_turn` at line 557. Structural weak-reference tests exercise consecutive turns and callback controller mutation. Main does not read the retired world snapshot/name aliases.
- `src/chronicler/checkpoint_replay.py:147-178` preserves all existing restrictions: agent mode, native bridge, economy, staged aliases, pending simulation signals, faction shifts, bootstrap state, treasury carry, completed-turn validity, and tracked focus deltas. The production change here is comments only. Runtime identity at lines 132-143 still hashes every package Python module; the new-module test proves a new `turn_artifacts.py` invalidates an older checkpoint.
- The three owned fixture interception seams now use explicit TurnResult/TurnObservation stubs and patch `chronicler.main.run_turn_result`. Existing frozen performance goldens were untouched; their historical oracle remains regression coverage rather than exact A01 replay proof. The public `simulation.run_turn -> str` source is untouched by this slice and remains the coordinator owner's responsibility.
- `scripts/a01_test_doubles.py:16-19` aborts if either real upstream interface exists. Production installs no fallback. The explicitly requested pytest plugin/capture option supplies absent interfaces only, and its identity is recorded in each candidate report.

## Independent final validation

Ran against the final implementation bytes:

```sh
PYTHONPATH=scripts:src /workspace/a01-venv/bin/python -m pytest -p a01_test_doubles -q \
  tests/test_turn_artifact_runner.py tests/test_main.py \
  tests/test_integration_snapshot_lifecycle.py tests/test_performance_equivalence.py \
  tests/test_checkpoint_replay.py
```

**223 passed in 5.15s**, including 33 focused runner tests. Earlier provisional runs passed 211 and 221 tests before the final evidence tests were added. Inspected the parent's broader final regression log `/tmp/a01-final-regression.log`: **544 passed in 5.28s** across the documented runner/main/checkpoint/performance/lifecycle/models/simulation/focus/artifact I/O/settlement/culture/religion/great-person suites. The broader 544-test run was not independently repeated.

Independently reran the final comparator for every paired capture and verified that its result equals the stored `output/a01/paired-comparison-{single,standard,wide}.json`. Also verified actual artifact manifests, exact RNG trace hashes, expected turn-log lengths, clean capture source identities, candidate source hashes against both current files and Git objects at `81a4a35`, and current driver/doubles hashes against the capture reports. The subsequently added `docs/a01/acceptance-slice3.json` metrics/checkpoint summary agrees with the authoritative reports, and report/comparison copies under `docs/a01/evidence/` are byte-identical to the authoritative paired captures.

| Existing fixture | Compared turns | Exact turn/narrator/RNG/artifact parity | Checkpoint split | Within-source status | Resumed turns |
| --- | ---: | --- | ---: | --- | ---: |
| single | 20 | PASS | 5 | PASS in both sources | 15 |
| standard | 60 | PASS | 5 | PASS in both sources | 55 |
| wide | 40 | PASS | 0 | PASS in both sources | 40 |

The 120 compared turns include complete TurnSnapshot/text/ordered events/named events/world captures, deterministic narrator inputs, exact seed/random/getrandbits primitive traces, final chronicle, bundle, state, and memory files. Only the existing fixed bundle generated-at convention is normalized. Fixture SHA256 is `ffb8a8d60e5b3902249b2e7aeb47b4b7a64694ec27d812474cdc18d984a3c535` in all six reports; each arm's initial state hash matches its counterpart.

The wide split-5 attempt was rejected by the existing completed-stockpile-bootstrap guard on both sources. Inspected `/tmp/a01-baseline-wide-final.log` and `/tmp/a01-candidate-wide-final.log`; both retain `checkpoint requires a completed stockpile bootstrap`. Final wide split 0 exercises serialization/resume at the initial boundary, **not a nonzero-turn continuation**. No guard was weakened to obtain a pass. Single and standard supply the nonzero split coverage.

Independently attempted to load `output/a01/paired-baseline-single/checkpoint.json` through the final candidate replay implementation, using the explicit absent-interface scaffolding. It rejected with `checkpoint source/Python/dependency runtime mismatch`, matching `output/a01/cross-source-rejection-final.json`.

RNG SHA256 values verified from actual trace bytes:

- single: `cd5ebb496dfeab3b75d1941f914b462982c55a9a1a4d0c52806b5c521c3f7666` — 117 seeds, 285 getrandbits, 225 random draws.
- standard: `36caae11b96babc022468cb57ad02f96c358ae3a36377a26f97ccefb233f9ce3` — 3,519 seeds, 1,110 getrandbits, 6,589 random draws.
- wide: `2118c0615d21270fccd0eca236e3b9b31f98a5ede4885acbf9b44e1340f8a2f5` — 3,866 seeds, 810 getrandbits, 7,324 random draws.

## Reviewed identities

Baseline runtime source SHA256: `c19c3b84fbb3bb592738d165417a376112fe36c2a35076cc5ae898342048ed71`.

Candidate runtime source SHA256: `0dc9d7fef5e34814cf159e7e16632aa00035ba3a3b9736798b426323ee0f0c1f`.

| Final reviewed file | SHA256 |
| --- | --- |
| src/chronicler/main.py | 65958a043703898fad0fce85bb7e243a097cc2c67e3ccd716deeac3bf6068f54 |
| src/chronicler/checkpoint_replay.py | 4ca3b3da8c56580071d12d8955a069ad888017cbcc9ed48188a00a47911a663c |
| scripts/a01_acceptance.py | 5c09167d301e761741a461c4ce561e945ae1b3d3ad69fbfb1510c2a49b72eafe |
| scripts/a01_test_doubles.py | 82ea0d23ac9bc8272d40d29992044a40f063775c267692f1cac0c8839401a1e5 |
| tests/test_turn_artifact_runner.py | 66e32b40c2fcf22be1cfa9f7ac75390eb761c5c5ba206b1c442f3abd130dbc52 |
| docs/a01/SLICE3.md | e28f7e3e1898ad21b46118d52a3395de994620cf351f5902422b889c6b190de9 |

Machine-readable independently checked evidence summary: `/tmp/a01-independent-final-evidence.json`.

## Acceptance limits and required integration follow-up

Slices 1/2 remain intentionally absent. This review covers the owned runner cutover with explicit contract doubles and exact Python-off regression captures. It does not prove real AgentRows cache semantics/lifetime, migrated coordinator snapshot stages/order, named-map copying, conquest/death plumbing, or complete callback ownership after coordinator alias removal. Parent integration must apply slices 1, 2, then 3 and remove snapshot/name publication through the coordinator owner. The prior-publication `_economy_result` gate remains required. The isolated slice cannot import/run production main without its upstream APIs and must not be deployed alone.

No reviewed compatible native binary or admitted in-process native starting fixture is available. Hybrid/shadow/demographics semantics, native get_snapshot order/stages, demanded-column decode reduction, real tuple/list peak-memory effects, and no retained-cache growth remain **BLOCKED**. The observer explicitly cannot capture native getter return batches and leaves unresolved identities/stages visible. All paired reports record zero decoded elements/native snapshot calls/live views in Python off mode; those zeros do not establish any native or real-cache result.

The reports record warmed whole-run and snapshot-consumer-span timing, current/peak tracemalloc, peak RSS, and callback/end live-view counters. Timing samples have mixed direction across the three fixtures and involve absent-interface doubles; no speedup or native-memory benefit follows. RSS is peak process RSS, and current tracemalloc bytes are retained allocations rather than total allocation volume. These are diagnostic metrics, not a correctness gate.

All final comparisons correctly report `exact_comparison_passed=true`, `integrated_python_off_acceptance=false`, `integrated_acceptance=false`, and blocked native acceptance. No full-hybrid checkpoint support, native allocation reduction, third-wave replay, scientific tuning, production activation, external write, blocked import, or unrelated Rustgame work is claimed or performed by this review.
