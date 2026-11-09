# Historical integration handoff — 2026-11-03

> PR #69 merged on 2026-11-04 at `cc4f70e2`. Start new work from fetched
> `main` and the [recovery/archive index](../RECOVERY.md). Machine paths and
> runnable-session commands below are historical, not portable setup instructions;
> use [development setup](../DEVELOPMENT.md) on a fresh machine. Archive manifests
> determine which evidence is recoverable; a local path alone does not.

This handoff's work used `integration/crisis-recovery-20261103`, isolated from the
preserved development branch and original checkout. Its records start with the
[durable progress log](progress-20261103.md),
[branch integration ledger](integration-ledger-20261103.md),
[active crisis roadmap](crisis-recovery-roadmap.md) and
[frozen held results](crisis-held-results-2026-11-03.md).
The historical exploration release below is evidence for its named commits,
not an active unfinished queue or final qualification of this integration.

---

# Development lead — exploration release qualification

The 36 requested items have bounded outcomes, not a blanket completion or
scientific-qualification claim. The matrix distinguishes newly implemented work,
existing behavior checked/reused, partial coverage, and deferred work. Source
links identify the implementation; evidence links point to external receipts for
particular runs, which are not substitutes for tests on later commits.

Historical runnable code `38116fc2` passed all nine [CI jobs](https://github.com/YotsuBotfds/Chronicler/actions/runs/41401640607).
Search correction `71590379` and IndexedDB bookmark correction `ce2b4e96` are
later changes and are not covered by that CI run. The corrected combined viewer passes **1,112 tests / 101 files**, lint and
production build. Actual rendered Chromium tabs verified concurrent saves,
same-bookmark conflicts, legacy migration, reload and storage failures; see the
[targeted closeout receipt](closeout-correction-2026-11-02.md).
Fresh [CI at corrected code `13871eb3`](https://github.com/YotsuBotfds/Chronicler/actions/runs/41424054835)
was dispatched for all nine jobs; its final status is preserved in the private
release manifest. The closing change is documentation only, with unchanged
runtime/test/build inputs. Economic policies remain optional and off by default; cloud environment
publication remains deferred.

## Backlog outcome

Primary outcomes: **18 newly implemented/tested, seven existing checked/reused,
11 partially covered**. No item is wholly unaddressed; unrun/deferred subparts
and their reasons are explicit below. A partial row is not a completion claim.

Evidence links below are local to this working environment. `Implemented` means
new or corrected code was exercised in the cited bounded checks; `reused` means
existing behavior was inspected and/or tested as stated; `partial` names the
uncovered boundary. Audits are source inspection, not executed simulations.

| # | Classification and bounded outcome | Source | Executed evidence or audit |
| --- | --- | --- | --- |
| A1 | **Newly implemented and tested**: population overlay; unknown is distinct from zero and missing control. Existing thematic overlays reused. | [Map layers](../../viewer/src/lib/mapLayers.ts) | [Focused checks](/workspace/shared/chronicler-multiwave-evidence/map-territory/focused-tests.log) |
| A2 | **Newly implemented and tested**: synchronized selection and retained metric/window/turn. | [App shell](../../viewer/src/components/phase75/AppShell.tsx) | [Browser workflows](/workspace/shared/chronicler-multiwave-evidence/browser/static-workflows-result.json) |
| A3 | **Newly implemented and tested**: bounded ownership changes; ambiguous identity and renames stay unknown. | [Region history](../../viewer/src/lib/regionHistory.ts) | [Map checks](/workspace/shared/chronicler-multiwave-evidence/map-territory/focused-tests.log) |
| A4 | **Newly implemented and tested**: dated search and later corrected actor history/rewind handling; no future observations. | [Search](../../viewer/src/lib/historicalSearch.ts) | [Historical tests](/workspace/shared/chronicler-multiwave-evidence/historical-search/focused-tests.log); [constructed browser result](/workspace/shared/chronicler-closeout-correction/search/browser-result.json) |
| A5 | **Newly implemented and tested**: five-snapshot disruption/recovery windows and source reports; descriptive, not causal. | [Region history](../../viewer/src/lib/regionHistory.ts) | [Checks](/workspace/shared/chronicler-multiwave-evidence/wave-ab-corrected-focus-final.log) |
| A6 | **Newly implemented and tested**: live-edge lock and return; existing live controls reused. | [Live controls](../../viewer/src/components/LiveInspectionControls.tsx) | [Browser timeline](/workspace/shared/chronicler-multiwave-evidence/browser/live-timeline-result.json) |
| B7 | **Newly implemented and tested**: bounded civilization lifecycle; successor/restoration uncertainty retained. | [Civilization history](../../viewer/src/lib/civilizationHistory.ts) | [Focused tests](/workspace/shared/chronicler-multiwave-evidence/civilization-history/focused-tests.log) |
| B8 | **Partially covered**: city-first institution histories, existing Learning reused; school rewind leak fixed. Full independent institution histories are not claimed. | [Institution history](../../viewer/src/lib/institutionHistory.ts) | [Checks](/workspace/shared/chronicler-multiwave-evidence/institution-history/check-receipt.json) |
| B9 | **Partially covered**: existing granary/transaction views and corrected release caption; actual food consumption is unrecorded. | [Food](../../viewer/src/lib/food.ts) | [Food/debt checks](/workspace/shared/chronicler-multiwave-evidence/debt-food/focused-tests.log) |
| B10 | **Newly implemented and tested**: fiscal evidence; foreign borrowing is a subset and lender allocations remain unknown. | [Debt evidence](../../viewer/src/lib/debtEvidence.ts) | [Food/debt checks](/workspace/shared/chronicler-multiwave-evidence/debt-food/focused-tests.log) |
| B11 | **Newly implemented and tested**: recorded migration pairs; net flow is separate from population change. | [Migration](../../viewer/src/lib/migrationEvidence.ts) | [Focused tests](/workspace/shared/chronicler-multiwave-evidence/migration/final-focused-tests.log) |
| B12 | **Newly implemented and tested**: deterministic values, clocks, source references and coverage; nearby reports are not causal proof. | [Investigation](../../viewer/src/lib/investigation.ts) | [Focused integration](/workspace/shared/chronicler-multiwave-evidence/root-focused-final.log) |
| C13 | **Existing functionality checked and reused**: stability panel reused for two supported previews and common point. | [What-if panel](../../viewer/src/components/WhatIfPanel.tsx) | [Control tests](/workspace/shared/chronicler-multiwave-evidence/what-if-viewer-recipes/control-tests.log) |
| C14 | **Newly implemented and tested**: literal global granary priority 0/1 for already-enabled hybrid cases, with provenance and default preservation. | [What-if](../../viewer/src/lib/whatIf.ts) | [Native/process checks](/workspace/shared/chronicler-multiwave-evidence/what-if-policy/process-final-77f14fcd.log); [browser pair](/workspace/shared/chronicler-multiwave-evidence/browser/policy-recipe-result.json) |
| C15 | **Newly implemented and tested**: single-measure entity comparison; identity limits remain explicit. | [Entity comparison](../../viewer/src/lib/entityRunComparison.ts) | [Browser comparison](/workspace/shared/chronicler-multiwave-evidence/browser/entity-comparison-result.json) |
| C16 | **Existing functionality checked and reused**: declared starts 8/12 through common turn 20 for seeds 7/42/91; windows and initial states differ. | [Session comparison](../../src/chronicler_lab/session_comparison.py) | [Declaration](/workspace/shared/chronicler-multiwave-evidence/policy-evaluation/declaration.json); [run](/workspace/shared/chronicler-multiwave-evidence/policy-evaluation/run-77f14fcd.log) |
| C17 | **Partially covered**: six declared native pairs were neutral; constructed benefits/harms retained. No policy promotion or general balance claim. | [Session comparison](../../src/chronicler_lab/session_comparison.py) | [Evaluation](/workspace/shared/chronicler-multiwave-evidence/policy-evaluation/run-77f14fcd.log) |
| C18 | **Newly implemented and tested**: strict byte-bound saved plans and explicit new-case adoption; import sends no command. | [What-if](../../viewer/src/lib/whatIf.ts) | [Recipe checks](/workspace/shared/chronicler-multiwave-evidence/what-if-viewer-recipes/final-focused-tests.log); [browser](/workspace/shared/chronicler-multiwave-evidence/browser/new-case-browser-result.json) |
| D19 | **Partially covered**: public route/supplier/keeper contracts exercised; forced private native transport disruption is **source audit only**, deferred pending an actual native disruption test. | [Transport](../../src/chronicler/transport.py) | [Public contract tests](../../tests/test_public_grain_shipments.py) in [historical CI](/workspace/shared/chronicler-multiwave-evidence/CI-38116fc2-success.json); [private read-only audit](/workspace/shared/chronicler-multiwave-evidence/disruption-scarcity-audit/AUDIT.md) |
| D20 | **Newly implemented and tested**: optional local full-meal release 0/1; immediate relief and later shortage tradeoff remain. | [Grain reserves](../../src/chronicler/grain_reserves.py) | [Focused and native checks](/workspace/shared/chronicler-multiwave-evidence/granary-release-policy/receipt.json) |
| D21 | **Existing functionality checked and reused**: delayed forecast mechanics checked with four declared pairs and no-supply control; not a general forecast qualification. | [Forecasts](../../src/chronicler/harvest_forecasts.py) | [Executed cases](/workspace/shared/chronicler-multiwave-evidence/forecast-audit/fixed-cases-final.log) |
| D22 | **Existing functionality checked and reused**: native care exercised: immediate production cost and recovery on a matched horizon. | [Health care](../../src/chronicler/health_care.py) | [Care evidence](/workspace/shared/chronicler-multiwave-evidence/care-labor/final-case-77f14fcd/receipt.json) |
| D23 | **Partially covered**: learning loss and new-incarnation recovery exercised; school, faith and city identities differ. No new mechanical defect demonstrated. Learning loss/recovery is exercised; generalized city fall/recovery and all institution types are not established. | [Institutions](../../src/chronicler/institutions.py) | [Pressure checks](/workspace/shared/chronicler-multiwave-evidence/institution-pressure/current64f-checks.log) |
| D24 | **Partially covered**: two constructed 64-turn pressure/control pairs; conquest was unapplied and no isolated welfare claim follows. | [Example generator](../../scripts/institution_pressure_example.py) | [Declared plan](/workspace/shared/chronicler-multiwave-evidence/institution-pressure/DECLARED_PLAN.json); [checks](/workspace/shared/chronicler-multiwave-evidence/institution-pressure/current64f-checks.log) |
| E25 | **Partially covered**: one 160-turn native trajectory and exact 80→160 continuation, not a broad multi-seed gate. | [Checkpoints](../../src/chronicler/live_checkpoints.py) | [Long-run receipt](/workspace/shared/chronicler-multiwave-evidence/longrun-qualification/receipt.json) |
| E26 | **Existing functionality checked and reused**: Targeted lifecycle interactions include constructed identity edges and actual-native cases; natural extremes not reached in E25. | [Sessions](../../src/chronicler_lab/experiment_sessions.py) | [Lifecycle tests](/workspace/shared/chronicler-multiwave-evidence/longrun-qualification/lifecycle-tests.log) |
| E27 | **Partially covered**: Output/cancellation checks and actual browser Cancel/retry/duplicate Run/new-case handling exercised. Selected cancellation boundaries were checked; arbitrary interruption faults were not. | [Session operations](../../src/chronicler_lab/session_operations.py) | [Edge checks](/workspace/shared/chronicler-multiwave-evidence/longrun-qualification/what-if-edges.log); [browser](/workspace/shared/chronicler-multiwave-evidence/browser/new-case-browser-result.json) |
| E28 | **Partially covered**: instrumented RSS, history, retention and export measured; allocator/observer effects prevent a leak-free bound. | [History index](../../src/chronicler/history_index.py) | [Footprint](/workspace/shared/chronicler-multiwave-evidence/longrun-qualification/history-footprint.json) |
| E29 | **Newly implemented and tested**: chart memo improvement on measured endpoint frames; no general performance claim. | [Completed run comparison](../../viewer/src/components/CompletedRunCompare.tsx) | [Frame receipt](/workspace/shared/chronicler-multiwave-evidence/frame-performance/receipt.json) |
| E30 | **Existing functionality checked and reused**: exact points/gaps/extrema/tables retained; aggregation was unnecessary for measured improvement. | [History comparison](../../viewer/src/lib/historyComparison.ts) | [DOM equivalence](/workspace/shared/chronicler-multiwave-evidence/frame-performance/equivalence.json) |
| F31 | **Newly implemented and tested**: file-bound bookmarks now use atomic IndexedDB transactions, explicit stale-edit conflicts and v1 migration; rendered two-tab and storage-error checks passed. | [Bookmarks](../../viewer/src/lib/investigationBookmarks.ts) | [Rendered two-tab result](/workspace/shared/chronicler-closeout-correction/bookmarks/rendered-two-tabs-result.json); [migration](/workspace/shared/chronicler-closeout-correction/bookmarks/migration-idb-output.json) |
| F32 | **Partially covered**: Keyboard/focus/reduced-motion and error flows checked; physical-device and screen-reader certification deferred. | [App shell](../../viewer/src/components/phase75/AppShell.tsx) | [Browser QA](/workspace/shared/chronicler-multiwave-evidence/browser/QA_SUMMARY.md) |
| F33 | **Existing functionality checked and reused**: 390px browser controls and overflow checked; physical-device certification deferred. | [Investigation controls](../../viewer/src/components/InvestigationBookmarks.tsx) | [Phone measurements](/workspace/shared/chronicler-multiwave-evidence/browser/phone-visual-measurements.json) |
| F34 | **Newly implemented and tested**: bounded JSON/Markdown packet; missing values null, private notes and raw metadata excluded. | [Packet](../../viewer/src/lib/investigationPacket.ts) | [Browser download](/workspace/shared/chronicler-multiwave-evidence/browser/actual-investigation-download.json) |
| F35 | **Partially covered**: Extended opt-in generator with four constructed institution cases; existing generator reused. Recovery and older mixed adverse outcomes are illustrated, not general policy benefit/backfire balance. | [Generator](../../scripts/institution_pressure_example.py) | [Reproduction checks](/workspace/shared/chronicler-multiwave-evidence/institution-pressure/GENERATOR_REPRODUCTION_CHECKS.json) |
| F36 | **Newly implemented and tested**: Bounded end-to-end native and viewer journey exercised through bookmark/export; not an unrestricted production qualification. | [Example script](../../scripts/archive/world-laboratory-example.sh) | [Journey result](/workspace/shared/chronicler-multiwave-evidence/browser/final-journey-result.json) |

## Deferred or blocked boundaries

These boundaries are deliberately separate from the delivered exploratory workflow:

- **Private native transport disruption:** inspection identified the gates, but no forced private-native disruption cohort was executed. Public cargo tests do not qualify it.
- **Food consumption:** no authoritative consumed-food observation is recorded, so the viewer cannot reconstruct an actual consumption ledger without a separately justified export change.
- **Institution coverage:** histories remain city-first; learning loss/recovery is checked, not a generalized school/faith/guild lifecycle contract.
- **Scientific promotion:** a 200-seed gate and general balance qualification were not run; optional policies remain off by default.
- **Performance/accessibility:** instrumented memory and selected browser interactions do not establish an uninstrumented leak-free bound, whole-viewer speedup, physical-device coverage or full assistive-technology certification.
- **Reusable environment:** publication and fresh-task restoration remain deferred by request; current-session execution is not proof of reproducible cloud onboarding.

This release establishes a bounded, evidence-linked world-exploration and what-if workflow. It does not establish that every original aspiration is fully implemented or qualified, and these recorded limits are not a silently restarted backlog.

## Runnable session

```bash
cd /workspace/Chronicler-kimi
source /workspace/shared/chronicler-onboarding/runtime-6da9acae6bda6d7a.env
export PYTHONPATH="$PWD/src"
```

Python3.13.5, Node20.19.0, Rust1.99.1, Chromium154. Native ABI
`cpython-313-x86_64-linux-gnu`, real Agent/Ecology/PoliticsSimulator extension at
`$CHRONICLER_NATIVE_ENV/lib/python3.13/site-packages/chronicler_agents/`.
Rust tree`edb263686adb7ea5e23864146a5f7d0c5a163da4` matches recorded build32ac5879;
actual `.so` SHA256`f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
This is explicit unchanged-input reuse, not a fresh local native build. No native
extension was replaced under tests. Separate native-absent lane remains intact.
Current Python package digest`64f0c573f16800434e2ca572ddf95efc56ac567b088c7c876c8f56b89a9ddba0`.

Fresh exact example: `/workspace/shared/chronicler-exploration-example-59d1de84`.
Original14 artifacts/checkpoints remain byte-identical after browser experiments.
The actual live parent quit at16 and exited0; original24-turn completed file is
intact. The `live` destination is already used; generate a fresh external folder
for another live demo. [Copyable walkthrough](exploring-world-laboratory.md),
[gallery](exploring-example-worlds.md), [controls/recipes](live-what-if.md),
[local release policy](grain-reserves.md). Do not run the environment installer.

```bash
cd /workspace/Chronicler-kimi/viewer
npm run build
npm run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

Use a fresh output directory with `scripts/archive/world-laboratory-example.sh generate`
and `live`, passing `$CHRONICLER_NATIVE_ENV/bin/python`. Existing older bundles
remain viewable; older-source/native checkpoints refuse exact loading. Never use
a mismatch override or silently reuse a wheel from changed Rust/ABI inputs.

## Actual checks and receipts

Historical CI at `38116fc2`: **1,107 viewer tests / 101 files**, lint and production build;
**9,510 native tests / six canonical skips / 623 subtests**; **9,133 native-absent
tests / 369 skips / 623 subtests**; **1,178 Rust tests / two ignored**; all 46
bounded offline chunks and then-current native wheel production/transfer gates
pass. Python CI used 3.13.17; the working-session runtime below remains 3.13.5.
Local combined viewer1,102 preceded the last five terminal-connection regressions.
Learning62 focused +actual failing/fixed browser boundary; recipes20 focused +
real strict same-pause roundtrip and explicit new-case workflow; paused inspection
14 focused +actual draft/selection/turn preservation. Initial failures and
rejected candidates remain in external evidence, never replaced by final passes.

C14 backend101 guarded pure,58 lifecycle,10 actual native/process checks passed
at77f14fcd. Current Python64f adds only the separately tested optional D20 layer:
233 focused/guarded,2 actual native mid-transit checkpoint cases and4 parent/
current default pairs comparing114 artifacts/native/RNG. Existing frozen witness
pins were retained through an exact, fail-closed inverse layer. Native ownership
registration311modules passes; existing6 native skips/623subtest seals unchanged.
Then-current-source long-run/lifecycle/output checks provide the combined proof above.

The prior source5162 all9 CI result is historical unchanged-source evidence only;
first combined CI at942da692 passed viewer/Rust/new-wheel but exposed two strict
native tests mistakenly included in native-absent lanes. They are moved intact
into the existing native-checkpoint module; the corrected guarded chunk passes
95/2 pre-existing skips, and both real native cases pass2/0 skips. CI also
identified the explicit module-registration test's old310 count; its new module
is now listed explicitly,311 total, with the original300-owner digest, six skips
and623subtest seals unchanged. All210 metadata tests pass under the guard.
Initial native/no-native/metadata failures are retained. Rust/package/locks/UI are unchanged by this lane-only correction.
All9 corrected CI jobs passed atf021f204, run41399429636 (Python3.13.17):
9133 no-Rust tests,623subtests; Rust1178/2ignored; viewer1102. Final native
shards/aggregate succeeded with6canonical skips.

A final zero-turn resume/browser check then found the terminal-close edge:
the server exits0 without a completed message and no new output, but the client
kept reconnecting/paused. A viewer-only fix tracks sent Quit and received completion
per socket, stops terminal retries, preserves history and explicitly leaves files/
unreceived pair results unconfirmed. Ordinary reconnect and new sessions remain
covered. Four-file integration44 plus the final hook32 tests pass; lint/build
and the actual native16→Quit/no-new-turn browser pass, one socket/no retries.
Selected opaque control contrast11.17–12.70 and reduced-motion0s checked; no
full contrast/screen-reader certification. All nine final CI jobs passed on
`38116fc218902993978c2c3c695a776ae73e70f8`, run `41401640607`; final receipts/logs
are retained as `CI-38116fc2-success.json` and `ci-final-*.log`. Python64f/Rust/
locks are unchanged by this viewer-only correction.

All new receipts/scripts/screenshots/data are under
`/workspace/shared/chronicler-multiwave-evidence`, with subdirectories
`browser`, `frame-performance`, `longrun-qualification`, `granary-release-policy`,
`forecast-audit`, `care-labor`, `policy-evaluation/run-77f14fcd`,
`institution-pressure`, `institution-gallery-current64f`, `what-if-viewer-recipes`.
The complete user backlog is retained there as`authorized-backlog.txt`.

## Limits and backup

One160-turn trajectory is bounded qualification, not general balance/scientific
promotion. Optional systems all ran (244injuries/238recoveries/19.4care work,
11schools founded/5fallen,311warnings issued/310delivered,18cities founded,
19,224receipts/0dropped,129.02grain released). Natural identity-capacity/extinction
extremes were not reached; focused constructed tests cover those interactions.

Memory measurements include observer serialization/allocator effects. A raw
private-cache pickle comparison failed while semantic memory/history/native/RNG
and exported bytes matched; negative retained. No uninstrumented301MiB peak or
leak-free bound is claimed. Private forced-native transport disruption, broad
scientific gates, physical-device/screen-reader certification, and fresh cloud
configuration publication/restoration are unrun. These are explicit limits,
not another automatic development queue.

Investigation packets bind raw-file SHA; absent bundle source hashes remain
unknown, so retain generator manifests alongside exports. Recipes require the
referenced checkpoint bytes for strict identity; an explicit new case does not
prove equivalent state. Live worlds lacking raw artifact identity cannot persist
portable bookmarks. Screenshots/outputs are private external files, not Git blobs.

## Recovery and remaining verification

Corrected runtime/viewer source is `13871eb39e98771caad574af48f3780148e69b32`;
any later closing change is documentation only. Its complete source bundle was
independently downloaded from private Drive, hash-verified, restored cleanly and
all 1,849 tracked files compared. Current combined viewer and rendered two-tab
checks passed; the [targeted closeout receipt](closeout-correction-2026-11-02.md)
records their scope. Final source identity and remote objects are indexed in
`CLOSEOUT-RELEASE.json` in the private folder. Source recovery is not fresh cloud
environment provisioning.


`/workspace/shared/chronicler-multiwave-evidence/release-final` contains:

- `source-final.bundle`: the then-final development head, bundle verification and a clean
  exact trial restore in `restore-final`; Rust tree and 280 package/native/lock
  files match. `restore-final.json` records the exact commit.
- `worlds-and-evidence-final.tar.gz`: real worlds/checkpoints, private screenshots,
  declarations, neutral/adverse outcomes, failed experiments, CI and browser
  receipts. `archive-members-sha256.json` verifies every archived member.
- `SHA256.json` and `release-receipt.json`: final byte counts/hashes and scope.

The earlier `release-942da692` backup and failed CI remain preserved. An owner-only
[ChroniclerArchives Drive folder](https://drive.google.com/drive/folders/1NfGQsBD4fvqus3qXM-8-xImPSWOX0gEm)
now holds three parts of a recovery archive. Each part was independently downloaded
and the reassembled archive hash verified; see [remote evidence](/workspace/shared/chronicler-closeout-correction/backup/verified-remote-evidence.json).
All 2,068 regular members were extracted from those downloaded parts and
matched the sanitized archive manifest. Corrected source, targeted correction
evidence and `Chronicler-closeout-RESTORE.txt` have also been independently
downloaded and verified. Local originals remain intact. The redundant monolithic
archive has size/access verification only; use the independently verified parts. Reusable cloud configuration publication and a fresh
cloud task remain deferred and unverified.
