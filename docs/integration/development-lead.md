# Active development lead

The active branch is `dev/codex-playable-build-20261031`, continued from clean,
published `32ac587908b28167e45ff105f62ace988fbb8e12`. Main and the older additive
Kimi remote are preserved. Reusable environment editing/publication is deferred
by the user; it is not a prerequisite for work in the current running session.

## Qualified starting point

The previous remediation queue is complete. Do not restart its fixes from the
older handoffs' historical UNRUN snapshots. Exact-source CI run
[41266231344](https://github.com/YotsuBotfds/Chronicler/actions/runs/41266231344)
passed all nine jobs: 9,184 native parents with six registered skips, 8,821
no-native parents with 355 skips, 623 successful subtests in each full lane,
43 guarded offline chunks, 1,178 Rust tests with two ignores, and 745 viewer
tests plus lint/build. Subsequent full checkpoint verification on unchanged
`32ac5879` passed all 23 registered cases: 707 resume points and 17,650 file
comparisons, zero differences, with matching live views. Scientific/balance
campaigns remain unrun; these are source-scoped functional results.

The working session has complete system Python 3.13.5, Rust 1.99.1, Node
20.19.0 and Chromium. At takeover, the real native module, wheel bytes, ABI,
selected Python project and native source-input digest were verified against
the current source. Native source digest was
`33b3080877fb8deb6bf624f398cdaae871569fe717d8ef27742cea995a62c182` and native
binary SHA-256 was
`f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
Future native edits need a matching fresh build; never replace it beneath
running tests. Working-session capability is distinct from fresh cloud
configuration restoration, which has not been verified or published.

## Chosen milestones

1. **Historical event exploration — verified.** Pinning an event keeps
   the selected timeline turn. Deliberate Go actions seek using the existing
   event clock. Resolved recorded causes/consequences and known actors become
   navigable without inventing relationships or revealing future observations.
   Worker component commit `80a5eb26` is integrated as `f3be89b0`. The combined
   viewer passed 759 tests, lint and production build. Production Chromium QA
   loaded an actual native bundle and passed six navigation/data/mobile checks,
   with no console/page errors. The harness waits for responsive charts to
   finish resizing before checking mobile overflow; no layout change was needed.
2. **Unknown granary targets — verified.** A target needs demand
   observations even when stored grain is known. Incomplete aggregate targets
   must be gaps/Not observed rather than zero or a partial sum. Measured zero
   remains zero; existing bundle formats and exports stay unchanged.
3. **Actual run/save/resume path — verified.** An actual 12-turn hybrid
   simulation with granaries resumed from turn four with seven byte-identical
   artifacts; decoded bundles differed only in generation timestamp. Its bundle
   also passed the production browser checks above. At clean `2f2e59eb`, live
   browser QA passed 20/20 checks separately in hybrid/native and aggregate with
   no native package: launch, save to disk, fork hint, quit, resume with matching
   history/metrics, stale/missing-token refusal, continue to turn ten and quit.
   All four processes exited normally. No product defect was found in this path.
4. **Held simulation work — assessed, preserved.** Debt-holder fixes, arc event
   reuse, native tick indexing and region partitions are already represented;
   do not bulk-merge their old branches. The shipment negative never observed a
   pending order and therefore never reached restore assertions. Its economic
   gate values were not retained; changing the case or policy would be speculation.
   Shipment/diagnostic and merchant-tax experiments remain separate.
5. **Opt-in shortage-first granary procurement — integrated and smoke-tested.** The
   current reserve-fill ordering can spend a scarce coin refilling a fed region
   while another region is underfed. Register an existing-tuning opt-in,
   `grain_reserves.shortfall_priority`, default zero. Enabled ordering promotes
   known current shortages, retaining sourcing passes, ledger rules and ties.
   Acceptance: the same coin buys eight units; the hungry destination receives
   7.6 after transit, then can release six next turn for food sufficiency 0.6,
   versus 0.2 under current allocation. Default/off outputs and RNG must remain
   unchanged. Worker commit `af782dee` is integrated as `62866079`. On that source,
   105 focused Python/native tests passed without skips, and 101 guarded offline
   tests passed with two explicitly native tests deselected. The actual native
   60-turn `hybrid_s42` case with resource accounting, receipt capture and this
   tuning option passed 45 plain/checkpoint comparisons and 33 turn-30 resume
   comparisons, zero differences. The exact checkpoint and all three final
   worlds retain the enabled key. The unchanged compiled native inputs were
   verified against their `32ac5879` build. The allocation fixture proves the
   scarce-budget effect; the native smoke proves wiring/accounting/continuation,
   not that this procedural run encountered competing purchase destinations.
   Scientific/balance qualification remains unrun and the option stays off.
6. **Plain-language viewer guidance — verified.** Replaced visible shell
   scaffolding copy with useful selected-turn/history/selection guidance, keeping
   existing controls and data semantics. Worker `43339a0e` is integrated as
   `56688c1f`. The final combined viewer passed all 759 tests, lint, build and
   seven production Chromium checks (navigation, unknown data, mobile layout and
   the guidance), with no browser errors. No additional implementation is planned
   for this queue; held experiments and scientific promotion remain separate.

Working-session evidence is outside the repository at
`/workspace/shared/chronicler-development-evidence`: baseline identity,
`viewer-milestone1-{tests,lint,build}.log`, native walkthrough outputs and
`browser-mobile-settled/report.json` plus screenshots. Two earlier browser
harness attempts are retained: an actor locator assumed a heading and an
overflow check ran before asynchronous chart resizing finished. Neither exposed
a product defect; the final harness checks the actual actor field and settled UI.

Live reports/screenshots are in `live-{hybrid,aggregate}-2f2e59eb`; the optional
policy's actual-native identity report is
`shortfall-native-identity-62866079/identity-receipt.json`. The development branch
was pushed through `62866079`; a complete bundle containing `2f2e59eb` and both
initial worker branches was SHA-256 verified and restored cleanly. Final viewer
logs are `viewer-final-{tests,lint,build}.log`, with report/screenshots in
`browser-final-56688c1f`. Final source publication, CI and backup receipts follow
before this milestone is closed.

## Working-session commands

Run from `/workspace/Chronicler-kimi`. The existing runtime file activates tools;
it does not install, rebuild or publish configuration. Its build provenance is
`32ac5879`; native reuse above is justified by identical native inputs, not by
assuming its recorded source commit tracks later Python/viewer changes.

```bash
source /workspace/shared/chronicler-onboarding/runtime-6da9acae6bda6d7a.env
export PYTHONPATH="$PWD/src"
"$CHRONICLER_NATIVE_ENV/bin/python" -m pytest -q tests/test_grain_reserves.py tests/test_public_purchase_receipts.py tests/test_public_purchase_receipts_native.py tests/test_tuning.py
cd viewer
npm test -- --run
npm run lint
npm run build
npm run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

For actual-native identity, from the repository root run
`python scripts/checkpoint_identity.py run OUT --case hybrid_s42 --ks 30 --jobs 1 --keep --cli-arg=--grain-reserves --cli-arg=--transaction-receipts --cli-arg=--tuning --cli-arg=YAML`
with native Python, `CHRONICLER_CHECK_RESOURCES=1`, `OMP_NUM_THREADS=1` and
`OPENBLAS_NUM_THREADS=1`. The script pins hash/Rayon settings. Use fresh external
output paths. Live browser QA is `viewer/scripts/qa-live-checkpoint.mjs` with
`--python PYTHON --viewer http://127.0.0.1:4173 --out OUT --agents hybrid --chromium /usr/bin/chromium`;
set `NODE_PATH=/workspace/shared/chronicler-browser/node_modules`. Use the
no-native interpreter and `--agents off` for the distinct aggregate lane.

## Continuation rules

Keep this one concise tracker current after integration. Use isolated worker
branches with explicit ownership. Finish each milestone with focused checks,
actual UI where applicable, integration review, a commit and a verified dev push.
Preserve unfinished work through a bundle/hash/trial-restore checkpoint before
context or quota runs tight. No main merge, destructive cleanup, deployment,
new credentials, paid API/narration, automatic full startup suites or optional
default promotion. Ask only for a genuinely blocking product/permission choice.
