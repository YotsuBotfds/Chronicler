# Development lead — exploration release qualification

Branch `dev/codex-playable-build-20261031`. The full 36-item backlog is complete:
implemented features and checked existing equivalents are recorded below.
**No planned development work remains.** Runnable code `38116fc2` passed all nine
[CI jobs](https://github.com/YotsuBotfds/Chronicler/actions/runs/41401640607).
The closing commit changes documentation only. Main stays `cb9fe70c`, optional
economic policies stay off by default, and environment publication remains deferred.
Started from clean, refreshed local/remote `977bab1a`; prior queues were not restarted.

## Backlog outcome

| # | Delivered / verified |
| --- | --- |
| A1 | Fixed-legend population and existing thematic overlays; unknown differs from zero. Exact control gaps also stay unknown. |
| A2 | Map/list/history/comparison selection synchronized; metric/window/turn retained. Conditions and explicit regional reports linked. |
| A3 | Bounded exact ownership changes, stable indices, ambiguity/renames unknown; no invented borders. |
| A4 | Dated region/civilization/city/actor search, aliases and ambiguity, no future observations. |
| A5 | Fixed five-snapshot disruption/recovery windows, explicit rule and paged underlying source reports. |
| A6 | Actual live incoming-turn lock, explicit latest-edge lock, Return to live and UI Quit verified. |
| B7 | Bounded recorded civilization lifecycle, restoration/successor uncertainty and event/history links. |
| B8 | City-first institution histories; existing Learning reused. Real school rewind leak fixed and browser-regressed. |
| B9 | Existing granary/transaction views cover food flows; corrected released-before-consumption caption. Actual consumption remains unrecorded. |
| B10 | Fiscal borrowing/service/paid-interest/principal/default/write-off evidence; foreign subset not added twice, lender allocations unknown. |
| B11 | Explicit migration origin/destination/source fields, summed duplicate pairs; net flow separate from model population change. |
| B12 | Deterministic values, clocks, source refs and coverage; nearby reports never assigned causal meaning. |
| C13 | Same existing stability panel now previews two supported controls and authoritative common point; no second workbench. |
| C14 | Literal global granary priority0/1, already-enabled hybrid only, schema2 provenance, no-op/default preservation; real native browser pair. |
| C15 | Per-region/civilization single-measure comparisons and identity limits; all8 real regional deltas checked against snapshots in browser. |
| C16 | Declared starts8/12 to common20, seeds7/42/91; differing windows/starting states explicit. |
| C17 | Six pairs/12 native children:6 neutral,0 failures, no retuning. Earlier constructed benefits/harms retained; no promotion. |
| C18 | Strict saved plan with byte-bound reference; import sends no command. Explicit new-case adoption preserves mismatch/identity honesty. |
| D19 | Public route/supplier/keeper/ownership contracts exercised; private transport source-audited. No proven new mechanics defect. |
| D20 | Optional YAML full_meal_release0/1 from local stock. Immediate relief vs later shortage harm retained; current defaults byte/physics checked. |
| D21 | Four declared forecast pairs plus no-supply: timely benefit, wrong/late cost, expiry refusal; existing delayed mechanics correctly wired. |
| D22 | Actual native care reduces immediate production, advances recovery; same-horizon continuation and observation neutrality checked. |
| D23 | Learning loss/new-incarnation recovery exercised; distinct school/faith/city identities. No demonstrated mechanical fix needed. |
| D24 | Two declared64-turn constructed pressure/control pairs; unapplied conquest retained, no seed search or isolated welfare claim. |
| E25 | Seed42 procedural32regions/8civs hybrid160; exact80→160 continuation matches64 artifacts and final native/RNG bytes. |
| E26 | 53 targeted lifecycle interactions, including identity capacity/restoration/late entries and6 actual-native cases, zero skips. |
| E27 | 91 current-source output/cancellation checks plus actual browser Cancel/retry/duplicate Run/new-case handling; owned parents exited0. |
| E28 | Instrumented RSS/history/retention/export growth measured; final bundle19,052,995B. No demonstrated accidental history duplication. |
| E29 | Actual endpoint frame legacy20058.8→25.6ms, current16068.95→26.55ms; chart memo only. History unchanged. |
| E30 | No aggregation needed for measured improvement; exact points/gaps/extrema/tables retained,257 DOM captures equivalent. |
| F31 | File-SHA-bound local entity/turn/panel/notes bookmarks; safe reload/restore and corrupt/full storage; notes excluded from sharing. |
| F32 | Named keyboard map/list/timeline, modal containment/restoration, focus jumps, reduced motion and error/refusal flows checked. |
| F33 | Actual390px selection/history/comparison/bookmark controls;44px targets, keyboard table scroll, no page overflow. |
| F34 | Bounded exact observation/event-reference JSON/Markdown packet; missing values null, no private notes/raw metadata/paths. |
| F35 | Existing generator extended opt-in with4 constructed institution cases; all7 current-source recipes and4 exact checkpoints verified. |
| F36 | Actual shortage→history→native16→18 policy pair→entity comparison→Quit→bookmark/restore/export journey, no page errors. |

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

Use a fresh output directory with `scripts/world-laboratory-example.sh generate`
and `live`, passing `$CHRONICLER_NATIVE_ENV/bin/python`. Existing older bundles
remain viewable; older-source/native checkpoints refuse exact loading. Never use
a mismatch override or silently reuse a wheel from changed Rust/ABI inputs.

## Actual checks and receipts

Final CI: **1,107 viewer tests / 101 files**, lint and production build;
**9,510 native tests / six canonical skips / 623 subtests**; **9,133 native-absent
tests / 369 skips / 623 subtests**; **1,178 Rust tests / two ignored**; all 46
bounded offline chunks and current-source native wheel production/transfer gates
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
Current-source long-run/lifecycle/output checks provide the combined proof above.

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

## Final recovery and shutdown

Source is pushed and verified on the development branch. Only closing handoff
text follows tested code `38116fc2`; verify a future checkout before development.
No unfinished source/WIP remains. All owned simulations, browsers and the preview
server are stopped. No further campaign or automatic startup test is queued.

`/workspace/shared/chronicler-multiwave-evidence/release-final` contains:

- `source-final.bundle`: final development head, bundle verification and a clean
  exact trial restore in `restore-final`; Rust tree and 280 package/native/lock
  files match. `restore-final.json` records the exact commit.
- `worlds-and-evidence-final.tar.gz`: real worlds/checkpoints, private screenshots,
  declarations, neutral/adverse outcomes, failed experiments, CI and browser
  receipts. `archive-members-sha256.json` verifies every archived member.
- `SHA256.json` and `release-receipt.json`: final byte counts/hashes and scope.

The earlier `release-942da692` backup and failed CI remain preserved. Source is
backed up remotely in Git; generated-data archives are local shared-workspace
copies, not an off-machine upload. Source restoration is verified; reusable
cloud configuration publication and a fresh cloud task remain deferred and
unverified. No public deployment, new credentials or paid narration/API calls.
