# Active development lead

## Current baseline and scope

Continue on `dev/codex-playable-build-20261031`. Remote refresh on 2026-11-01
found the local and remote tip both `061594a0606b9a9dfdbd1a63de2afb7dfcc3c3db`,
with a clean worktree and no newer work to reconcile. Main remains untouched.
The prior queue is complete: [its handoff at 061594a0](https://github.com/YotsuBotfds/Chronicler/blob/061594a0606b9a9dfdbd1a63de2afb7dfcc3c3db/docs/integration/development-lead.md)
records all nine passing CI jobs at code source `f371e6fa`, browser/live checks,
optional shortfall procurement, backup verification and source boundaries.
Do not repeat that queue or its full baseline checkpoint matrix.

The user authorized this new six-item development queue. Environment publication,
main merges, public deployment, new credentials and paid narration/API calls
remain out of scope. Optional economic changes stay off by default.

## Queue

1. **Saved worlds — browser-verified.** Existing loader now retains the world,
   identity and selected turn on failure; detects checkpoint/state file types;
   rejects incomplete required/nested food, finance and granary records; supports
   legacy/new bundles and repeated/failed-then-successful loads. Details shows
   actual recorded range, seed/mode, saved enabled systems and history coverage.
2. **What changed — browser-verified.** Existing history inspector now compares
   exact civilization/region endpoints through the selected turn. Missing/birth/
   extinction rows stay unknown; territory/debt avoid double counting. Event
   context follows completed ticks (snapshot T reflects T−1), without causal
   claims. Inspect keeps target/turn; explicit View seeks. Phone 390 fits.
3. **Completed-run comparison — browser-verified.** Existing BatchCompare now
   includes completed runs, reachable from the main header. Exact-turn charts
   and summaries retain null gaps/tails, source/settings warnings and original
   hashes. JSON/Markdown sharing, failed-load retention and tab persistence pass.
4. **Held grain shipments — integrated, native-verified.** Original fixture had
   28 foreign offers floored below one coin after domestic depletion: no pending
   dispatch, not a restore/product bug. Original native negative is retained;
   finite opening seller granaries establish a genuine positive precondition.
   A separate original manifest assertion omitted a second unspecified flag.
   Existing default-off shipment overlay is composed selectively, without Rust,
   policy tuning or immutable historical-pin changes. 620 isolated focused
   passes and 164 integrated native/Python passes include accounting and exact
   mid-transit restore. Default and explicit-off match parent in 25 artifacts,
   native bytes, live views and controlled RNG. Actual shipment-browser checks
   pass 15 cases (stored versus pending, single payment, arrival/receipt clock,
   metadata, desktop and cold/resized phone). A real phone overflow was fixed
   with the existing minimum-width container; original failure is retained.
   See public-grain-shipments.md.
5. **Shortfall purchasing — evaluated, remains off.** Six preregistered matched
   constructed scenarios show immediate benefits and harms (competing hunger
   reduces total release 8→6; moving hunger loses relief elsewhere). The fixed
   natural seed42/60 native pair is neutral: purchases occur but order changes
   none. Accounting, deterministic defaults and both exact continuations pass.
   No policy parameter, seed selection or default changed. Full scientific
   promotion is not justified. See shortfall-priority-evaluation.md.
6. **Guided real examples — generated and browser-verified.** A small existing-CLI wrapper and
   guide define three fixed template/procedural examples, separated aggregate
   and native runtimes, always simulate-only. Output/existing-folder guards,
   shell quoting and Python syntax checks pass. Three examples at clean source
   `4ec56a41` complete 24/60/40 turns; all 12 browser walkthrough checks pass,
   including observed grain release/borrowing, real care rows, honest zero seats
   of learning and final-turn loading. A 390px 12-region care table fits. No
   manual initial-state changes or paid narration were used for these examples.
   See exploring-example-worlds.md and the generated WALKTHROUGH.md.

## Working session and evidence

Python 3.13.5, official Rust 1.99.1, Node 20.19.0 and system Chromium work here.
Reusable cloud configuration publication/restoration remains deferred and unverified.
Activate existing tools without invoking installer/startup:

```bash
source /workspace/shared/chronicler-onboarding/runtime-6da9acae6bda6d7a.env
export PYTHONPATH="$PWD/src"
```

The native extension is a real `cpython-313-x86_64-linux-gnu` module exposing all
three simulator classes. Its `32ac5879` native build inputs remain identical at
`061594a0` and through `88fdf829` (Rust tree
`edb263686adb7ea5e23864146a5f7d0c5a163da4`), binary SHA-256
`f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
This is explicit same-input reuse, not a claim of a fresh build at a later commit.
Native source changes require an isolated matching build; never replace the shared
extension while tests run. Each worker sets PYTHONPATH to its selected worktree.

New evidence is external at `/workspace/shared/chronicler-next-development-evidence`.
Combined source at root `828e3c72` plus the recorded UI working diff passed **861
viewer tests**, lint and production build, plus **164 Python/native tests without
skips**. `browser-load-history/final828` passes old/new/error/recovery/repetition,
exact metrics, all 46 civilization/nine regional event links, target retention and
mobile layout; `browser-completed-comparison/report.json` passes four cases with
actual completed 12/60-turn bundles, exports, null tails and source arithmetic.
No browser console/page errors. First real product failures and separate external
locator/float-precision harness negatives remain retained. Native input/binary
provenance is `baseline.json`; shipment and preregistered evaluation receipts have
their own directories. These are functional checks, not scientific qualification.
A complete bundle plus working patch/untracked source archive was SHA-256 checked
and restored byte-for-byte under `checkpoints/loader-history-integration`.
The example commands' shell syntax and parsed arguments match the actual CLI
runs; both repeated generator calls and recorded shell commands refuse existing
folders without changing bundle hashes. Artifacts/guide/provenance are outside
Git at `/workspace/shared/chronicler-example-worlds-20261101`.
All planned implementation and local/browser checks are complete.

## Final qualification and delivery

Runnable code source **`88fdf8295db92b3e3af68ed1fe07bcc3a2a62daf`** is pushed to
the development branch. [CI 41358475090](https://github.com/YotsuBotfds/Chronicler/actions/runs/41358475090)
passed all nine jobs on that exact source, attempt one:

- Native Python: 9,321 parent passes, six registered skips, 623 successful subtests;
  both disjoint module shards and the exact-once aggregate/barrier passed.
- No-Rust Python: 8,956 parent passes, 357 skips, 623 successful subtests.
- Rust: 1,178 passed, two ignores. Viewer: 861 tests, lint and build passed.
- All 44 bounded offline chunks passed (5,519 passed reports, 67 skipped reports;
  these report counts are not added to the full-suite parent counts).

The workflow built one current-source wheel with locked maturin/Cargo on Python
3.13.17 and validated compiled classes plus same-run transfer and aggregate
provenance. All nine job logs/status/build metadata are retained under
`ci-41358475090/summary.json`. Raw archives were not downloaded: the earlier
Azure artifact-transfer denial was respected, with no retry/bypass or new denial.
Wheel/native hashes and exact import path not printed in those logs remain
unobserved; artifact ZIP digests are not wheel hashes. The verified local build
above is a separate, matching-input runtime. CI does not verify saved cloud
configuration publication or fresh-task restoration.

`chronicler-exploration-88fdf829.bundle` contains complete history and all five
integration/worker refs, SHA-256
`de634c8f5d6b7d0f5df6432b2f4ad2e72f231a1b3d0240a5f830a2aca2ce077e`.
Bundle verification and clean exact-commit trial restoration passed. The final
closing commit changes this handoff only; final bundle/hash/restoration details
are retained externally in `FINAL-DEVELOPMENT-RECEIPT.json`.

The three viewable worlds and guides are packaged outside Git at
`/workspace/shared/chronicler-exploration-examples-20261101.zip` (385,790 bytes),
SHA-256 `bf38d47e3591c03b548ecce67c6ae441351d619db12049fda229bb1ca7bd2d9a`.
All three archived bundle hashes were verified against `examples.json`. No bulky
worlds, logs, checkpoints or runtime dependencies were committed.

Limits: regional historical population is not exported and remains unknown;
cross-run provenance absent from a bundle remains unknown; food means explicitly
cover observed regions without population weighting. The browser inspects checkpoint
headers only; exact resume still requires the matching source/native/environment.
Shipment tests use a declared constructed starting reserve, and shortage-priority
evidence includes harms and a neutral natural run. Both options remain off; no
scientific, balance, performance or default-promotion claim is made.

## Integration and continuation

Root owns integration, this tracker, turn comparison and final examples. Loader,
shipment and evaluation workers have separate branches/worktrees and file ownership.
No overlapping writers or recursive review chains. Inspect each commit, integrate
selectively, qualify combined source, commit and push the dev branch, verify remote.
Preserve unfinished source via complete bundle/SHA-256/clean trial restoration
before context or quota runs tight. Keep generated runs and private logs untracked.

Next action: none for this queue; it is complete. Environment publication and
scientific promotion remain deferred. Main stays at
`cb9fe70c81658fb65c6f511b821447f1d7b55b54`; native source and dependency locks are
unchanged from the starting point. Owned local servers, tests and simulations
have stopped; generated files stay ignored/external. The dev remote and clean
final backup are verified during closeout. No merge, deployment, new credentials
or paid narration/API calls occurred.
