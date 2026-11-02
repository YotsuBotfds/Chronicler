# Interactive world laboratory — complete

Runnable branch: `dev/codex-playable-build-20261031`. Final verified code is
`5162ab051365fd483dd6106979aa0513648503d3`; the closing handoff changes documentation
only. [All nine CI jobs](https://github.com/YotsuBotfds/Chronicler/actions/runs/41376993245)
passed on that exact code. No planned development remains in this queue.

Initial refresh on 2026-11-02 found clean local/remote `c04b32ad`, with no newer
work to reconcile. The [previous queue remains complete](https://github.com/YotsuBotfds/Chronicler/blob/c04b32adef05e54c46f597d9fece9568e719c7c7/docs/integration/development-lead.md).
Remote main stays `cb9fe70c81658fb65c6f511b821447f1d7b55b54`, untouched. Economic
defaults, dependency locks and Rust inputs are unchanged. No deployment, new
credentials, paid API/narration calls or environment publication occurred.

## Delivered

1. **Authoritative regional history.** Version-1 observations export each stable
   world-region index's actual completed model population, separately labeled
   native counts and frozen Phase2 food weights/ownership. Completed snapshotT
   follows tickT−1, including subsequent migration/birth/death/political effects.
   Demographics clamp and shadow/model differences remain explicit. Absent or
   invalid observations stay unknown. Existing history, turn comparison and run
   comparison expose the data, with weighted-food coverage/denominators.
2. **Where should I look?** Selected-turn food distress, population changes,
   finance, movement, recovery and institution prompts show recorded values and
   windows, grouped per entity. Links open existing history without seeking.
   No universal score, inferred cause or future observation is used.
3. **Exact what-if pair.** A paused simulate-only live session prepares a labeled
   stability1–100 control and 1–20 additional turns, then explicitly runs unchanged
   and intervention continuations from one exact checkpoint. The original stays
   paused. Strict compatibility, private UUID output paths, duplicate safeguards,
   bounded serial children, cancel/quit cleanup and reconnect replay are covered.
   Existing completed-run comparison accepts both real arms and retains source,
   checkpoint-epoch settings, arm roles and raw hashes in JSON/Markdown exports.
4. **Measured history cost reduction.** On a real 10.8MB,32-region/200-turn saved
   world, event-key caching and reused number formatting reduced history scripting
   median22.15→16.60ms. Frame time was52.60→52.95ms; loading/comparison did not
   improve. Shared-host contention and overlapping ranges limit the result.
   Rejected memo experiments and slower measurements remain in the evidence.
   Real/legacy rendered-DOM equivalence found zero differences.
5. **Guided real example.** Fixed natural seed42, hybrid24,8regions/4civs,
   granaries+receipts, exact checkpoint8. The deliberately constructed Ashkari
   stability31→70 pair continues through16; population199→195 and treasury165→203
   illustrate a single case's tradeoffs. Original prefix and checkpoint are
   preserved. [Launch/load walkthrough](exploring-world-laboratory.md) includes
   actual observations, copyable commands, screenshot names and limitations.

Contracts: [regional population](regional-population-observations.md),
[viewer conditions](regional-laboratory-viewer-2026-11-02.md),
[exact-pair backend](live-what-if.md),
[performance measurements](../performance/viewer-history-2026-11-02.md).

## Actual checks and limits

- CI: native9427 passes/6 registered skips/623 subtests; no-Rust9057 passes/362 skips/623 subtests; viewer895/80files plus lint/build; Rust1178 passes/2 ignored; guarded offline46 chunks. Fresh native build/install and real native execution are
  distinct from the no-Rust and guarded offline lanes. Rust links and executes.
- Isolated observation proof:577 passes/61subtests/one existing mock skip;
  guarded32. Parent/current16-turn pairs in all four modes preserve world,
  decisions, RNG and native bytes after removing only the intentional observation
  export. Same-source8→16 exact resumes retain complete new history in all modes.
- Combined local focus:111 Python/native passes. Backend pure/registration,
  process/native and real browser lifecycle checks pass. Final current package
  reads the original exact8 checkpoint under the declared environment, with its
  hash unchanged. All12 exported comparison metrics match actual source files.
- Actual Chromium154 checks include condition→history without timeline movement,
  all16 regional rows against source, older unknowns, prepare/run review, duplicate
  clicks, refusal/recovery, prepared/running cancellation and reconnect. An observed
  native child was killed/joined146ms after cancel. Phone390 layouts fit; wide
  tables scroll inside their container. All owned servers/browser work stopped.
- Intentional export changes required updating frozen-witness projections, not
  the historical fixtures or expected RNG. One strict test-local v1 projection
  is shared across every frozen snapshot/artifact capture; other fields and
  malformed/future versions remain checked. All16 golden trajectories pass.
  Original failures, the cancelled follow-up and the gate that rejected two hash-seed skips are retained. Fixed-hash native fixtures now execute in bounded supervised children; the original six-skip seal is unchanged. Their execution exposed an actual output-monitor race with atomic temporary-file renames. The fix tolerates only vanished file stats during running scans, keeps strict final scans/real I/O errors and enforces unchanged log/total caps;45 guarded regressions and CI-style native5 passed. Prior failures remain preserved.
- Exact what-if requires POSIX, PYTHONHASHSEED=0, a simulate-only source and matching
  package/native/interpreter/packages/thread settings. It caps each arm at120s,
  16MiB bundle and192MiB output, with eight retained requests/session. State JSON
  forks cannot supply this exact runtime. One pair is not scientific qualification.
- No general balance/promotion, large campaign or broader scientific gate is
  claimed. Shortage-first purchasing and delayed shipments remain default-off.

## Working session, backups and continuation

```bash
cd /workspace/Chronicler-kimi
source /workspace/shared/chronicler-onboarding/runtime-6da9acae6bda6d7a.env
export PYTHONPATH="$PWD/src"
```

Session tools: Python3.13.5, Rust1.99.1, Node20.19.0, Chromium154. The session's real
native extension exposes all three simulator classes, ABI
`cpython-313-x86_64-linux-gnu`. Its `32ac5879` build inputs still match Rust tree
`edb263686adb7ea5e23864146a5f7d0c5a163da4`; binary SHA-256
`f6f78b0c63efcf5fd09e310d6901c460711e667f09e57d3e348df00ca57cab29`.
This is explicit same-input reuse. CI separately builds a current-source wheel.
A future native-source/ABI change requires an isolated matching build; never
replace a shared extension under tests. Reusable environment publication and
fresh-environment restoration remain deferred and unverified.

New evidence: `/workspace/shared/chronicler-world-lab-evidence`;
regional parity/resume evidence:
`/workspace/shared/chronicler-regional-population-evidence-20261102`.
Frozen-witness proof receipts also live in the regional performance/independent
witness directories. Final source bundle/hash/clean trial restore and evidence
archive identities are recorded in the external `FINAL.json` under the evidence
root. Trial source restoration does not qualify a fresh runtime environment.

Example: `/workspace/shared/chronicler-world-lab-example-final-20261102`.
Shareable archive: `/workspace/shared/chronicler-world-lab-5162ab05.zip`,
2,585,911bytes; SHA-256
`e7e46cfd0daa215d8858e4b60bfeeb303a8ab965210349565e10f5850ba00a26`.
All57 archived files/CRC/content hashes verify. It includes source/runtime
manifests, original/paired outputs, comparison exports and actual screenshots.
No bulky generated worlds, private runtime files or machine configuration are
committed. The root worktree is clean and the dev remote matches the closing tip.

Nothing remains to implement or approve for this queue. To explore, follow the
walkthrough; existing outputs are preserved, so use a fresh path for another live
session. Do not restart an older queue or make environment publication a prerequisite.
