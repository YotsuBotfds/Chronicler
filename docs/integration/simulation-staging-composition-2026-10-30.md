# Simulation staging composition — source only, 2026-10-30

This private staging branch combines five independently developed changes from
qualified701. It is a new untested source. No push, CI, build, test, native,
World, checkpoint, benchmark, acquisition or dispatch occurred in assembly.
The five ordinary merge commits preserve each reviewed donor as a second
parent; a final commit resolves documentation and adds only the CI coverage
hardening described below. No main ref or original source/evidence changes.

| Component | Exact donor | Preserved behavior/scope |
| --- | --- | --- |
| Household wealth |5122fad852535f1f70a281c5b0fbfef06dfa8f69|Intentional native ratio floor correction; six Rust tests.|
| Settlement cell reuse |ca8a0a51ab1630470db29bba1616f80001bc17ab|Exact product/test optimization; all standalone kernel regressions remain documented.|
| Trade-route membership |b11f25380bb703180813a1645a53ac72e50d8618|Exact guarded builtin fast path and full scalar fallback; standalone fallback regressions remain documented.|
| Kin diagnostics |35aa2e308cbedd8e4243b4ce318761304bde07cb|Historical-compatible pure reader99 and default-disabled fake acquisition driver30; no actual capture.|
| Workflow analyzer |9eae69398c67e9b6e504704cd877021166c58fe1|Explicit fixed-DAG assumption, synthetic33 and retained metadata demonstration; no scheduling-speed guarantee.|

The independent donor source diffs overlap only at CONTINUATION.md. The final
continuation describes the combined state and retains the common701 body once;
all original donor continuation bodies remain untouched in their ancestry.
Every other donor product/test/note blob is preserved exactly. Historical Kin
wealth factors above1 remain readable alongside the intentional new native
floor; the source-constant witnesses concern roots/temperature, not a claim
that historical frames use the new wealth formula.

## Closed CI hardening

Exact35aa selected its capture-driver cases but omitted
scripts/capture_kin_root_exposure.py from the offline receipt's source map.
That file is outside the automatically pinned product/testing folders. This
staging runner appends its name to the existing helper-pin tuple; it does not
change the driver or tests. It also appends scripts/ci_critical_path.py and a
new ci-critical-path-contracts chunk selecting the unchanged
 tests/ci_critical_path_contracts.py33 cases. This gives existing pure tooling
standard offline coverage without creating a new test framework. The original
39 chunks, order, selectors, guard,110-second cap, exclusions, deselections,
environment and stop-on-first-failure behavior remain exact. Kin remains the
40th chunk with99+30 cases; analyzer is41st. A closed AST projection removing
only the new chunk and two helper names equals the exact35aa runner.

## Prospective selection counts

All numbers below derive from existing qualified701 counts plus exact source
membership. They are expectations for this new source, not observed results.

| Lane | Expected combined selection |
| --- | --- |
| Native Python |9012 passed,6 skipped,623 successful subreports;9018 parents/27054 phases. Intelligence owner0 adds12; settlements owner1 adds39.|
| No-Rust |8679 passed,325 skipped,623 subreports;9004 raw parent tuples.|
| Offline |5133 passed,65 skipped,97 subreports;41 chunks/234 selector strings/344 source pins.|
| Rust |1160 passed,2 ignored;619 library passes/37 targets.|
| Viewer |743 tests/69 files, plus unchanged lint/build requirements.|
| Wrapper preflights |2 native-environment pure cases and2 no-Rust cases, separately.|

Offline adds12 intelligence cases in the existing core chunk,129 Kin cases
and33 analyzer cases. Settlement's39 additions are not selected by CHUNKS.
No new default test modules or native owner registrations are introduced:
305 owners,6 skips and623 subreports remain. The new diagnostics/contracts
are explicitly nondefault files. All retained native parent-phase/XML/no-Rust
raw orders must remain exact old subsequences; only97 care subreport displays
carry cross-run raw-value equality authority. No execution order is sorted to
claim equality, and no skipped or successful subreports become parent counts.

## Held science and storage

Product sources, thresholds, seeds, original horizons and ablation windows are
unchanged except5122's deliberate wealth correction. The isolated701/native09ec
before and5122/nativea840 after families stay exact and are not replaced by this
combined source. The staging native tree is5122's exacta840. No trajectory/RNG,
checkpoint identity, performance, whole-turn scaling, installed API, actual
Kin frame,102-tick acquisition or new scientific qualification follows.
Existing scientific controller/resource proposals and hostedC are excluded;
the entire workflows/dependencies/viewer remain exact701.

The staging Git shares the existing frozen complete5122 object authority and
owns only missing donor-delta loose objects plus its new merges. There is no
new full worktree/export or copied pack. A complete virtual source manifest
resolves unchanged bytes to the existing readonly701 source and changed paths
to the new readonly overlay. Both dependencies are explicit in the handoff;
independent source review and first standardCI follow separately.
